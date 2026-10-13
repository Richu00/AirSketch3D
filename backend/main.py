import asyncio, time
from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from backend.config.manager import ConfigManager
from backend.vision.camera import Camera
from backend.gestures.recognizer import GestureRecognizer
from backend.gestures.stabilizer import Stabilizer
from backend.actions.controller import ActionController
from backend.modes.manager import ModeManager, MODES
from backend.sketch.engine import SketchEngine
from backend.sketch.recognition import SketchGestureRecognizer
from backend.sketch.inspector import SketchInspector

HOST, PORT = "127.0.0.1", 8000


class AppState:
    def __init__(self):
        self.config = ConfigManager()
        self.settings = self.config.settings()
        self.camera = None
        self.tracker = None
        self.actions = ActionController(self.config)
        self.modes = ModeManager(self.actions, apps_provider=lambda: self.config.applications().get('applications', []))
        self.recognizer = GestureRecognizer()
        self.stabilizer = Stabilizer()
        self.sketch = SketchEngine()
        self.sketch_recognizer = SketchGestureRecognizer()
        self.sketch_inspector = SketchInspector()
        self._sent_sketch_version = -1
        self._thumb_frames = 0
        self._palm_left_frames = 0
        self._palm_left_latched = False
        self._inspect_transition_until = 0.0
        self.sketch_debug = {}
        self.apply_settings()
        self.running = False
        self.clients = set()
        self.task = None
        self.latest_jpeg = None
        self.frame_id = 0
        self.dragging = False
        self.latest = {'hand_detected': False, 'landmarks': [], 'gesture': 'NONE', 'confidence': 0, 'fps': 0,
                       'mode': 'DESKTOP', 'action': '', 'system_status': 'OFFLINE', 'is_running': False,
                       'is_paused': False, 'gesture_state': 'IDLE', 'scroll_direction': None,
                       'cursor_position': None, 'launcher': self.modes.launcher_state(),
                       'sketch': self.sketch_state(0.0), 'sketch_strokes': [], 'sketch_model': None, 'hands': []}

    # paused lives in the mode manager so gesture handling and the API agree
    @property
    def paused(self): return self.modes.paused
    @paused.setter
    def paused(self, v): self.modes.paused = bool(v)
    @property
    def mode(self): return self.modes.mode

    def apply_settings(self):
        s = self.settings
        g, c = s['gesture'], s['camera']
        rec = dict(s.get('recognition', {}))
        rec['min_confidence'] = g['confidence_threshold']
        self.recognizer = GestureRecognizer(rec, aspect=c['width'] / max(1, c['height']))
        frames = g['stabilization_frames']
        # a pinch is a deliberate, fast gesture: confirm it a little sooner than the others
        self.stabilizer = Stabilizer(frames, g['cooldown_ms'], overrides={'PINCH': max(3, frames // 2)})
        sk = s.get('sketch', {})
        self.sketch.configure(sk, aspect=c['width'] / max(1, c['height']))
        self.sketch_recognizer.configure(
            params=rec, aspect=c['width'] / max(1, c['height']),
            history=sk.get('gesture_history', 5), hold_frames=sk.get('gesture_hold_frames', 2),
        )
        m = s.get('media', {})
        self.modes.configure(columns=s.get('launcher', {}).get('columns'), volume_steps=m.get('volume_steps'),
                             media_exit_hold_ms=m.get('exit_hold_ms'))

    def configure(self):
        from backend.vision.hand_tracker import HandTracker   # lazy: keeps the API importable without mediapipe
        c = self.settings['camera']
        self.camera = Camera(c['camera_index'], c['width'], c['height'], c['mirror'], c.get('exposure'))
        self.tracker = HandTracker(min_detection=0.5, min_tracking=0.5, model_complexity=0)

    async def broadcast(self, msg):
        dead = []
        for ws in list(self.clients):
            try: await ws.send_json(msg)
            except Exception: dead.append(ws)
        for ws in dead: self.clients.discard(ws)

    # ------------------------------------------------------------- sketch helpers
    def sketch_state(self, now=None):
        d = self.sketch.state(now)
        d['ml_active'] = False
        d['inspection'] = self.sketch_inspector.state()
        d['control_mode'] = self.modes.sketch_control_mode
        d['gesture_debug'] = dict(self.sketch_debug)
        return d

    def refresh_sketch(self, now=None):
        """Put the latest sketch data into `latest` (used by /status and new websocket clients)."""
        self.latest['sketch'] = self.sketch_state(now)
        self.latest['sketch_strokes'] = self.sketch.strokes_payload()
        self.latest['sketch_model'] = self.sketch.model
        self._sent_sketch_version = -1          # force the next broadcast to include strokes + model

    def _sketch_gesture(self, points, stable=None):
        """Pinch-free Sketch classifier; desktop pinch remains untouched."""
        if not points:
            self.sketch_recognizer.reset()
            self.sketch_debug = dict(self.sketch_recognizer.debug)
            return 'NONE'
        gesture, conf = self.sketch_recognizer.classify(points)
        self.sketch_debug = dict(self.sketch_recognizer.debug)
        self.sketch_debug['confidence'] = round(float(conf), 3)
        return gesture

    def _end_drag(self):
        if self.dragging:
            self.actions.end_drag(); self.dragging = False

    def process(self, points, now):
        """One frame of gesture logic. Returns (gesture, conf, motion, state, event_name, action)."""
        s = self.settings
        thr = s['gesture']['confidence_threshold']
        sketch_gesture = None
        general_gesture = 'NONE'
        if points:
            gesture, conf, motion = self.recognizer.recognize(points, now)
            general_gesture = gesture
        else:
            self.recognizer.reset()
            gesture, conf, motion = 'NONE', 0.0, {'scroll': 0, 'swipe': 0, 'swipe_event': None}

        if self.modes.mode == 'SKETCH':
            sketch_gesture = self._sketch_gesture(points) if points else 'NONE'
            sketch_conf = float(self.sketch_debug.get('confidence', 0.0)) if points else 0.0

            # PALM_LEFT is a Sketch-only static pose. Do not depend on the
            # general desktop confidence/stabilizer here: the screenshot/UI can
            # already be showing PALM LEFT while the general recognizer reports
            # a different open-palm pose. Count the Sketch classifier directly.
            # Three consecutive frames (~0.3s at 10 FPS) makes entry/exit deliberate.
            if sketch_gesture == 'PALM_LEFT' and self.sketch.model is not None and self.modes.sketch_control_mode == 'DRAW':
                self._palm_left_frames += 1
            else:
                self._palm_left_frames = 0
                self._palm_left_latched = False

            # Global safety/utility gestures remain available in Sketch mode.
            # Pinch is deliberately excluded; it is never mapped or acted upon here.
            if self.modes.sketch_control_mode == 'MOUSE':
                # MOUSE control: the normal desktop recognizer drives the cursor and PINCH clicks.
                gesture = general_gesture
            
            else:
                # DRAW control: sketch poses, plus the global safety gestures. THUMBS_UP is passed through
                # only so the hold-to-toggle timer can see it; it never draws or clicks.
                gesture = general_gesture if general_gesture in ('SCREENSHOT', 'THUMBS_DOWN', 'THUMBS_UP') else sketch_gesture
            if self.modes.sketch_control_mode == 'DRAW' and gesture == sketch_gesture:
                conf = max(float(conf), sketch_conf)

            # Sketch has its own pinch-free static classifier. Physical swipes are
            # intentionally ignored in Sketch; INSPECT is entered/exited only
            # with the deliberate screen-left open-palm pose.
            if gesture == 'VERTICAL_SCROLL':
                gesture = 'INDEX_POINT'

        # while paused only OPEN_PALM (resume) is allowed through. PALM_LEFT is
        # handled by the Sketch-only direct latch below, so it must never enter
        # the generic desktop stabilizer and fire a second toggle.
        if self.modes.mode == 'SKETCH' and gesture == 'PALM_LEFT':
            eff = 'NONE'
        else:
            eff = gesture if (not self.paused or gesture == 'OPEN_PALM') else 'NONE'
        event, state = self.stabilizer.update(eff, conf, thr, now)
        stable = self.stabilizer.stable
        mode = self.modes.mode
        cur = s['cursor']

        if points and not self.paused:
            if mode == 'APPS':
                if gesture in ('INDEX_POINT', 'VERTICAL_SCROLL') and stable in ('INDEX_POINT', 'VERTICAL_SCROLL'):
                    self.modes.update_hover(points[8][0], points[8][1])
            elif mode in ('DESKTOP', 'BROWSER'):
                if gesture == 'PINCH' and stable == 'PINCH':
                    if abs(motion['swipe']) > 0.35 or abs(motion['scroll']) > 0.35:
                        self.actions.begin_drag(); self.dragging = True
                    if self.dragging:
                        self.actions.move_cursor(points[8][0], points[8][1], cur['sensitivity'], cur['smoothing'], cur['invert_x'], cur['invert_y'])
                elif gesture == 'INDEX_POINT' and stable == 'INDEX_POINT':
                    self.actions.move_cursor(points[8][0], points[8][1], cur['sensitivity'], cur['smoothing'], cur['invert_x'], cur['invert_y'])
                elif gesture == 'VERTICAL_SCROLL' and stable in ('INDEX_POINT', 'VERTICAL_SCROLL'):
                    self.actions.scroll(motion['scroll'])
        # SKETCH MOUSE control: reuse the normal cursor mapping (DRAW control never moves the cursor)
        if mode == 'SKETCH' and self.modes.sketch_control_mode == 'MOUSE' and points and not self.paused and not self.sketch_inspector.inspecting:
            if gesture == 'INDEX_POINT' and stable == 'INDEX_POINT':
                self.actions.move_cursor(points[8][0], points[8][1], cur['sensitivity'], cur['smoothing'], cur['invert_x'], cur['invert_y'])

        # SKETCH DRAW control: air-drawing (the cursor is NOT moved here)
        # A steady thumbs-up (8+ frames) means "toggle control mode", so it must not also start a fist-build.
        self._thumb_frames = self._thumb_frames + 1 if (points and general_gesture == 'THUMBS_UP') else 0
        sketch_event = ''
        if mode == 'SKETCH':
            if self.sketch_inspector.inspecting:
                # In inspect mode the hand is a controller, not a pen.
                self.sketch.update('NONE', None, now)
                self.sketch_inspector.update(getattr(self.tracker, 'last_hands', []) if self.tracker else [])
            else:
                draw_control = self.modes.sketch_control_mode == 'DRAW'
                in_transition_hold = now < self._inspect_transition_until
                sg = sketch_gesture if (draw_control and not self.paused and self._thumb_frames < 8 and not in_transition_hold) else 'NONE'
                tip = (points[8][0], points[8][1]) if points else None
                sketch_event = self.sketch.update(sg, tip, now)
        else:
            self.sketch.update('NONE', None, now)
            self.sketch_inspector.exit()

        # release a drag as soon as the pinch is gone (or the hand/pause/mode no longer allows it)
        if self.dragging and (stable != 'PINCH' or self.paused or mode not in ('DESKTOP', 'BROWSER')):
            self._end_drag()

        palm_left_event = (
            mode == 'SKETCH'
            and self.sketch.model is not None
            and self._palm_left_frames >= 1
            and not self._palm_left_latched
        )
        if palm_left_event:
            self._palm_left_latched = True

        event_name, action = event, ''
        if palm_left_event:
            # PALM_LEFT is intentionally handled outside the generic stabilizer.
            # This guarantees that the pose displayed by the Sketch recognizer
            # is the same pose that changes the 3D inspection state.
            if self.sketch_inspector.inspecting:
                self.sketch_inspector.exit()
                self._inspect_transition_until = now + 0.75
                action = 'Returned to Sketch'
            else:
                self.sketch_inspector.enter()
                self._inspect_transition_until = now + 0.35
                action = '3D Inspect Mode'
            event_name = 'PALM_LEFT'
        elif event and not self.sketch_inspector.inspecting:
            # Sketch-only editing commands. They never leak into Desktop/Browser.
            if mode == 'SKETCH' and not self.sketch_inspector.inspecting and event == 'THUMBS_LEFT':
                ok = self.sketch.undo_stroke()
                self.refresh_sketch(now)
                action = 'Sketch Undo' if ok else 'Nothing to Undo'
            elif mode == 'SKETCH' and not self.sketch_inspector.inspecting and event == 'THUMBS_RIGHT':
                ok = self.sketch.redo_stroke()
                self.refresh_sketch(now)
                action = 'Sketch Redo' if ok else 'Nothing to Redo'
            elif mode == 'SKETCH' and event == 'PALM_LEFT' and self.sketch.model:
                if self.sketch_inspector.inspecting:
                    self.sketch_inspector.exit()
                    action = 'Returned to Sketch'
                else:
                    self.sketch_inspector.enter()
                    action = '3D Inspect Mode'
                self.stabilizer.reset()
            else:
                action = self.modes.handle_event(event)
        elif motion.get('swipe_event') and not self.paused and mode != 'SKETCH':
            # Swipes remain available to Desktop/Browser/Media. Sketch now uses
            # a deliberate sideways open-palm pose instead of a moving swipe.
            event_name = motion['swipe_event']
            action = self.modes.handle_swipe(event_name)
        if mode == 'SKETCH' and self.sketch_inspector.inspecting and stable == 'FIST' and not self.sketch_inspector.solid:
            self.sketch_inspector.solid = True
            action = '3D Model Solidified'
            event_name = 'FIST'
        if sketch_event and not action:
            event_name, action = 'FIST', sketch_event
        if not action and not self.sketch_inspector.inspecting:
            tick = self.modes.tick(stable, now)
            if tick:
                event_name, action = ('THUMBS_UP' if mode == 'SKETCH' else 'THUMBS_DOWN'), tick
        if not action:
            event_name = None
        return gesture, conf, motion, state, event_name, action

    def _capture_and_track(self):
        """Blocking work (camera wait + MediaPipe + JPEG encode). Runs in a worker thread."""
        import cv2
        frame = self.camera.read() if self.camera else None
        if frame is None:
            return None, None
        points, _ = self.tracker.process(frame, draw=self.settings['camera']['show_landmarks'])
        ok, jpg = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 70])
        return points, (jpg.tobytes() if ok else None)

    async def loop(self):
        self.configure()
        while True:
            if not self.running:
                await asyncio.sleep(.08); continue
            points, jpg = await asyncio.to_thread(self._capture_and_track) if self.camera else (None, None)
            if points is None:
                self.latest.update(system_status='OFFLINE', is_running=False, hand_detected=False, landmarks=[])
                await self.broadcast({'type': 'state_update', 'data': self.latest}); await asyncio.sleep(.1); continue
            if jpg is not None:
                self.latest_jpeg = jpg; self.frame_id += 1
            gesture, conf, motion, state, event_name, action = self.process(points, time.perf_counter())
            self.latest = {'hand_detected': bool(points), 'landmarks': points, 'gesture': gesture, 'confidence': round(conf, 3),
                           'fps': round(self.camera.fps, 1), 'track_ms': round(getattr(self.tracker, 'last_ms', 0.0), 1), 'mode': self.mode, 'action': action,
                           'system_status': 'PAUSED' if self.paused else 'ACTIVE', 'is_running': self.running,
                           'is_paused': self.paused, 'gesture_state': state,
                           'scroll_direction': ('UP' if motion['scroll'] < 0 else 'DOWN') if gesture == 'VERTICAL_SCROLL' else None,
                           'cursor_position': list(self.actions.last_cursor) if self.actions.last_cursor else None,
                           'launcher': self.modes.launcher_state(),
                           'sketch': self.sketch_state(time.perf_counter()),
                           'hands': getattr(self.tracker, 'last_hands', []) if self.modes.mode == 'SKETCH' and self.sketch_inspector.inspecting else []}
            msg = dict(self.latest)
            if self.sketch.version != self._sent_sketch_version:      # strokes/model only when they changed
                self._sent_sketch_version = self.sketch.version
                msg['sketch_strokes'] = self.latest['sketch_strokes'] = self.sketch.strokes_payload()
                msg['sketch_model'] = self.latest['sketch_model'] = self.sketch.model
            else:
                msg.pop('sketch_strokes', None); msg.pop('sketch_model', None)
            await self.broadcast({'type': 'state_update', 'data': msg})
            if action:
                await self.broadcast({'type': 'action_event', 'data': {'gesture': event_name, 'action': action, 'confidence': conf,
                                                                       'mode': self.mode, 'timestamp': time.strftime('%H:%M:%S')}})
            await asyncio.sleep(0)


state = AppState()


@asynccontextmanager
async def lifespan(app):
    state.task = asyncio.create_task(state.loop()); yield
    state.running = False
    state._end_drag()
    if state.task: state.task.cancel()
    if state.tracker: state.tracker.close()
    if state.camera: state.camera.release()


app = FastAPI(title='AIRCONTROL', lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=['*'], allow_credentials=True, allow_methods=['*'], allow_headers=['*'])


@app.get('/health')
def health(): return {'ok': True, 'service': 'AIRCONTROL'}
@app.get('/status')
def status(): return state.latest
@app.get('/config')
def config(): return state.settings
@app.post('/config')
def update_config(payload: dict):
    state.settings = state.config.save_settings(payload); state.apply_settings(); return state.settings
@app.post('/start')
def start(): state.running = True; state.paused = False; return {'success': True}
@app.post('/stop')
def stop(): state.running = False; state._end_drag(); return {'success': True}
@app.post('/emergency-stop')
def emergency(): state.running = False; state.paused = True; state._end_drag(); return {'success': True}
@app.post('/mode')
def mode(payload: dict):
    m = str(payload.get('mode', 'DESKTOP')).upper()
    state.modes.set_mode(m if m in MODES else 'DESKTOP')
    if state.modes.mode != 'SKETCH':
        state.sketch_inspector.exit()
    else:
        state.sketch_inspector.exit()
        state.sketch_recognizer.reset()
    state.latest['mode'] = state.modes.mode; state.latest['launcher'] = state.modes.launcher_state()
    state.refresh_sketch()
    return {'success': True, 'mode': state.modes.mode}
@app.get('/sketch')
def sketch_get():
    return {**state.sketch_state(), 'strokes': state.sketch.strokes_payload(), 'model': state.sketch.model}
@app.post('/sketch/clear')
async def sketch_clear():
    state.sketch.clear(); state.sketch_inspector.reset(); state.refresh_sketch()
    await state.broadcast({'type': 'state_update', 'data': state.latest}); return {'success': True}
@app.post('/sketch/undo')
async def sketch_undo():
    ok = state.sketch.undo_stroke(); state.refresh_sketch()
    await state.broadcast({'type': 'state_update', 'data': state.latest}); return {'success': ok}
@app.post('/sketch/redo')
async def sketch_redo():
    ok = state.sketch.redo_stroke(); state.refresh_sketch()
    await state.broadcast({'type': 'state_update', 'data': state.latest}); return {'success': ok}
@app.post('/sketch/inspect/reset-view')
async def sketch_reset_view():
    state.sketch_inspector.reset_view(); state.refresh_sketch()
    await state.broadcast({'type': 'state_update', 'data': state.latest}); return {'success': True}
@app.post('/sketch/generate')
async def sketch_generate():
    state.sketch_inspector.reset()
    ok, msg = state.sketch.generate(); state.refresh_sketch()
    await state.broadcast({'type': 'state_update', 'data': state.latest})
    return JSONResponse({'success': ok, 'message': msg, 'model': state.sketch.model}, status_code=200 if ok else 400)
@app.get('/applications')
def applications(): return state.config.applications()
@app.get('/websites')
def websites(): return state.config.websites()
@app.get('/gestures')
def gestures(): return state.config.gestures()
@app.post('/launch-app')
def launch(payload: dict):
    ok, msg = state.actions.launch_app(payload.get('name', '')); return JSONResponse({'success': ok, 'message': msg}, status_code=200 if ok else 404)
@app.post('/open-website')
def website(payload: dict):
    ok = state.actions.open_website(payload.get('url', '')); return {'success': bool(ok)}
@app.get('/video_feed')
def video_feed():
    async def gen():
        last = -1
        while True:
            if state.latest_jpeg is not None and state.frame_id != last:
                last = state.frame_id
                yield b'--frame\r\nContent-Type: image/jpeg\r\n\r\n' + state.latest_jpeg + b'\r\n'
            await asyncio.sleep(.008)
    return StreamingResponse(gen(), media_type='multipart/x-mixed-replace; boundary=frame')
@app.websocket('/ws')
async def websocket(ws: WebSocket):
    await ws.accept(); state.clients.add(ws)
    try:
        await ws.send_json({'type': 'state_update', 'data': state.latest})
        while True: await ws.receive_text()
    except WebSocketDisconnect: state.clients.discard(ws)
    except Exception: state.clients.discard(ws)


if __name__ == '__main__':
    # `python -m backend.main` now actually starts the server (it silently did nothing before).
    import uvicorn
    uvicorn.run(app, host=HOST, port=PORT)

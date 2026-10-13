"""Mode state machine: decides what each gesture does in each mode.

Modes: DESKTOP (default), BROWSER, APPS (launcher), MEDIA, SKETCH (air-draw -> 3D model).
Keeping this separate from main.py makes the gesture->action mapping testable
without a camera, a screen or a window system.
"""
import math

MODES = ("DESKTOP", "BROWSER", "APPS", "MEDIA", "SKETCH")


class ModeManager:
    def __init__(self, actions, apps_provider=None, columns=3, volume_steps=5, media_exit_hold_ms=1500):
        self.actions = actions
        self.apps_provider = apps_provider or (lambda: [])
        self.columns = max(1, int(columns))
        self.volume_steps = max(1, int(volume_steps))
        self.media_exit_hold_ms = media_exit_hold_ms
        self.mode = "DESKTOP"
        self.paused = False
        self.items = []
        self.hover = -1
        self.pointer = None
        self._pu = None
        self._pv = None
        self.media_playing = None   # assumed - OS media keys are toggles, real state is unknown
        self._td_since = None
        self._td_done = False
        # Sketch has two control modes: DRAW (air-drawing, pinch-free) and MOUSE (normal cursor + pinch click).
        # Switching is a deliberate HOLD of thumbs-up, so a fist with the thumb poking out cannot flip it by accident.
        self.sketch_control_mode = "DRAW"
        self.sketch_toggle_hold_ms = 1000
        self._tu_since = None
        self._tu_done = False

    # -------------------------------------------------------------- mode ctrl
    def configure(self, columns=None, volume_steps=None, media_exit_hold_ms=None):
        if columns: self.columns = max(1, int(columns))
        if volume_steps: self.volume_steps = max(1, int(volume_steps))
        if media_exit_hold_ms: self.media_exit_hold_ms = media_exit_hold_ms

    def set_mode(self, mode):
        mode = mode if mode in MODES else "DESKTOP"
        if mode == "APPS":
            self.items = [a.get("name", "") for a in self.apps_provider()]
            self.hover, self.pointer, self._pu, self._pv = -1, None, None, None
        if mode == "MEDIA":
            self.media_playing = None
        if mode == "SKETCH":
            self.paused = False          # a paused desktop must not freeze the sketch pad
        self.sketch_control_mode = "DRAW"
        self._tu_since, self._tu_done = None, False
        self._td_since, self._td_done = None, False
        self.mode = mode
        return mode

    def launcher_state(self):
        return {"open": self.mode == "APPS", "items": self.items if self.mode == "APPS" else [],
                "hover_index": self.hover if self.mode == "APPS" else -1,
                "pointer": self.pointer if self.mode == "APPS" else None, "columns": self.columns}

    # --------------------------------------------------------------- launcher
    def update_hover(self, x, y):
        """Map the index fingertip (normalised frame coords) onto the launcher grid."""
        if self.mode != "APPS" or not self.items:
            return
        u = min(1.0, max(0.0, (x - 0.2) / 0.6))   # use the central 60% of the frame
        v = min(1.0, max(0.0, (y - 0.25) / 0.5))
        a = 0.35                                    # smoothing
        self._pu = u if self._pu is None else self._pu * (1 - a) + u * a
        self._pv = v if self._pv is None else self._pv * (1 - a) + v * a
        n = len(self.items)
        rows = math.ceil(n / self.columns)
        col = min(self.columns - 1, int(self._pu * self.columns))
        row = min(rows - 1, int(self._pv * rows))
        idx = row * self.columns + col
        self.hover = idx if idx < n else -1
        self.pointer = [round(self._pu, 3), round(self._pv, 3)]

    # ---------------------------------------------------------------- events
    def handle_event(self, g):
        """Handle a debounced one-shot gesture. Returns action text ('' = nothing)."""
        if self.paused:
            if g == "OPEN_PALM":
                self.paused = False
                return "Gesture Control Resumed"
            return ""
        m = self.mode

        if g == "SCREENSHOT":                      # same in every mode
            return "Screenshot: " + self.actions.screenshot()

        if m == "APPS":
            if g == "PINCH":
                if self.hover < 0 or self.hover >= len(self.items):
                    return "No application selected"
                name = self.items[self.hover]
                ok, msg = self.actions.launch_app(name)
                self.mode = "DESKTOP"
                return msg if ok else "Launch failed: " + msg
            if g == "THUMBS_DOWN":
                self.mode = "DESKTOP"
                return "Launcher Closed"
            return ""

        if m == "SKETCH":
            # drawing / erasing / pausing / generating are continuous and handled by SketchEngine.
            # Discrete events: leaving the mode, and (in MOUSE control) a pinch click.
            # DRAW mode never consumes pinch. THUMBS_UP is a HOLD handled in tick().
            if g == "THUMBS_DOWN":
                self.mode = "DESKTOP"
                self.sketch_control_mode = "DRAW"
                return "Sketch Mode Exited"
            if self.sketch_control_mode == "MOUSE" and g == "PINCH":
                self.actions.click()
                return "Mouse Click"
            return ""

        if m == "MEDIA":
            if g == "OPEN_PALM":
                self.media_playing = True
                self.actions.media("play_pause"); return "Play / Resume"
            if g == "FIST":
                self.media_playing = False
                self.actions.media("play_pause"); return "Pause"
            if g == "THUMBS_UP":
                self.actions.media("volume_up", self.volume_steps); return "Volume Up"
            return ""                               # THUMBS_DOWN handled in tick()

        # DESKTOP / BROWSER share pointer behaviour
        if g in ("PINCH", "FIST"):
            self.actions.click(); return "Left Click"
        if g == "OPEN_PALM":
            return ""                               # already active
        if g == "PEACE":
            if m == "BROWSER": return ""
            self.mode = "BROWSER"; return "Browser Mode"
        if g == "THUMBS_UP":
            self.set_mode("APPS"); return "Application Launcher"
        if g == "THUMBS_DOWN":
            if m == "BROWSER":
                self.mode = "DESKTOP"; return "Exited Browser Mode"
            self.paused = True; return "Gesture Control Paused"
        return ""

    def handle_swipe(self, direction):
        if self.paused or self.mode in ("APPS", "SKETCH"):
            return ""
        nxt = direction == "SWIPE_RIGHT"
        if self.mode == "BROWSER":
            (self.actions.browser_forward if nxt else self.actions.browser_back)()
        else:
            self.actions.media("next" if nxt else "previous")
        return "Next" if nxt else "Previous"

    def tick(self, stable, now):
        """Time-based gestures.

        Sketch: HOLD thumbs-up ~1 s toggles DRAW <-> MOUSE control.
        Media:  thumbs-down TAP = volume down, HOLD = exit media mode.
        """
        if self.mode == "SKETCH" and not self.paused:
            if stable == "THUMBS_UP":
                if self._tu_since is None:
                    self._tu_since, self._tu_done = now, False
                elif not self._tu_done and (now - self._tu_since) * 1000 >= self.sketch_toggle_hold_ms:
                    self._tu_done = True
                    self.sketch_control_mode = "MOUSE" if self.sketch_control_mode == "DRAW" else "DRAW"
                    return "Sketch Mouse Control" if self.sketch_control_mode == "MOUSE" else "Sketch Draw Control"
            else:
                self._tu_since, self._tu_done = None, False
            return ""
        self._tu_since, self._tu_done = None, False
        if self.mode != "MEDIA" or self.paused:
            self._td_since, self._td_done = None, False
            return ""
        if stable == "THUMBS_DOWN":
            if self._td_since is None:
                self._td_since, self._td_done = now, False
            elif not self._td_done and (now - self._td_since) * 1000 >= self.media_exit_hold_ms:
                self._td_done = True
                self.mode = "DESKTOP"
                return "Media Mode Exited"
            return ""
        out = ""
        if self._td_since is not None and not self._td_done:
            self.actions.media("volume_down", self.volume_steps)
            out = "Volume Down"
        self._td_since, self._td_done = None, False
        return out

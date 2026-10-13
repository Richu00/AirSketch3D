import { useEffect, useRef, useState } from 'react';
import * as THREE from 'three';
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js';
import { STLExporter } from 'three/examples/jsm/exporters/STLExporter.js';
import { OBJExporter } from 'three/examples/jsm/exporters/OBJExporter.js';
import { Box, Download, RotateCw, Sparkles, Trash2, Undo2, Redo2, Grid3x3, Eye, MousePointer2, Hand, ArrowLeft, Image as ImageIcon, Crosshair } from 'lucide-react';
import { useStore } from '../../store/useStore';
import { sketchClear, sketchGenerate, sketchUndo, sketchRedo, sketchResetView } from '../../api/client';

/** AirSketch3D viewer: mouse orbit remains available; hand inspection is additive. */
export function SketchViewer() {
  const { systemState, addNotification } = useStore();
  const sketch = systemState.sketch;
  const model = systemState.sketch_model;
  const holder = useRef<HTMLDivElement>(null);
  const groupRef = useRef<THREE.Group | null>(null);
  const controlsRef = useRef<OrbitControls | null>(null);
  const sceneRef = useRef<THREE.Scene | null>(null);
  const rendererRef = useRef<THREE.WebGLRenderer | null>(null);
  const cameraRef = useRef<THREE.PerspectiveCamera | null>(null);
  const [wire, setWire] = useState(false);
  const [spin, setSpin] = useState(true);

  useEffect(() => {
    const el = holder.current;
    if (!el) return;
    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(45, 1, 0.1, 100);
    camera.position.set(2.6, 2.0, 3.2);
    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    el.appendChild(renderer.domElement);
    scene.add(new THREE.AmbientLight(0xffffff, 0.7));
    const key = new THREE.DirectionalLight(0xffffff, 1.4); key.position.set(3, 5, 4); scene.add(key);
    const rim = new THREE.DirectionalLight(0x22d3ee, 0.8); rim.position.set(-4, 2, -3); scene.add(rim);
    scene.add(new THREE.GridHelper(4, 16, 0x0e7490, 0x1e293b));
    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.autoRotate = true;
    controls.autoRotateSpeed = 2.2;
    controlsRef.current = controls;
    sceneRef.current = scene;
    rendererRef.current = renderer;
    cameraRef.current = camera;
    const resize = () => {
      const w = el.clientWidth || 1, h = el.clientHeight || 1;
      renderer.setSize(w, h, false);
      renderer.domElement.style.width = '100%'; renderer.domElement.style.height = '100%';
      camera.aspect = w / h; camera.updateProjectionMatrix();
    };
    resize();
    const ro = new ResizeObserver(resize); ro.observe(el);
    let raf = 0;
    const tick = () => { controls.update(); renderer.render(scene, camera); raf = requestAnimationFrame(tick); };
    tick();
    return () => {
      cancelAnimationFrame(raf); ro.disconnect(); controls.dispose(); renderer.dispose();
      if (renderer.domElement.parentNode === el) el.removeChild(renderer.domElement);
      sceneRef.current = null; groupRef.current = null; controlsRef.current = null; rendererRef.current = null; cameraRef.current = null;
    };
  }, []);

  useEffect(() => {
    const scene = sceneRef.current;
    if (!scene) return;
    if (groupRef.current) {
      scene.remove(groupRef.current);
      groupRef.current.traverse((obj) => {
        const mesh = obj as THREE.Mesh;
        if (mesh.geometry) mesh.geometry.dispose();
        if (mesh.material) {
          const mats = Array.isArray(mesh.material) ? mesh.material : [mesh.material];
          mats.forEach((m) => m.dispose());
        }
      });
      groupRef.current = null;
    }
    if (!model) return;
    const group = new THREE.Group();
    const outlines = model.outlines?.length ? model.outlines : [model.outline];
    const solid = sketch?.inspection?.solid ?? false;
    outlines.forEach((outline) => {
      if (outline.length < 3) return;
      const shape = new THREE.Shape();
      outline.forEach(([x, y], i) => i === 0 ? shape.moveTo(x, y) : shape.lineTo(x, y));
      shape.closePath();
      const geo = new THREE.ExtrudeGeometry(shape, { depth: model.height, bevelEnabled: false, curveSegments: 1 });
      geo.translate(0, 0, -model.height / 2);
      const mat = new THREE.MeshStandardMaterial({ color: 0x22d3ee, metalness: 0.25, roughness: 0.4, flatShading: true, wireframe: wire || !solid });
      const mesh = new THREE.Mesh(geo, mat);
      mesh.add(new THREE.LineSegments(new THREE.EdgesGeometry(geo, 25), new THREE.LineBasicMaterial({ color: 0xe0f2fe })));
      group.add(mesh);
    });
    scene.add(group);
    groupRef.current = group;
  }, [model?.id, wire, sketch?.inspection?.solid]);

  useEffect(() => {
    const g = groupRef.current;
    const i = sketch?.inspection;
    if (!g || !i) return;
    g.rotation.set(i.rotation[0], i.rotation[1], i.rotation[2]);
    g.position.set(i.pan[0], i.pan[1], 0);
    const z = i.zoom || 1;
    g.scale.setScalar(z);
  }, [sketch?.inspection]);

  useEffect(() => { if (controlsRef.current) controlsRef.current.autoRotate = spin && !sketch?.inspection?.inspecting; }, [spin, sketch?.inspection?.inspecting]);

  const download = (kind: 'stl' | 'obj') => {
    const object = groupRef.current;
    if (!object) return;
    object.updateMatrixWorld(true);
    const data = kind === 'stl' ? new STLExporter().parse(object) : new OBJExporter().parse(object);
    const url = URL.createObjectURL(new Blob([data], { type: 'text/plain' }));
    const a = document.createElement('a'); a.href = url; a.download = `airsketch3d-${model?.id ?? 0}.${kind}`; a.click();
    URL.revokeObjectURL(url);
  };

  // PNG snapshot of the current 3D view (drawn onto a dark background so it is not transparent).
  const savePng = () => {
    const r = rendererRef.current, s = sceneRef.current, c = cameraRef.current;
    if (!r || !s || !c || !model) return;
    r.render(s, c);                                   // render + read in the same tick (no preserveDrawingBuffer needed)
    const src = r.domElement;
    const out = document.createElement('canvas');
    out.width = src.width; out.height = src.height;
    const ctx = out.getContext('2d');
    if (!ctx) return;
    ctx.fillStyle = '#070b16'; ctx.fillRect(0, 0, out.width, out.height);
    ctx.drawImage(src, 0, 0);
    const a = document.createElement('a');
    a.href = out.toDataURL('image/png'); a.download = `airsketch3d-${model.id ?? 0}.png`; a.click();
  };

  const generate = async () => {
    try {
      const r = await sketchGenerate();
      addNotification({ gesture: 'FIST', action: r.message, confidence: 1 });
    } catch (error) {
      addNotification({ gesture: 'FIST', action: error instanceof Error ? error.message : 'Could not generate 3D model', confidence: 1 });
    }
  };

  const pct = Math.round((sketch?.fist_progress ?? 0) * 100);
  const inspecting = sketch?.inspection?.inspecting;
  const btn = 'px-2 py-1.5 rounded-lg border border-slate-700/80 text-[10px] text-slate-300 hover:bg-white/5 hover:text-cyan-200 flex items-center gap-1.5 transition-colors';
  const on = 'border-cyan-400/50 text-cyan-200 bg-cyan-400/10';

  return (
    <div className="glass-panel rounded-2xl overflow-hidden h-full min-h-[240px] hud-corners relative flex flex-col">
      <div className="flex items-center justify-between px-4 pt-3 pb-2 gap-2 flex-wrap">
        <div className="flex items-center gap-2 text-[10px] tracking-[.2em] text-fuchsia-300"><Box size={14} /> 3D MODEL</div>
        {inspecting && (
          <div className="flex items-center gap-1.5 rounded-full border border-cyan-400/40 bg-cyan-400/10 px-2.5 py-1 text-[9px] tracking-[.16em] text-cyan-200">
            <Eye size={11} /> INSPECT MODE
          </div>
        )}
        <div className="flex gap-1.5 flex-wrap">
          <button className={btn} onClick={() => sketchUndo().catch(() => {})} title="Undo last stroke"><Undo2 size={12} />Undo</button><button className={btn} onClick={() => sketchRedo().catch(() => {})} title="Redo last undone stroke"><Redo2 size={12} />Redo</button>
          <button className={btn} onClick={() => sketchClear().catch(() => {})} title="Clear drawing and model"><Trash2 size={12} />Clear</button>
          <button className={btn} onClick={generate} title="Generate without the fist gesture"><Sparkles size={12} />Generate</button>
        </div>
      </div>
      <div className="relative flex-1 min-h-[180px]">
        <div ref={holder} className="absolute inset-0" />
        {!model && <div className="absolute inset-0 flex flex-col items-center justify-center text-center px-6 pointer-events-none"><div className="text-slate-400 text-xs tracking-[.2em]">NO MODEL YET</div><div className="text-slate-500 text-[11px] mt-2 leading-relaxed">☝️ draw · ✌️ erase · 🖐️ pause · ✊ hold fist = make 3D<br />Loop back to the green ring to close it — or just hold the fist, small gaps are closed for you</div><div className="text-slate-600 text-[10px] mt-2">{sketch?.points ?? 0} points · {sketch?.closed_strokes ?? 0} closed</div></div>}
        {pct > 0 && pct < 100 && <div className="absolute left-4 right-4 bottom-3"><div className="text-[9px] tracking-widest text-amber-300 mb-1">HOLD FIST · {pct}%</div><div className="h-1 bg-slate-800 rounded"><div className="h-1 rounded bg-amber-300" style={{ width: `${pct}%` }} /></div></div>}
        {inspecting && model && (
          <div className="absolute left-3 top-3 rounded-xl border border-cyan-400/30 bg-slate-950/75 backdrop-blur-sm px-3 py-2 text-[9px] text-cyan-100 pointer-events-none">
            <div className="tracking-[.18em] text-cyan-300 mb-1">3D INSPECT</div>
            <div className="text-slate-400">Move your hand to interact with the model</div>
            <div className="text-slate-500 mt-1">Palm ← exits inspect</div>
          </div>
        )}
      </div>
      <div className="px-4 py-2 border-t border-slate-800/70 text-[9px] text-slate-400">
        {inspecting ? (
          <div className="flex items-center gap-3 flex-wrap">
            <span className="inline-flex items-center gap-1"><Hand size={11} /> one hand: rotate</span>
            <span>✋✋ two hands: pan / zoom</span>
            <span>✊ solidify</span>
            <span className="text-cyan-300">🖐️← palm left: exit</span>
          </div>
        ) : sketch?.control_mode === 'MOUSE' ? (
          <div className="flex items-center gap-3 flex-wrap">
            <span className="inline-flex items-center gap-1"><MousePointer2 size={11} /> ☝️ move</span>
            <span>🤏 click</span>
            <span>👈 undo</span>
            <span>👉 redo</span>
            <span>👍 hold: DRAW</span>
          </div>
        ) : (
          <div className="flex items-center gap-3 flex-wrap">
            <span>☝️ draw</span><span>✌️ erase</span><span>🖐️ pause</span><span>✊ build</span>
            <span>👈 undo</span><span>👉 redo</span>
            <span className="text-cyan-300 inline-flex items-center gap-1"><ArrowLeft size={10} /> palm left: INSPECT</span>
            <span>👍 MOUSE</span>
          </div>
        )}
      </div>
      <div className="flex items-center justify-between gap-2 px-4 py-2 flex-wrap">
        <div className="flex gap-1.5"><button className={`${btn} ${spin ? on : ''}`} onClick={() => setSpin(!spin)}><RotateCw size={12} />Spin</button><button className={`${btn} ${wire ? on : ''}`} onClick={() => setWire(!wire)}><Grid3x3 size={12} />Wire</button>{inspecting && <button className={btn} onClick={() => sketchResetView().catch(() => {})} title="Reset rotation, pan and zoom"><Crosshair size={12} />Reset view</button>}</div>
        <div className="flex items-center gap-1.5"><button className={btn} disabled={!model} onClick={savePng} title="Save a PNG of the current view"><ImageIcon size={12} />PNG</button><button className={btn} disabled={!model} onClick={() => download('stl')}><Download size={12} />STL</button><button className={btn} disabled={!model} onClick={() => download('obj')}><Download size={12} />OBJ</button></div>
      </div>
    </div>
  );
}

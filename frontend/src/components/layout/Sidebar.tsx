import { Monitor, Globe2, AppWindow, Music2, Box, Pause, Play, Camera, Keyboard } from 'lucide-react';
import { useStore } from '../../store/useStore';
import { emergencyStop, startTracking, switchMode } from '../../api/client';
import type { Mode } from '../../types';

const modes = [
  ['DESKTOP', 'Desktop', Monitor, 'Cursor · click · scroll'],
  ['BROWSER', 'Browser', Globe2, '✌️ enter · 👎 exit'],
  ['APPS', 'Apps', AppWindow, '👍 open launcher'],
  ['MEDIA', 'Media', Music2, 'Play · volume · tracks'],
  ['SKETCH', 'Sketch 3D', Box, '☝️ draw · ✌️ erase · ✊ 3D'],
] as const;

export function Sidebar() {
  const { systemState, updateSystemState } = useStore();

  const setMode = async (m: Mode) => {
    try { await switchMode(m); updateSystemState({ mode: m }); } catch { /* backend offline */ }
  };
  const toggle = async () => {
    try {
      if (systemState.is_running) {
        await emergencyStop();
        updateSystemState({ is_running: false, is_paused: true, system_status: 'PAUSED' });
      } else {
        await startTracking();
        updateSystemState({ is_running: true, is_paused: false, system_status: 'ACTIVE' });
      }
    } catch { /* backend offline */ }
  };

  return (
    <aside className="w-16 md:w-52 shrink-0 border-r border-cyan-400/10 bg-slate-950/50 backdrop-blur p-2 md:p-3 flex flex-col gap-2 md:gap-3">
      <div className="hidden md:block text-[9px] tracking-[.25em] text-slate-500 px-2 pt-1">CONTROL MODES</div>
      {modes.map(([id, label, Icon, hint]) => {
        const active = systemState.mode === id;
        return (
          <button
            key={id}
            onClick={() => setMode(id)}
            title={label}
            className={`w-full p-3 rounded-xl flex items-center justify-center md:justify-start gap-3 text-left transition-all duration-200 border ${
              active ? 'bg-cyan-400/10 text-cyan-300 border-cyan-400/40 shadow-glow-cyan' : 'text-slate-400 border-transparent hover:bg-white/5 hover:text-slate-200'
            }`}
          >
            <Icon size={17} className="shrink-0" />
            <span className="hidden md:block min-w-0">
              <span className="block text-xs font-medium">{label}</span>
              <span className="block text-[9px] text-slate-500 truncate">{hint}</span>
            </span>
          </button>
        );
      })}

      <div className="mt-auto space-y-2">
        <div className="hidden md:block rounded-xl border border-slate-800 bg-slate-900/60 p-3 text-[10px] text-slate-500">
          <div className="flex items-center gap-2 mb-2 text-slate-400"><Camera size={13} /> TRACKING</div>
          <div className="text-emerald-400 font-mono">{systemState.fps.toFixed(0)} FPS</div>
          <div className="mt-2 flex items-center gap-2"><Keyboard size={12} /> ESC = EMERGENCY</div>
        </div>
        <button
          onClick={toggle}
          className={`w-full py-3 rounded-xl text-xs font-semibold flex items-center justify-center gap-2 border transition-colors ${
            systemState.is_running ? 'border-rose-400/30 text-rose-300 bg-rose-400/5 hover:bg-rose-400/10' : 'border-emerald-400/30 text-emerald-300 bg-emerald-400/5 hover:bg-emerald-400/10'
          }`}
        >
          {systemState.is_running ? <><Pause size={14} /><span className="hidden md:inline"> DISABLE</span></> : <><Play size={14} /><span className="hidden md:inline"> ACTIVATE</span></>}
        </button>
      </div>
    </aside>
  );
}

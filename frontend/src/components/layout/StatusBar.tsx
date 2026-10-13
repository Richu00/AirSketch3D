import { Activity, Wifi, WifiOff, Settings as SettingsIcon } from 'lucide-react';
import { useStore } from '../../store/useStore';
import { gestureMeta } from '../../lib/gestures';

const MODE_STYLE: Record<string, string> = {
  DESKTOP: 'text-cyan-300 border-cyan-400/30 bg-cyan-400/10',
  BROWSER: 'text-violet-300 border-violet-400/30 bg-violet-400/10',
  APPS: 'text-emerald-300 border-emerald-400/30 bg-emerald-400/10',
  MEDIA: 'text-amber-300 border-amber-400/30 bg-amber-400/10',
  SKETCH: 'text-fuchsia-300 border-fuchsia-400/30 bg-fuchsia-400/10',
};

export function StatusBar() {
  const { systemState, connectionStatus, toggleSettings } = useStore();
  const online = connectionStatus === 'connected';
  const g = gestureMeta(systemState.gesture);
  const paused = systemState.is_paused;
  const dot = !online ? 'bg-rose-400' : paused ? 'bg-amber-400' : systemState.is_running ? 'bg-emerald-400' : 'bg-slate-500';
  const label = !online ? 'BACKEND OFFLINE' : paused ? 'PAUSED' : systemState.is_running ? 'SYSTEM ONLINE' : 'STANDBY';

  return (
    <header className="h-16 shrink-0 border-b border-cyan-400/10 bg-slate-950/70 backdrop-blur-xl flex items-center justify-between px-4 sm:px-5 z-20">
      <div className="flex items-center gap-3">
        <div className="w-9 h-9 rounded-xl bg-cyan-400/10 border border-cyan-400/30 flex items-center justify-center text-cyan-300 shadow-glow-cyan">
          <Activity size={18} />
        </div>
        <div>
          <div className="font-semibold tracking-[.18em] text-sm">AIR<span className="text-cyan-300 glow-text-cyan">CONTROL</span></div>
          <div className="hidden sm:block text-[9px] text-slate-500 tracking-[.25em]">VISION INTERFACE</div>
        </div>
      </div>

      <div className="flex items-center gap-2 sm:gap-4 text-xs">
        <span className={`hidden md:flex items-center gap-2 px-3 py-1.5 rounded-full border ${paused ? 'text-slate-500 border-slate-700' : 'text-slate-200 border-slate-700/80 bg-white/5'}`}>
          <span className="text-base leading-none">{g.emoji}</span>
          <span className="tracking-wider text-[10px]">{g.label.toUpperCase()}</span>
        </span>
        <span className={`px-3 py-1.5 rounded-full border text-[10px] font-semibold tracking-[.18em] transition-colors ${MODE_STYLE[systemState.mode] ?? MODE_STYLE.DESKTOP}`}>
          {systemState.mode}
        </span>
        <span className="hidden sm:flex items-center gap-2 text-slate-400">
          {online ? <Wifi size={14} className="text-emerald-400" /> : <WifiOff size={14} className="text-rose-400" />}
          <span className="hidden lg:inline text-[10px] tracking-widest">{online ? 'LINKED' : 'OFFLINE'}</span>
        </span>
        <span className="flex items-center gap-2 text-[10px] tracking-widest">
          <i className={`w-2 h-2 rounded-full ${dot} ${online && !paused ? 'animate-pulse' : ''}`} />
          <span className="hidden sm:inline">{label}</span>
        </span>
        <button onClick={toggleSettings} aria-label="Settings" className="p-2 rounded-lg hover:bg-white/5 text-slate-400 hover:text-cyan-300 transition-colors">
          <SettingsIcon size={17} />
        </button>
      </div>
    </header>
  );
}

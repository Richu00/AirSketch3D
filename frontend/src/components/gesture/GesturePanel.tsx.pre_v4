import { Target, Zap, MousePointer2 } from 'lucide-react';
import { useStore } from '../../store/useStore';
import { gestureMeta } from '../../lib/gestures';

const STATE_STYLE: Record<string, string> = {
  IDLE: 'text-slate-500', DETECTING: 'text-amber-300', CONFIRMED: 'text-emerald-300', HELD: 'text-cyan-300', COOLDOWN: 'text-sky-300',
};

export function GesturePanel() {
  const { systemState } = useStore();
  const g = gestureMeta(systemState.gesture);
  const pct = Math.round(systemState.confidence * 100);
  const unknown = systemState.gesture === 'UNKNOWN';
  const sketch = systemState.sketch;
  const dbg = sketch?.gesture_debug;
  const circ = 2 * Math.PI * 26;

  return (
    <div className="glass-panel rounded-2xl p-4 flex flex-col">
      <div className="text-[9px] tracking-[.22em] text-slate-500 mb-4">GESTURE TELEMETRY</div>

      <div className="flex items-center gap-4">
        <div className="relative w-16 h-16 shrink-0">
          <svg viewBox="0 0 64 64" className="absolute inset-0 -rotate-90">
            <circle cx="32" cy="32" r="26" fill="none" stroke="rgba(51,65,85,.6)" strokeWidth="3" />
            <circle cx="32" cy="32" r="26" fill="none" stroke={unknown ? '#f59e0b' : '#22d3ee'} strokeWidth="3" strokeLinecap="round"
              strokeDasharray={circ} strokeDashoffset={circ * (1 - pct / 100)} style={{ transition: 'stroke-dashoffset .25s ease' }} />
          </svg>
          <div key={systemState.gesture} className="absolute inset-0 flex items-center justify-center text-2xl gesture-pop">{g.emoji}</div>
        </div>
        <div className="min-w-0">
          <div className="text-lg font-semibold tracking-wide truncate">{g.label}</div>
          <div className="text-[9px] text-slate-500 tracking-widest">CURRENT GESTURE</div>
          <div className="text-[11px] font-mono text-cyan-300 mt-1">{pct}% confidence</div>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-2 mt-5">
        <div className="glass-card rounded-xl p-3">
          <Target size={14} className="text-cyan-300 mb-2" />
          <div className="text-[9px] text-slate-500">STATE</div>
          <div className={`text-xs mt-1 font-medium ${STATE_STYLE[systemState.gesture_state] ?? ''}`}>{systemState.gesture_state}</div>
        </div>
        <div className="glass-card rounded-xl p-3">
          <Zap size={14} className="text-emerald-300 mb-2" />
          <div className="text-[9px] text-slate-500">ACTION</div>
          <div className="text-xs mt-1 truncate">{systemState.action || '—'}</div>
        </div>
      </div>

      {systemState.mode === 'SKETCH' && dbg && (
        <div className="mt-4 rounded-xl border border-cyan-400/15 bg-slate-950/35 p-3">
          <div className="flex items-center justify-between mb-2">
            <span className="text-[8px] tracking-[.2em] text-cyan-300">SKETCH GESTURE DEBUG</span>
            <span className={`text-[8px] font-mono ${dbg.locked ? 'text-emerald-300' : 'text-slate-500'}`}>{dbg.locked ? 'LOCKED' : 'WAITING'}</span>
          </div>
          <div className="grid grid-cols-2 gap-x-3 gap-y-1 text-[9px]">
            <span className="text-slate-500">RAW</span><span className="font-mono text-slate-300">{dbg.raw}</span>
            <span className="text-slate-500">STABLE</span><span className="font-mono text-cyan-300">{dbg.stable}</span>
            <span className="text-slate-500">CONFIDENCE</span><span className="font-mono text-slate-300">{Math.round((dbg.confidence ?? 0) * 100)}%</span>
            <span className="text-slate-500">HAND QUALITY</span><span className="font-mono text-slate-300">{Math.round((dbg.quality ?? 0) * 100)}%</span>
            <span className="text-slate-500">CANDIDATE</span><span className="font-mono text-amber-300">{dbg.candidate || '—'} {dbg.candidate ? `${dbg.candidate_frames}/${dbg.required_frames}` : ''}</span>
            <span className="text-slate-500">FINGERS</span><span className="font-mono text-slate-300">{(dbg.finger_states ?? []).join(' ') || '—'}</span>
          </div>
        </div>
      )}

      <div className="mt-4 pt-3 border-t border-slate-800/70 flex items-center gap-2">
        <MousePointer2 size={12} className="text-slate-500" />
        <div className="text-[9px] text-slate-500 tracking-widest">CURSOR</div>
        <div className="ml-auto font-mono text-xs text-slate-300">{systemState.cursor_position ? `${systemState.cursor_position[0]} × ${systemState.cursor_position[1]}` : '—'}</div>
      </div>
    </div>
  );
}

import { useStore } from '../../store/useStore';
import { MODE_GUIDE, gestureMeta } from '../../lib/gestures';

/** Cheat-sheet for the current mode; the row matching the live gesture lights up. */
export function GestureGuide() {
  const { systemState } = useStore();
  const rows = MODE_GUIDE[systemState.mode] ?? MODE_GUIDE.DESKTOP;
  const live = systemState.gesture;

  return (
    <div className="glass-panel rounded-2xl p-4 min-h-0 flex flex-col">
      <div className="flex items-center justify-between mb-3">
        <div className="text-[9px] tracking-[.22em] text-slate-500">{systemState.mode} · GESTURES</div>
        <div className="w-1.5 h-1.5 rounded-full bg-cyan-300 animate-pulse" />
      </div>
      <ul className="space-y-1 overflow-auto pr-1">
        {rows.map((r) => {
          const active = live === r.gesture;
          const m = gestureMeta(r.gesture);
          return (
            <li key={r.gesture} className={`flex items-center gap-3 px-2.5 py-1.5 rounded-lg border transition-all duration-150 ${active ? 'bg-cyan-400/10 border-cyan-400/40 text-cyan-200 shadow-glow-cyan' : 'border-transparent text-slate-400'}`}>
              <span className="text-lg w-6 text-center leading-none">{m.emoji}</span>
              <span className="text-[11px] truncate">{r.action}</span>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

import { X, AppWindow } from 'lucide-react';
import { useEffect, useState } from 'react';
import { getApplications, launchApp, switchMode } from '../../api/client';
import { useStore } from '../../store/useStore';

interface App { name: string; path: string }

export function AppLauncher() {
  const { systemState, updateSystemState } = useStore();
  const open = systemState.mode === 'APPS';
  const launcher = systemState.launcher;
  const [apps, setApps] = useState<App[]>([]);

  useEffect(() => {
    if (open) getApplications().then((x) => setApps(x.applications)).catch(() => {});
  }, [open]);

  if (!open) return null;
  const close = async () => { try { await switchMode('DESKTOP'); } catch { /* offline */ } updateSystemState({ mode: 'DESKTOP' }); };
  const hover = launcher?.hover_index ?? -1;
  const cols = launcher?.columns ?? 3;
  const pointer = launcher?.pointer;

  return (
    <div className="overlay-backdrop flex items-center justify-center p-4 overlay-in">
      <div className="w-[760px] max-w-full glass-panel rounded-2xl p-5 sm:p-6 shadow-glow-cyan">
        <div className="flex justify-between items-center mb-5">
          <div>
            <div className="text-[10px] tracking-[.25em] text-cyan-300">APPLICATION MATRIX</div>
            <h2 className="text-xl font-semibold mt-1">Select an application</h2>
          </div>
          <button onClick={close} aria-label="Close launcher" className="p-2 rounded-lg hover:bg-white/5 text-slate-400 hover:text-white"><X size={19} /></button>
        </div>

        <div className="relative">
          <div className="grid gap-3" style={{ gridTemplateColumns: `repeat(${cols}, minmax(0, 1fr))` }}>
            {apps.map((a, i) => {
              const active = i === hover;
              return (
                <button
                  key={a.name}
                  onClick={() => launchApp(a.name).then(close).catch(() => {})}
                  className={`glass-card rounded-xl p-5 text-left transition-all duration-150 ${active ? 'tile-active' : 'hover:border-cyan-400/30'}`}
                >
                  <AppWindow size={20} className={active ? 'text-cyan-200' : 'text-cyan-300/70'} />
                  <div className={`mt-5 text-sm ${active ? 'text-white font-semibold' : 'text-slate-200'}`}>{a.name}</div>
                  <div className="text-[9px] text-slate-600 mt-1 truncate">{a.path}</div>
                  {active && <div className="mt-2 text-[9px] tracking-[.2em] text-cyan-300">🤏 PINCH TO LAUNCH</div>}
                </button>
              );
            })}
          </div>
          {pointer && (
            <div className="pointer-dot" style={{ left: `${pointer[0] * 100}%`, top: `${pointer[1] * 100}%` }} />
          )}
        </div>

        <div className="mt-5 pt-4 border-t border-slate-800/70 flex flex-wrap gap-x-6 gap-y-2 text-[11px] text-slate-400">
          <span>☝️ move / hover</span><span>🤏 launch highlighted app</span><span>👎 cancel</span>
          <span className="ml-auto text-slate-600">Edit config/applications.json</span>
        </div>
      </div>
    </div>
  );
}

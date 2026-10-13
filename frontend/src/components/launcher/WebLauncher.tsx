import { X, Globe2, ExternalLink } from 'lucide-react';
import { useEffect, useState } from 'react';
import { getWebsites, openWebsite, switchMode } from '../../api/client';
import { useStore } from '../../store/useStore';

export function WebLauncher() {
  const { systemState, updateSystemState } = useStore();
  const open = systemState.mode === 'BROWSER';
  const [sites, setSites] = useState<{ name: string; url: string }[]>([]);

  useEffect(() => {
    if (open) getWebsites().then((x) => setSites(x.websites)).catch(() => {});
  }, [open]);

  if (!open) return null;
  const close = async () => { try { await switchMode('DESKTOP'); } catch { /* offline */ } updateSystemState({ mode: 'DESKTOP' }); };

  return (
    <div className="overlay-backdrop flex items-center justify-center p-4 overlay-in">
      <div className="w-[760px] max-w-full glass-panel rounded-2xl p-5 sm:p-6 shadow-glow-cyan">
        <div className="flex justify-between items-center mb-5">
          <div>
            <div className="text-[10px] tracking-[.25em] text-violet-300">WEB GATEWAY · BROWSER MODE</div>
            <h2 className="text-xl font-semibold mt-1">Open a website</h2>
          </div>
          <button onClick={close} aria-label="Exit browser mode" className="p-2 rounded-lg hover:bg-white/5 text-slate-400 hover:text-white"><X size={19} /></button>
        </div>
        <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
          {sites.map((s) => (
            <button key={s.name} onClick={() => openWebsite(s.url)} className="glass-card rounded-xl p-5 text-left hover:border-violet-400/40 hover:shadow-glow-cyan transition-all">
              <Globe2 size={20} className="text-violet-300" />
              <div className="mt-5 text-sm">{s.name}</div>
              <div className="text-[9px] text-slate-600 mt-1 flex items-center gap-1 truncate">{s.url}<ExternalLink size={10} /></div>
            </button>
          ))}
        </div>
        <div className="mt-5 pt-4 border-t border-slate-800/70 flex flex-wrap gap-x-6 gap-y-2 text-[11px] text-slate-400">
          <span>☝️ move cursor</span><span>🤏 select / click</span><span>👈 👉 back / forward</span><span>👎 exit mode</span>
        </div>
      </div>
    </div>
  );
}

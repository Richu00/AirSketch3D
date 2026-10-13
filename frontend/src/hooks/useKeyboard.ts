import { useEffect } from 'react';
import { emergencyStop, switchMode } from '../api/client';
import { useStore } from '../store/useStore';

export function useKeyboard() {
  const { updateSystemState, showSettings, toggleSettings } = useStore();

  useEffect(() => {
    const handleKeyDown = async (e: KeyboardEvent) => {
      if (e.key !== 'Escape') return;
      // 1st Esc closes whatever is open (settings, launcher, browser/media mode); otherwise emergency stop.
      if (showSettings) { toggleSettings(); return; }
      const mode = useStore.getState().systemState.mode;
      if (mode !== 'DESKTOP') {
        try { await switchMode('DESKTOP'); updateSystemState({ mode: 'DESKTOP' }); } catch { /* ignore */ }
        return;
      }
      try {
        await emergencyStop();
        updateSystemState({ is_running: false, is_paused: true, system_status: 'PAUSED' });
      } catch { /* ignore */ }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [showSettings, toggleSettings, updateSystemState]);
}

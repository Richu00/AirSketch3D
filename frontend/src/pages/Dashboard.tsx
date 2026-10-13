import { useEffect } from 'react';
import { useStore } from '../store/useStore';
import { getConfig, startTracking } from '../api/client';
import { StatusBar } from '../components/layout/StatusBar';
import { Sidebar } from '../components/layout/Sidebar';
import { CameraView } from '../components/camera/CameraView';
import { SketchViewer } from '../components/sketch/SketchViewer';
import { GesturePanel } from '../components/gesture/GesturePanel';
import { GestureGuide } from '../components/gesture/GestureGuide';
import { ActionHistory } from '../components/actions/ActionHistory';
import { ActionNotification } from '../components/actions/ActionNotification';
import { AppLauncher } from '../components/launcher/AppLauncher';
import { WebLauncher } from '../components/launcher/WebLauncher';
import { Settings } from '../components/settings/Settings';

export function Dashboard() {
  const { setSettings, updateSystemState, connectionStatus, systemState } = useStore();
  const sketchMode = systemState.mode === 'SKETCH';

  // (re)start tracking whenever the websocket (re)connects, e.g. after the backend was started later
  useEffect(() => {
    if (connectionStatus !== 'connected') return;
    getConfig().then(setSettings).catch(() => {});
    startTracking().then(() => updateSystemState({ is_running: true, system_status: 'ACTIVE' })).catch(() => {});
  }, [connectionStatus === 'connected']); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div className="h-screen flex flex-col bg-dark-bg overflow-hidden">
      <div className="fixed inset-0 data-bg opacity-40 pointer-events-none" />
      <div className="fixed inset-0 pointer-events-none ambient-glow" />
      <StatusBar />
      <div className="flex flex-1 overflow-hidden relative">
        <Sidebar />
        <div className="flex-1 flex flex-col lg:flex-row overflow-y-auto lg:overflow-hidden min-w-0">
          <main className="flex-1 flex flex-col p-3 sm:p-4 gap-3 sm:gap-4 min-w-0 min-h-0">
            <div className="flex-1 min-h-[280px] flex flex-col xl:flex-row gap-3 sm:gap-4">
              <div className="flex-1 min-h-[240px] min-w-0"><CameraView /></div>
              {sketchMode && <div className="flex-1 min-h-[300px] min-w-0"><SketchViewer /></div>}
            </div>
            <div className="lg:h-40 shrink-0"><ActionHistory /></div>
          </main>
          <aside className="lg:w-72 shrink-0 p-3 sm:p-4 lg:pl-0 flex flex-col gap-3 sm:gap-4 lg:overflow-y-auto">
            <GesturePanel />
            <GestureGuide />
          </aside>
        </div>
      </div>
      <ActionNotification />
      <AppLauncher />
      <WebLauncher />
      <Settings />
    </div>
  );
}

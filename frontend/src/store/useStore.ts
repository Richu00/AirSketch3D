import { create } from 'zustand';
import { SystemState, ActionRecord, Notification, Settings } from '../types';

// ── Default State ──────────────────────────────────────────────────────────
const defaultSystemState: SystemState = {
  hand_detected: false,
  landmarks: [],
  gesture: 'NONE',
  confidence: 0,
  fps: 0,
  mode: 'DESKTOP',
  action: '',
  system_status: 'OFFLINE',
  is_running: false,
  is_paused: false,
  gesture_state: 'IDLE',
  scroll_direction: null,
  cursor_position: null,
  launcher: { open: false, items: [], hover_index: -1, pointer: null, columns: 3 },
  sketch: { gesture: 'NONE', points: 0, closed_strokes: 0, version: 0, fist_progress: 0, erase_radius: 0.06, has_model: false, model_id: 0, ml_active: false, inspection: { inspecting: false, solid: false, rotation: [0, 0, 0], pan: [0, 0], zoom: 1 }, control_mode: 'DRAW' as const },
  sketch_strokes: [],
  sketch_model: null,
  hands: [],
};

const defaultSettings: Settings = {
  gesture: {
    confidence_threshold: 0.85,
    stabilization_frames: 8,
    cooldown_ms: 800,
    sensitivity: 1.0,
  },
  cursor: {
    sensitivity: 1.5,
    smoothing: 0.7,
    invert_x: false,
    invert_y: false,
  },
  camera: {
    camera_index: 0,
    width: 640,
    height: 480,
    mirror: true,
    show_landmarks: true,
    show_fps: true,
  },
  sketch: { extrude_height: 0.6, fist_hold_ms: 700, erase_radius: 0.06, min_points: 15, resample_points: 96, gesture_history: 5, gesture_hold_frames: 2, close_snap_distance: 0.035, min_component_area: 0.0015 },
  actions: {
    gesture_mappings: {
      INDEX_POINT: 'cursor_control',
      PINCH: 'left_click',
      FIST: 'click',
      OPEN_PALM: 'resume',
      PEACE: 'browser_mode',
      THUMBS_UP: 'app_launcher',
      THUMBS_DOWN: 'cancel',
      SWIPE_LEFT: 'previous',
      SWIPE_RIGHT: 'next',
      VERTICAL_SCROLL: 'scroll',
      PINCH_DRAG: 'drag',
      SCREENSHOT: 'screenshot',
    },
  },
};

// ── Store Interface ────────────────────────────────────────────────────────
interface AirControlStore {
  systemState: SystemState;
  connectionStatus: 'connected' | 'disconnected' | 'connecting';
  actionHistory: ActionRecord[];
  notifications: Notification[];
  settings: Settings;
  showAppLauncher: boolean;
  showWebLauncher: boolean;
  showSettings: boolean;

  // Actions
  updateSystemState: (state: Partial<SystemState>) => void;
  addAction: (record: Omit<ActionRecord, 'id' | 'timestamp'>) => void;
  addNotification: (n: Omit<Notification, 'id' | 'timestamp'>) => void;
  removeNotification: (id: string) => void;
  setConnectionStatus: (status: 'connected' | 'disconnected' | 'connecting') => void;
  setSettings: (settings: Settings) => void;
  updateSetting: <K extends keyof Settings>(section: K, values: Partial<Settings[K]>) => void;
  toggleAppLauncher: () => void;
  toggleWebLauncher: () => void;
  toggleSettings: () => void;
  clearHistory: () => void;
}

// ── Store ──────────────────────────────────────────────────────────────────
export const useStore = create<AirControlStore>((set, get) => ({
  systemState: defaultSystemState,
  connectionStatus: 'disconnected',
  actionHistory: [],
  notifications: [],
  settings: defaultSettings,
  showAppLauncher: false,
  showWebLauncher: false,
  showSettings: false,

  updateSystemState: (partial) =>
    set((s) => ({ systemState: { ...s.systemState, ...partial } })),

  addAction: (record) => {
    const newRecord: ActionRecord = {
      ...record,
      id: `${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
      timestamp: new Date(),
    };
    set((s) => ({
      actionHistory: [newRecord, ...s.actionHistory].slice(0, 50),
    }));
  },

  addNotification: (n) => {
    const id = `${Date.now()}-${Math.random().toString(36).slice(2, 7)}`;
    const notif: Notification = { ...n, id, timestamp: new Date() };
    set((s) => ({ notifications: [...s.notifications, notif].slice(-5) }));
    // Auto-remove after 2.8s
    setTimeout(() => {
      get().removeNotification(id);
    }, 2800);
  },

  removeNotification: (id) =>
    set((s) => ({ notifications: s.notifications.filter((n) => n.id !== id) })),

  setConnectionStatus: (status) => set({ connectionStatus: status }),

  setSettings: (settings) => set({ settings }),

  updateSetting: (section, values) =>
    set((s) => ({
      settings: {
        ...s.settings,
        [section]: { ...s.settings[section], ...values },
      },
    })),

  toggleAppLauncher: () =>
    set((s) => ({ showAppLauncher: !s.showAppLauncher, showWebLauncher: false })),

  toggleWebLauncher: () =>
    set((s) => ({ showWebLauncher: !s.showWebLauncher, showAppLauncher: false })),

  toggleSettings: () => set((s) => ({ showSettings: !s.showSettings })),

  clearHistory: () => set({ actionHistory: [] }),
}));

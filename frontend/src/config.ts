// Single source of truth for the backend address. The backend always runs on 127.0.0.1:8000
// (start_backend.bat). Override with VITE_API_BASE / VITE_WS_URL in frontend/.env if needed.
export const API_BASE: string = (import.meta.env.VITE_API_BASE as string | undefined) || 'http://127.0.0.1:8000';
export const WS_URL: string =
  (import.meta.env.VITE_WS_URL as string | undefined) || API_BASE.replace(/^http/, 'ws') + '/ws';

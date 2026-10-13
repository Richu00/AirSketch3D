import { useEffect, useRef, useCallback } from 'react';
import { useStore } from '../store/useStore';
import { WsMessage } from '../types';
import { WS_URL } from '../config';

const MAX_RECONNECT_DELAY = 5000;

export function useWebSocket() {
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimeout = useRef<ReturnType<typeof setTimeout> | null>(null);
  const reconnectDelay = useRef(500);
  const isMounted = useRef(true);

  const { updateSystemState, addAction, addNotification, setConnectionStatus } = useStore();

  const handleMessage = useCallback((event: MessageEvent) => {
    try {
      const msg: WsMessage = JSON.parse(event.data as string);
      if (msg.type === 'state_update') {
        updateSystemState(msg.data);
        if (msg.data.system_status === 'ACTIVE') setConnectionStatus('connected');
      } else if (msg.type === 'action_event') {
        // Overlays (launcher / web gateway) are driven by `mode` in the state stream,
        // so action events only feed the history + toast.
        const { gesture, action, confidence, mode } = msg.data;
        addAction({ gesture, action, confidence, mode });
        addNotification({ gesture, action, confidence });
      }
    } catch {
      // ignore malformed messages
    }
  }, [updateSystemState, addAction, addNotification, setConnectionStatus]);

  const connect = useCallback(() => {
    if (!isMounted.current) return;
    if (wsRef.current?.readyState === WebSocket.OPEN) return;
    setConnectionStatus('connecting');
    const ws = new WebSocket(WS_URL);
    wsRef.current = ws;

    ws.onopen = () => {
      if (!isMounted.current) return;
      setConnectionStatus('connected');
      reconnectDelay.current = 500;
      updateSystemState({ system_status: 'ACTIVE' });
    };
    ws.onmessage = handleMessage;
    ws.onclose = () => {
      if (!isMounted.current) return;
      setConnectionStatus('disconnected');
      updateSystemState({ system_status: 'OFFLINE', is_running: false });
      reconnectTimeout.current = setTimeout(() => {
        reconnectDelay.current = Math.min(reconnectDelay.current * 1.5, MAX_RECONNECT_DELAY);
        connect();
      }, reconnectDelay.current);
    };
    ws.onerror = () => { ws.close(); };
  }, [handleMessage, setConnectionStatus, updateSystemState]);

  useEffect(() => {
    isMounted.current = true;
    connect();
    return () => {
      isMounted.current = false;
      if (reconnectTimeout.current) clearTimeout(reconnectTimeout.current);
      wsRef.current?.close();
    };
  }, [connect]);

  const sendMessage = useCallback((data: unknown) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) wsRef.current.send(JSON.stringify(data));
  }, []);

  return { sendMessage };
}

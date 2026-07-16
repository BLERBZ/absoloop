import { useState, useEffect, useCallback, useRef } from 'react';
import type { Activity } from '../hooks/usePolling';

const typeColors: Record<string, string> = {
  task_started: '#58a6ff',
  task_completed: '#3fb950',
  task_failed: '#f85149',
  self_reflection: '#a371f7',
  heartbeat: '#7d8590',
  research: '#d29922',
  spawned: '#79c0ff',
  status_change: '#d2a8ff',
  error: '#f85149',
  phase_start: '#58a6ff',
  session_start: '#3fb950'
};

const typeBadgeLabels: Record<string, string> = {
  task_started: 'STARTED',
  task_completed: 'COMPLETED',
  task_failed: 'FAILED',
  self_reflection: 'REFLECTION',
  heartbeat: 'HEARTBEAT',
  research: 'RESEARCH',
  spawned: 'SPAWNED',
  status_change: 'STATUS',
  error: 'ERROR',
  phase_start: 'PHASE',
  session_start: 'SESSION'
};

interface Toast {
  id: number;
  activity: Activity;
  dismissing: boolean;
}

let nextToastId = 0;

export function ToastNotifications({ activity, darkMode }: {
  activity: Activity[];
  darkMode: boolean;
}) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const prevLengthRef = useRef(activity.length);

  const dismissToast = useCallback((id: number) => {
    setToasts(prev => prev.map(t => t.id === id ? { ...t, dismissing: true } : t));
    setTimeout(() => {
      setToasts(prev => prev.filter(t => t.id !== id));
    }, 300);
  }, []);

  // Detect new activity items
  useEffect(() => {
    const prevLen = prevLengthRef.current;
    const currentLen = activity.length;
    prevLengthRef.current = currentLen;

    if (currentLen > prevLen && prevLen > 0) {
      const newItems = activity.slice(prevLen);
      const newToasts: Toast[] = newItems.map(item => ({
        id: nextToastId++,
        activity: item,
        dismissing: false,
      }));

      setToasts(prev => {
        const combined = [...prev, ...newToasts];
        // Keep max 3 visible — dismiss oldest if over limit
        if (combined.length > 3) {
          return combined.slice(combined.length - 3);
        }
        return combined;
      });
    }
  }, [activity]);

  // Auto-dismiss after 4 seconds
  useEffect(() => {
    const activesToDismiss = toasts.filter(t => !t.dismissing);
    if (activesToDismiss.length === 0) return;

    const timers = activesToDismiss.map(t => {
      return setTimeout(() => dismissToast(t.id), 4000);
    });

    return () => timers.forEach(clearTimeout);
  }, [toasts, dismissToast]);

  if (toasts.length === 0) return null;

  const cardBg = darkMode ? '#161b22' : '#ffffff';
  const borderColor = darkMode ? '#30363d' : '#d0d7de';
  const textColor = darkMode ? '#c9d1d9' : '#1f2328';
  const mutedColor = darkMode ? '#7d8590' : '#656d76';

  return (
    <div style={{
      position: 'fixed',
      bottom: 20,
      right: 20,
      zIndex: 9999,
      display: 'flex',
      flexDirection: 'column',
      gap: 8,
      pointerEvents: 'none',
    }}>
      {toasts.map(toast => {
        const color = typeColors[toast.activity.type] || mutedColor;
        const badge = typeBadgeLabels[toast.activity.type] || toast.activity.type.replace(/_/g, ' ').toUpperCase();

        return (
          <div
            key={toast.id}
            className={toast.dismissing ? 'toast-fade-out' : 'toast-slide-in'}
            style={{
              background: cardBg,
              border: `1px solid ${borderColor}`,
              borderLeft: `3px solid ${color}`,
              borderRadius: 8,
              padding: '10px 14px',
              maxWidth: 320,
              minWidth: 240,
              boxShadow: darkMode
                ? '0 8px 24px rgba(0, 0, 0, 0.4), 0 2px 8px rgba(0, 0, 0, 0.3)'
                : '0 8px 24px rgba(0, 0, 0, 0.12), 0 2px 8px rgba(0, 0, 0, 0.08)',
              pointerEvents: 'auto',
              cursor: 'pointer',
            }}
            onClick={() => dismissToast(toast.id)}
          >
            {/* Header: badge + agent */}
            <div style={{
              display: 'flex',
              alignItems: 'center',
              gap: 6,
              marginBottom: 4,
            }}>
              <span style={{
                fontSize: 9,
                fontWeight: 700,
                color: color,
                background: `${color}18`,
                padding: '1px 6px',
                borderRadius: 3,
                letterSpacing: 0.3,
              }}>
                {badge}
              </span>
              <span style={{
                fontSize: 10,
                color: mutedColor,
                fontWeight: 500,
              }}>
                {toast.activity.agentId}
              </span>
            </div>

            {/* Message */}
            <div style={{
              fontSize: 12,
              color: textColor,
              lineHeight: 1.4,
              overflow: 'hidden',
              textOverflow: 'ellipsis',
              display: '-webkit-box',
              WebkitLineClamp: 2,
              WebkitBoxOrient: 'vertical',
            }}>
              {toast.activity.message}
            </div>
          </div>
        );
      })}
    </div>
  );
}

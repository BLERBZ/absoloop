import { useEffect } from 'react';

interface KeyboardHelpProps {
  visible: boolean;
  onClose: () => void;
  darkMode: boolean;
}

const shortcuts = [
  { key: '?', description: 'Toggle this help overlay' },
  { key: 'f', description: 'Focus search on task board' },
  { key: 'd', description: 'Toggle dark / light mode' },
  { key: '1-6', description: 'Filter kanban by phase number' },
  { key: '0', description: 'Clear phase filter (show all)' },
  { key: 'Esc', description: 'Close this overlay' },
];

export function KeyboardHelp({ visible, onClose, darkMode }: KeyboardHelpProps) {
  // Close on Escape
  useEffect(() => {
    if (!visible) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape' || e.key === '?') {
        e.preventDefault();
        onClose();
      }
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [visible, onClose]);

  if (!visible) return null;

  const bgOverlay = darkMode ? 'rgba(1, 4, 9, 0.75)' : 'rgba(0, 0, 0, 0.45)';
  const cardBg = darkMode ? '#161b22' : '#ffffff';
  const borderColor = darkMode ? '#30363d' : '#d0d7de';
  const textColor = darkMode ? '#e6edf3' : '#1f2328';
  const mutedColor = darkMode ? '#7d8590' : '#656d76';
  const kbdBg = darkMode ? '#0d1117' : '#f6f8fa';
  const kbdBorder = darkMode ? '#30363d' : '#d0d7de';

  return (
    <div
      className="modal-backdrop-fade-in"
      onClick={onClose}
      style={{
        position: 'fixed',
        inset: 0,
        background: bgOverlay,
        zIndex: 10000,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
      }}
    >
      <div
        className="modal-content-scale-in"
        onClick={e => e.stopPropagation()}
        style={{
          background: cardBg,
          border: `1px solid ${borderColor}`,
          borderRadius: 12,
          padding: '24px 28px',
          maxWidth: 400,
          width: '90vw',
          boxShadow: darkMode
            ? '0 16px 48px rgba(0, 0, 0, 0.5), 0 4px 16px rgba(0, 0, 0, 0.4)'
            : '0 16px 48px rgba(0, 0, 0, 0.15), 0 4px 16px rgba(0, 0, 0, 0.1)',
        }}
      >
        {/* Header */}
        <div style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          marginBottom: 20,
        }}>
          <h2 style={{
            margin: 0,
            fontSize: 16,
            fontWeight: 700,
            color: textColor,
          }}>
            Keyboard Shortcuts
          </h2>
          <button
            onClick={onClose}
            style={{
              background: 'none',
              border: 'none',
              color: mutedColor,
              fontSize: 18,
              cursor: 'pointer',
              padding: '2px 6px',
              borderRadius: 4,
              lineHeight: 1,
            }}
            onMouseEnter={e => (e.currentTarget.style.color = textColor)}
            onMouseLeave={e => (e.currentTarget.style.color = mutedColor)}
          >
            x
          </button>
        </div>

        {/* Shortcut List */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 0 }}>
          {shortcuts.map((s, i) => (
            <div
              key={s.key}
              style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                padding: '10px 0',
                borderBottom: i < shortcuts.length - 1 ? `1px solid ${darkMode ? '#21262d' : '#e8e8e8'}` : 'none',
              }}
            >
              <span style={{
                fontSize: 13,
                color: textColor,
                fontWeight: 500,
              }}>
                {s.description}
              </span>
              <kbd style={{
                background: kbdBg,
                border: `1px solid ${kbdBorder}`,
                borderRadius: 6,
                padding: '3px 10px',
                fontSize: 12,
                fontFamily: 'monospace',
                fontWeight: 600,
                color: textColor,
                boxShadow: darkMode
                  ? '0 1px 0 #21262d'
                  : '0 1px 0 #d0d7de',
                minWidth: 28,
                textAlign: 'center',
              }}>
                {s.key}
              </kbd>
            </div>
          ))}
        </div>

        {/* Footer hint */}
        <div style={{
          marginTop: 16,
          fontSize: 11,
          color: mutedColor,
          textAlign: 'center',
        }}>
          Press <strong style={{ color: textColor }}>?</strong> or <strong style={{ color: textColor }}>Esc</strong> to close
        </div>
      </div>
    </div>
  );
}

import { useEffect, useRef, useState } from 'react';
import type { ObjectiveHistoryEntry } from '../hooks/usePolling';

interface ObjectiveDropdownProps {
  displayedText: string;
  history: ObjectiveHistoryEntry[];
  darkMode: boolean;
  borderColor: string;
  textColor: string;
  mutedColor: string;
}

function kindLabel(kind: ObjectiveHistoryEntry['kind']): string {
  return kind === 'continuation' ? 'Continuation' : 'Original objective';
}

function formatElapsedSeconds(totalSeconds: number): string {
  const s = Math.max(0, Math.floor(totalSeconds));
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = s % 60;
  return `${h.toString().padStart(2, '0')}:${m.toString().padStart(2, '0')}:${sec.toString().padStart(2, '0')}`;
}

/** Live or frozen wall time for one history row. */
function entryElapsedSeconds(entry: ObjectiveHistoryEntry, nowSec: number): number | null {
  const started = Number(entry.startedAt);
  if (started > 0) {
    const ended = Number(entry.endedAt);
    const endSec = ended > started ? ended : nowSec;
    return Math.max(0, endSec - started);
  }
  const snap = Number(entry.elapsedSeconds);
  return snap >= 0 && Number.isFinite(snap) ? snap : null;
}

export function ObjectiveDropdown({
  displayedText,
  history,
  darkMode,
  borderColor,
  textColor,
  mutedColor,
}: ObjectiveDropdownProps) {
  const [open, setOpen] = useState(false);
  const [nowSec, setNowSec] = useState(() => Date.now() / 1000);
  const rootRef = useRef<HTMLDivElement | null>(null);
  const canOpen = history.length > 1;

  useEffect(() => {
    if (!open) return;
    const onDoc = (event: MouseEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) {
        setOpen(false);
      }
    };
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setOpen(false);
    };
    document.addEventListener('mousedown', onDoc);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('mousedown', onDoc);
      document.removeEventListener('keydown', onKey);
    };
  }, [open]);

  // Tick while open so the current loop's elapsed stays live.
  useEffect(() => {
    if (!open) return;
    const needsTick = history.some(
      e => Number(e.startedAt) > 0 && !(Number(e.endedAt) > Number(e.startedAt)),
    );
    if (!needsTick) return;
    setNowSec(Date.now() / 1000);
    const id = window.setInterval(() => setNowSec(Date.now() / 1000), 1000);
    return () => window.clearInterval(id);
  }, [open, history]);

  // Newest first in the menu so the active note sits at the top.
  const menuItems = [...history].reverse();
  const menuBg = darkMode ? '#161b22' : '#ffffff';
  const menuHover = darkMode ? '#21262d' : '#f6f8fa';
  const activeText = displayedText.trim();

  return (
    <div
      ref={rootRef}
      style={{
        position: 'relative',
        display: 'flex',
        alignItems: 'center',
        gap: 4,
        minWidth: 0,
        flex: 1,
      }}
    >
      <button
        type="button"
        disabled={!canOpen}
        aria-haspopup={canOpen ? 'menu' : undefined}
        aria-expanded={canOpen ? open : undefined}
        title={canOpen
          ? (open ? 'Hide objective history' : 'View objective & continuation notes')
          : activeText}
        onClick={() => {
          if (!canOpen) return;
          setOpen(value => !value);
        }}
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 6,
          minWidth: 0,
          flex: 1,
          background: open ? (darkMode ? '#21262d' : '#e1e4e8') : 'none',
          border: 'none',
          borderRadius: 6,
          padding: '2px 4px',
          margin: 0,
          cursor: canOpen ? 'pointer' : 'default',
          color: mutedColor,
          textAlign: 'left',
        }}
        onMouseEnter={e => {
          if (canOpen) {
            e.currentTarget.style.background = darkMode ? '#21262d' : '#e1e4e8';
            e.currentTarget.style.color = textColor;
          }
        }}
        onMouseLeave={e => {
          if (!open) {
            e.currentTarget.style.background = 'none';
            e.currentTarget.style.color = mutedColor;
          }
        }}
      >
        <span
          style={{
            fontSize: 12,
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            whiteSpace: 'nowrap',
            minWidth: 0,
            flex: 1,
          }}
        >
          {activeText}
        </span>
        {canOpen && (
          <svg
            width="10"
            height="10"
            viewBox="0 0 12 12"
            aria-hidden="true"
            style={{
              display: 'block',
              flexShrink: 0,
              transform: open ? 'rotate(180deg)' : 'none',
              transition: 'transform 0.15s ease',
            }}
          >
            <path
              d="M2.5 4.5 L6 8 L9.5 4.5"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.6"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
        )}
      </button>

      {open && canOpen && (
        <div
          role="menu"
          style={{
            position: 'absolute',
            top: 'calc(100% + 6px)',
            left: 0,
            right: 0,
            minWidth: 280,
            maxWidth: 'min(720px, 70vw)',
            maxHeight: 'min(320px, 50vh)',
            overflowY: 'auto',
            zIndex: 50,
            background: menuBg,
            border: `1px solid ${borderColor}`,
            borderRadius: 8,
            boxShadow: darkMode
              ? '0 12px 28px rgba(0,0,0,0.45)'
              : '0 12px 28px rgba(31,35,40,0.18)',
            padding: 4,
            display: 'flex',
            flexDirection: 'column',
            gap: 2,
          }}
        >
          {menuItems.map((entry, index) => {
            const isActive = entry.text.trim() === activeText;
            const key = `${entry.kind}-${entry.loopId || 'none'}-${index}`;
            const elapsed = entryElapsedSeconds(entry, nowSec);
            return (
              <div
                key={key}
                role="menuitem"
                style={{
                  borderRadius: 6,
                  padding: '8px 10px',
                  background: isActive ? menuHover : 'none',
                  border: isActive
                    ? `1px solid ${darkMode ? '#30363d' : '#d0d7de'}`
                    : '1px solid transparent',
                }}
              >
                <div style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 8,
                  marginBottom: 3,
                  flexWrap: 'wrap',
                }}>
                  <span style={{
                    fontSize: 10,
                    fontWeight: 700,
                    letterSpacing: '0.06em',
                    textTransform: 'uppercase',
                    color: entry.kind === 'continuation'
                      ? (darkMode ? '#e3b341' : '#9a6700')
                      : mutedColor,
                  }}>
                    {kindLabel(entry.kind)}
                    {isActive ? ' · current' : ''}
                  </span>
                  {entry.loopId && (
                    <span style={{
                      fontSize: 10,
                      fontFamily: 'monospace',
                      color: mutedColor,
                      overflow: 'hidden',
                      textOverflow: 'ellipsis',
                      whiteSpace: 'nowrap',
                    }}>
                      {entry.loopId}
                    </span>
                  )}
                  {elapsed != null && (
                    <span
                      title="Total time elapsed for this loop"
                      style={{
                        fontSize: 10,
                        fontFamily: 'monospace',
                        fontVariantNumeric: 'tabular-nums',
                        fontWeight: 600,
                        color: isActive
                          ? (darkMode ? '#58a6ff' : '#0969da')
                          : mutedColor,
                        whiteSpace: 'nowrap',
                        flexShrink: 0,
                      }}
                    >
                      {formatElapsedSeconds(elapsed)}
                    </span>
                  )}
                </div>
                <div style={{
                  fontSize: 12,
                  color: textColor,
                  lineHeight: 1.45,
                  whiteSpace: 'pre-wrap',
                  wordBreak: 'break-word',
                }}>
                  {entry.text}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

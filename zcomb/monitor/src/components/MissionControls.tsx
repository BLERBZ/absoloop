import { useEffect, useRef, useState, type CSSProperties } from 'react';
import type { Metrics } from '../hooks/usePolling';

export type ActionName = 'approve' | 'resume' | 'extend' | 'report' | 'abort';

interface MissionControlsProps {
  metrics?: Metrics | null;
  darkMode: boolean;
  borderColor: string;
  textColor: string;
  mutedColor: string;
  /** True while the objective row is open for an extend continuation note. */
  extendMode?: boolean;
  /** Open the highlighted extend-objective editor (does not launch yet). */
  onRequestExtend?: () => void;
  /** Called when Resume/Extend starts a new/continued run so Kanban can reset. */
  onRunRestarting?: () => void;
}

export async function triggerAction(
  action: ActionName,
  body?: { note?: string },
): Promise<{ ok: boolean; message: string }> {
  const res = await fetch(`/api/actions/${action}`, {
    method: 'POST',
    headers: body ? { 'Content-Type': 'application/json' } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  });
  let payload: { ok?: boolean; message?: string; error?: string; detached?: boolean } = {};
  try {
    payload = await res.json();
  } catch {
    payload = {};
  }
  if (!res.ok || payload.ok === false) {
    return {
      ok: false,
      message: payload.error || payload.message || `Failed to ${action} (HTTP ${res.status})`,
    };
  }
  return {
    ok: true,
    message: payload.message || (payload.detached ? `Started ${action}` : `${action} done`),
  };
}

export function MissionControls({
  metrics,
  darkMode,
  borderColor,
  textColor,
  mutedColor,
  extendMode = false,
  onRequestExtend,
  onRunRestarting,
}: MissionControlsProps) {
  const [busy, setBusy] = useState<ActionName | null>(null);
  const [flash, setFlash] = useState<{ ok: boolean; text: string } | null>(null);
  const [menuOpen, setMenuOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement | null>(null);

  const status = String(metrics?.status || '').toUpperCase();
  const live = Boolean(metrics?.live);
  const awaitingRun = Boolean(metrics?.awaitingRun);
  const hasMission = Boolean(metrics?.missionId || status) && status !== 'IDLE';
  const runningLike = live
    || ['EXECUTING', 'FINAL_REVIEW', 'RUNNING', 'STARTING'].includes(status);

  const approveEnabled = !busy && hasMission && status === 'AWAITING_APPROVAL';
  const resumeEnabled = !busy && hasMission && !live && !awaitingRun
    && status !== 'AWAITING_APPROVAL' && status !== 'STARTING' && !extendMode;
  const extendEnabled = !busy && hasMission && !live && !awaitingRun
    && status !== 'AWAITING_APPROVAL' && status !== 'STARTING';
  const reportEnabled = !busy && hasMission && !awaitingRun;
  const abortEnabled = !busy && hasMission && runningLike && !awaitingRun;

  useEffect(() => {
    if (!menuOpen) return;
    const onDoc = (event: MouseEvent) => {
      if (!menuRef.current?.contains(event.target as Node)) {
        setMenuOpen(false);
      }
    };
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setMenuOpen(false);
    };
    document.addEventListener('mousedown', onDoc);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('mousedown', onDoc);
      document.removeEventListener('keydown', onKey);
    };
  }, [menuOpen]);

  const run = async (action: Exclude<ActionName, 'extend'>) => {
    if (action === 'approve') {
      const confirmed = window.confirm(
        'Approve this mission and mark it COMPLETED? Delivery will run next.',
      );
      if (!confirmed) return;
    }
    if (action === 'abort') {
      const confirmed = window.confirm(
        live
          ? 'Abort the live loop now? The runner and its agent children will be stopped; you can resume later from the last checkpoint.'
          : 'Mark this mission STOPPED? Use this to clear a stuck EXECUTING status.',
      );
      if (!confirmed) return;
    }

    setBusy(action);
    setFlash(null);
    setMenuOpen(false);
    try {
      const result = await triggerAction(action);
      setFlash({ ok: result.ok, text: result.message });
      if (action === 'resume' && result.ok) {
        onRunRestarting?.();
      }
    } catch (err: any) {
      setFlash({ ok: false, text: err?.message || `Failed to ${action}` });
    } finally {
      setBusy(null);
      window.setTimeout(() => setFlash(null), 4000);
    }
  };

  const requestExtend = () => {
    if (!extendEnabled) return;
    setMenuOpen(false);
    setFlash(null);
    onRequestExtend?.();
  };

  const btnBase: CSSProperties = {
    borderRadius: 6,
    padding: '4px 11px',
    fontSize: 12,
    fontWeight: 600,
    letterSpacing: '0.01em',
    cursor: 'pointer',
    transition: 'background 0.15s, opacity 0.15s, border-color 0.15s',
    lineHeight: 1.3,
    whiteSpace: 'nowrap',
  };

  const outlineBtn = (enabled: boolean): CSSProperties => ({
    ...btnBase,
    background: 'none',
    border: `1px solid ${borderColor}`,
    color: enabled ? textColor : mutedColor,
    opacity: enabled ? 1 : 0.45,
    cursor: enabled ? 'pointer' : 'not-allowed',
  });

  const approveBtn = (enabled: boolean): CSSProperties => ({
    ...btnBase,
    background: enabled ? '#238636' : 'transparent',
    border: `1px solid ${enabled ? '#238636' : borderColor}`,
    color: enabled ? '#fff' : mutedColor,
    opacity: enabled ? 1 : 0.45,
    cursor: enabled ? 'pointer' : 'not-allowed',
  });

  const abortBtn = (enabled: boolean): CSSProperties => ({
    ...btnBase,
    background: enabled ? (darkMode ? '#3d1215' : '#ffebe9') : 'transparent',
    border: `1px solid ${enabled ? '#da3633' : borderColor}`,
    color: enabled ? '#f85149' : mutedColor,
    opacity: enabled ? 1 : 0.45,
    cursor: enabled ? 'pointer' : 'not-allowed',
  });

  const menuBg = darkMode ? '#161b22' : '#ffffff';
  const menuHover = darkMode ? '#21262d' : '#eaeef2';
  const splitEnabled = resumeEnabled || extendEnabled;

  return (
    <div style={{
      display: 'flex',
      alignItems: 'center',
      gap: 8,
      borderLeft: `1px solid ${borderColor}`,
      paddingLeft: 12,
      marginLeft: 4,
      flexWrap: 'wrap',
    }}>
      <span style={{
        fontSize: 10,
        fontWeight: 700,
        letterSpacing: '0.08em',
        textTransform: 'uppercase',
        color: mutedColor,
        marginRight: 2,
      }}>
        Controls
      </span>

      <button
        type="button"
        disabled={!approveEnabled}
        title={
          status === 'AWAITING_APPROVAL'
            ? 'Approve mission (absoloop approve)'
            : 'Available when status is AWAITING_APPROVAL'
        }
        onClick={() => run('approve')}
        style={approveBtn(approveEnabled)}
        onMouseEnter={e => {
          if (approveEnabled) e.currentTarget.style.background = '#2ea043';
        }}
        onMouseLeave={e => {
          if (approveEnabled) e.currentTarget.style.background = '#238636';
        }}
      >
        {busy === 'approve' ? '…' : 'Approve'}
      </button>

      {/* Split Resume / Extend control */}
      <div ref={menuRef} style={{ position: 'relative', display: 'flex', alignItems: 'stretch' }}>
        <button
          type="button"
          disabled={!resumeEnabled}
          title={
            extendMode
              ? 'Finish or cancel the extend objective below'
              : live
                ? 'Loop is already running'
                : status === 'AWAITING_APPROVAL'
                  ? 'Decide the gate first (Approve), then resume'
                  : 'Continue the loop (absoloop resume)'
          }
          onClick={() => run('resume')}
          style={{
            ...outlineBtn(resumeEnabled),
            borderTopRightRadius: 0,
            borderBottomRightRadius: 0,
            borderRight: 'none',
            minWidth: 72,
          }}
          onMouseEnter={e => {
            if (resumeEnabled) {
              e.currentTarget.style.background = darkMode ? '#21262d' : '#e1e4e8';
            }
          }}
          onMouseLeave={e => {
            e.currentTarget.style.background = 'none';
          }}
        >
          {busy === 'resume' ? '…' : 'Resume'}
        </button>
        <button
          type="button"
          disabled={!splitEnabled}
          aria-haspopup="menu"
          aria-expanded={menuOpen}
          title="Choose Resume or Extend"
          onClick={() => {
            if (!splitEnabled) return;
            setMenuOpen(open => !open);
          }}
          style={{
            ...outlineBtn(splitEnabled),
            borderTopLeftRadius: 0,
            borderBottomLeftRadius: 0,
            paddingLeft: 7,
            paddingRight: 7,
            background: menuOpen || extendMode
              ? (darkMode ? '#21262d' : '#e1e4e8')
              : 'none',
          }}
          onMouseEnter={e => {
            if (splitEnabled) {
              e.currentTarget.style.background = darkMode ? '#21262d' : '#e1e4e8';
            }
          }}
          onMouseLeave={e => {
            if (!menuOpen && !extendMode) e.currentTarget.style.background = 'none';
          }}
        >
          <svg width="10" height="10" viewBox="0 0 12 12" aria-hidden="true"
               style={{ display: 'block' }}>
            <path
              d="M2.5 4.5 L6 8 L9.5 4.5"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.6"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
        </button>

        {menuOpen && (
          <div
            role="menu"
            style={{
              position: 'absolute',
              top: 'calc(100% + 4px)',
              left: 0,
              minWidth: 220,
              zIndex: 40,
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
            <button
              type="button"
              role="menuitem"
              disabled={!resumeEnabled}
              onClick={() => run('resume')}
              style={{
                textAlign: 'left',
                background: 'none',
                border: 'none',
                borderRadius: 6,
                padding: '8px 10px',
                cursor: resumeEnabled ? 'pointer' : 'not-allowed',
                opacity: resumeEnabled ? 1 : 0.45,
                color: textColor,
              }}
              onMouseEnter={e => {
                if (resumeEnabled) e.currentTarget.style.background = menuHover;
              }}
              onMouseLeave={e => {
                e.currentTarget.style.background = 'none';
              }}
            >
              <div style={{ fontSize: 12, fontWeight: 700 }}>Resume</div>
              <div style={{ fontSize: 11, color: mutedColor, marginTop: 2 }}>
                Continue from the last checkpoint
              </div>
            </button>
            <button
              type="button"
              role="menuitem"
              disabled={!extendEnabled}
              onClick={requestExtend}
              style={{
                textAlign: 'left',
                background: extendMode ? menuHover : 'none',
                border: 'none',
                borderRadius: 6,
                padding: '8px 10px',
                cursor: extendEnabled ? 'pointer' : 'not-allowed',
                opacity: extendEnabled ? 1 : 0.45,
                color: textColor,
              }}
              onMouseEnter={e => {
                if (extendEnabled) e.currentTarget.style.background = menuHover;
              }}
              onMouseLeave={e => {
                if (!extendMode) e.currentTarget.style.background = 'none';
              }}
            >
              <div style={{ fontSize: 12, fontWeight: 700 }}>Extend</div>
              <div style={{ fontSize: 11, color: mutedColor, marginTop: 2 }}>
                Fresh budgets — set continuation objective
              </div>
            </button>
          </div>
        )}
      </div>

      <button
        type="button"
        disabled={!reportEnabled}
        title="Open mission report (absoloop report)"
        onClick={() => run('report')}
        style={outlineBtn(reportEnabled)}
        onMouseEnter={e => {
          if (reportEnabled) {
            e.currentTarget.style.background = darkMode ? '#21262d' : '#e1e4e8';
          }
        }}
        onMouseLeave={e => {
          e.currentTarget.style.background = 'none';
        }}
      >
        {busy === 'report' ? '…' : 'Report'}
      </button>

      <button
        type="button"
        disabled={!abortEnabled}
        title={
          live
            ? 'Stop the live loop now (absoloop abort)'
            : runningLike
              ? 'Clear stuck run state (absoloop abort)'
              : 'Available while the loop is running'
        }
        onClick={() => run('abort')}
        style={abortBtn(abortEnabled)}
        onMouseEnter={e => {
          if (abortEnabled) {
            e.currentTarget.style.background = darkMode ? '#67060c' : '#ffd7d5';
          }
        }}
        onMouseLeave={e => {
          if (abortEnabled) {
            e.currentTarget.style.background = darkMode ? '#3d1215' : '#ffebe9';
          }
        }}
      >
        {busy === 'abort' ? '…' : 'Abort'}
      </button>

      {flash && (
        <span
          style={{
            fontSize: 11,
            color: flash.ok ? '#3fb950' : '#f85149',
            maxWidth: 220,
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            whiteSpace: 'nowrap',
          }}
          title={flash.text}
        >
          {flash.text}
        </span>
      )}
    </div>
  );
}

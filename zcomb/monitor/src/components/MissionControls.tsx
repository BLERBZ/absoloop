import { useState, type CSSProperties } from 'react';
import type { Metrics } from '../hooks/usePolling';

type ActionName = 'approve' | 'resume' | 'report';

interface MissionControlsProps {
  metrics?: Metrics | null;
  darkMode: boolean;
  borderColor: string;
  textColor: string;
  mutedColor: string;
}

async function triggerAction(action: ActionName): Promise<{ ok: boolean; message: string }> {
  const res = await fetch(`/api/actions/${action}`, { method: 'POST' });
  let body: { ok?: boolean; message?: string; error?: string; detached?: boolean } = {};
  try {
    body = await res.json();
  } catch {
    body = {};
  }
  if (!res.ok || body.ok === false) {
    return {
      ok: false,
      message: body.error || body.message || `Failed to ${action} (HTTP ${res.status})`,
    };
  }
  return {
    ok: true,
    message: body.message || (body.detached ? `Started ${action}` : `${action} done`),
  };
}

export function MissionControls({
  metrics,
  darkMode,
  borderColor,
  textColor,
  mutedColor,
}: MissionControlsProps) {
  const [busy, setBusy] = useState<ActionName | null>(null);
  const [flash, setFlash] = useState<{ ok: boolean; text: string } | null>(null);

  const status = String(metrics?.status || '').toUpperCase();
  const live = Boolean(metrics?.live);
  const hasMission = Boolean(metrics?.missionId || status);

  const approveEnabled = !busy && hasMission && status === 'AWAITING_APPROVAL';
  const resumeEnabled = !busy && hasMission && !live && status !== 'AWAITING_APPROVAL';
  const reportEnabled = !busy && hasMission;

  const run = async (action: ActionName) => {
    if (action === 'approve') {
      const confirmed = window.confirm(
        'Approve this mission and mark it COMPLETED? Delivery will run next.',
      );
      if (!confirmed) return;
    }

    setBusy(action);
    setFlash(null);
    try {
      const result = await triggerAction(action);
      setFlash({ ok: result.ok, text: result.message });
    } catch (err: any) {
      setFlash({ ok: false, text: err?.message || `Failed to ${action}` });
    } finally {
      setBusy(null);
      window.setTimeout(() => setFlash(null), 4000);
    }
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

      <button
        type="button"
        disabled={!resumeEnabled}
        title={
          live
            ? 'Loop is already running'
            : status === 'AWAITING_APPROVAL'
              ? 'Decide the gate first (Approve), then resume'
              : status === 'COMPLETED'
                ? 'Start a follow-on run (absoloop resume --extend)'
                : 'Continue the loop (absoloop resume)'
        }
        onClick={() => run('resume')}
        style={outlineBtn(resumeEnabled)}
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

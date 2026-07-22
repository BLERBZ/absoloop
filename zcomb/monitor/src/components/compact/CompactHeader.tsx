import { useState, type CSSProperties, type ReactNode } from 'react';
import type { Metrics } from '../../hooks/usePolling';
import { triggerAction, type ActionName } from '../MissionControls';
import { SettingsMenu } from '../SettingsMenu';
import { ViewModeToggle } from './ViewModeToggle';
import type { CompactTheme, RunActionState, RunStateInfo } from './runState';
import { ACCENT } from './runState';

function ProgressRing({ pct, size, color, track }: {
  pct: number;
  size: number;
  color: string;
  track: string;
}) {
  const stroke = 3;
  const r = (size - stroke) / 2;
  const c = 2 * Math.PI * r;
  return (
    <svg
      width={size}
      height={size}
      viewBox={`0 0 ${size} ${size}`}
      style={{ transform: 'rotate(-90deg)', flexShrink: 0 }}
      aria-hidden="true"
    >
      <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke={track} strokeWidth={stroke} />
      <circle
        cx={size / 2}
        cy={size / 2}
        r={r}
        fill="none"
        stroke={color}
        strokeWidth={stroke}
        strokeDasharray={c}
        strokeDashoffset={c - (Math.min(100, Math.max(0, pct)) / 100) * c}
        strokeLinecap="round"
        style={{ transition: 'stroke-dashoffset 0.5s ease' }}
      />
    </svg>
  );
}

function ActionButton({ label, icon, tone, enabled, busy, title, onClick, theme }: {
  label: string;
  icon: ReactNode;
  tone: 'primary' | 'neutral' | 'danger';
  enabled: boolean;
  busy: boolean;
  title: string;
  onClick: () => void;
  theme: CompactTheme;
}) {
  const base: CSSProperties = {
    display: 'inline-flex',
    alignItems: 'center',
    gap: 5,
    height: 32,
    padding: '0 10px',
    borderRadius: 8,
    fontSize: 12,
    fontWeight: 600,
    letterSpacing: '0.01em',
    whiteSpace: 'nowrap',
    cursor: enabled ? 'pointer' : 'not-allowed',
    opacity: enabled ? 1 : 0.5,
    transition: 'background 0.15s ease, border-color 0.15s ease',
    flexShrink: 0,
  };
  let style: CSSProperties;
  if (tone === 'primary') {
    style = {
      ...base,
      background: enabled ? '#238636' : 'transparent',
      border: `1px solid ${enabled ? '#238636' : theme.border}`,
      color: enabled ? '#ffffff' : theme.muted,
    };
  } else if (tone === 'danger') {
    style = {
      ...base,
      background: enabled ? '#f851491a' : 'transparent',
      border: `1px solid ${enabled ? '#da3633' : theme.border}`,
      color: enabled ? ACCENT.red : theme.muted,
    };
  } else {
    style = {
      ...base,
      background: 'transparent',
      border: `1px solid ${theme.border}`,
      color: enabled ? theme.text : theme.muted,
    };
  }
  return (
    <button
      type="button"
      className={`compact-action compact-action-${tone}`}
      disabled={!enabled}
      title={title}
      aria-label={title}
      onClick={onClick}
      style={style}
    >
      {busy ? (
        <span aria-hidden="true" style={{ fontVariantNumeric: 'tabular-nums' }}>…</span>
      ) : icon}
      <span>{label}</span>
    </button>
  );
}

const ICONS = {
  approve: (
    <svg width="13" height="13" viewBox="0 0 16 16" aria-hidden="true">
      <path d="M3 8.5 L6.5 12 L13 4.5" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  ),
  resume: (
    <svg width="12" height="12" viewBox="0 0 16 16" aria-hidden="true">
      <path d="M4.5 3 L12.5 8 L4.5 13 Z" fill="currentColor" />
    </svg>
  ),
  report: (
    <svg width="13" height="13" viewBox="0 0 16 16" aria-hidden="true">
      <path d="M4 2.5 H10.5 L13 5 V13.5 H4 Z" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinejoin="round" />
      <path d="M6 8 H11 M6 10.5 H11" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" />
    </svg>
  ),
  abort: (
    <svg width="12" height="12" viewBox="0 0 16 16" aria-hidden="true">
      <rect x="3.5" y="3.5" width="9" height="9" rx="1.5" fill="currentColor" />
    </svg>
  ),
};

/**
 * 48px compact command-center header: brand + run state, consolidated
 * progress cluster, and the contextual action zone. The header body doubles
 * as the drag handle (interactive elements are excluded by the drag hook).
 */
export function CompactHeader({
  theme,
  darkMode,
  metrics,
  runState,
  actions,
  progressPct,
  doneTasks,
  totalTasks,
  elapsed,
  narrow,
  onDragStart,
  onToggleView,
  onThemeChange,
  onRequestExtend,
  onRunRestarting,
  onRefresh,
}: {
  theme: CompactTheme;
  darkMode: boolean;
  metrics?: Metrics | null;
  runState: RunStateInfo;
  actions: RunActionState;
  progressPct: number;
  doneTasks: number;
  totalTasks: number;
  elapsed: string;
  /** Below ~900px the action labels shrink to keep 32px hit targets. */
  narrow: boolean;
  onDragStart: (e: React.PointerEvent) => void;
  onToggleView: () => void;
  onThemeChange: (dark: boolean) => void;
  onRequestExtend: () => void;
  onRunRestarting: (note?: string) => void;
  onRefresh: () => void;
}) {
  const [busy, setBusy] = useState<ActionName | null>(null);
  const [flash, setFlash] = useState<{ ok: boolean; text: string } | null>(null);

  const run = async (action: Exclude<ActionName, 'extend'>) => {
    if (action === 'approve') {
      const confirmed = window.confirm(
        'Approve this mission and mark it COMPLETED? Delivery will run next.',
      );
      if (!confirmed) return;
    }
    if (action === 'abort') {
      const confirmed = window.confirm(
        actions.live
          ? 'Abort the live loop now? The runner and its agent children will be stopped; you can resume later from the last checkpoint.'
          : 'Mark this mission STOPPED? Use this to clear a stuck EXECUTING status.',
      );
      if (!confirmed) return;
    }
    setBusy(action);
    setFlash(null);
    try {
      const result = await triggerAction(action);
      setFlash({ ok: result.ok, text: result.message });
      if (action === 'resume' && result.ok) onRunRestarting();
      if (action === 'approve' || action === 'abort' || action === 'report') onRefresh();
    } catch (err: any) {
      setFlash({ ok: false, text: err?.message || `Failed to ${action}` });
      onRefresh();
    } finally {
      setBusy(null);
      window.setTimeout(() => setFlash(null), 4000);
    }
  };

  const engine = String(metrics?.settings?.activeEngine || metrics?.engine || '').trim();
  const model = String(metrics?.settings?.activeModel || metrics?.model || '').trim();
  const clusterTitle = [
    `${doneTasks} of ${totalTasks} tasks complete`,
    `Elapsed ${elapsed}`,
    engine || model ? `Engine ${engine || '—'} · ${model || '—'}` : '',
  ].filter(Boolean).join('\n');

  const progressColor = progressPct === 100 ? ACCENT.green : ACCENT.blue;

  // Contextual primary: Approve at the gate; Resume/Extend when idle;
  // nothing extra while executing (Abort is the stop control).
  const showApprove = actions.atHumanGate;
  const showResume = !showApprove && (actions.resumeEnabled || actions.extendEnabled)
    && !actions.runningLike;
  const primaryIsExtend = actions.preferExtend && actions.extendEnabled;

  return (
    <div
      className="compact-drag-region"
      onPointerDown={onDragStart}
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: 10,
        height: 48,
        padding: '0 8px 0 12px',
        background: theme.headerBg,
        borderBottom: `1px solid ${theme.border}`,
        borderRadius: '16px 16px 0 0',
        flexShrink: 0,
        cursor: 'grab',
        touchAction: 'none',
        position: 'relative',
      }}
    >
      {/* Left zone — brand + run state */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, minWidth: 0, flexShrink: 1 }}>
        <img
          src="/absoloop-logo-mark.png"
          alt=""
          height={22}
          style={{ height: 22, width: 'auto', objectFit: 'contain', display: 'block', flexShrink: 0 }}
          draggable={false}
        />
        {!narrow && (
          <span style={{
            fontSize: 15,
            fontWeight: 700,
            color: theme.text,
            letterSpacing: '-0.02em',
            whiteSpace: 'nowrap',
          }}>
            ZComb
          </span>
        )}
        <span
          className={runState.tone === 'active' ? 'compact-state-pill-active' : undefined}
          role="status"
          aria-label={`Run state: ${runState.label}`}
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: 6,
            fontSize: 11,
            fontWeight: 700,
            letterSpacing: '0.05em',
            textTransform: 'uppercase',
            color: runState.color,
            background: `${runState.color}16`,
            border: `1px solid ${runState.color}3a`,
            borderRadius: 7,
            padding: '3px 8px',
            whiteSpace: 'nowrap',
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            minWidth: 0,
          }}
        >
          <span
            aria-hidden="true"
            className={runState.tone === 'active' ? 'compact-pulse-dot' : undefined}
            style={{
              width: 6,
              height: 6,
              borderRadius: '50%',
              background: runState.color,
              flexShrink: 0,
            }}
          />
          <span style={{ overflow: 'hidden', textOverflow: 'ellipsis' }}>{runState.label}</span>
        </span>
      </div>

      {/* Center/right — consolidated live execution cluster */}
      <div
        title={clusterTitle}
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 8,
          marginLeft: 'auto',
          flexShrink: 0,
        }}
      >
        <ProgressRing pct={progressPct} size={28} color={progressColor} track={theme.track} />
        <span style={{
          fontSize: 18,
          fontWeight: 800,
          color: progressColor,
          fontVariantNumeric: 'tabular-nums',
          lineHeight: 1,
          minWidth: 44,
          textAlign: 'right',
        }}>
          {progressPct}%
        </span>
        <span style={{
          display: 'flex',
          flexDirection: 'column',
          gap: 1,
          lineHeight: 1.2,
        }}>
          <span style={{
            fontSize: 11,
            fontWeight: 600,
            color: theme.text,
            fontVariantNumeric: 'tabular-nums',
            whiteSpace: 'nowrap',
          }}>
            {doneTasks} / {totalTasks}
          </span>
          <span style={{
            fontSize: 11,
            fontFamily: 'ui-monospace, monospace',
            color: theme.muted,
            fontVariantNumeric: 'tabular-nums',
            whiteSpace: 'nowrap',
            minWidth: 62,
          }}>
            {elapsed}
          </span>
        </span>
      </div>

      {/* Action zone */}
      <div style={{
        display: 'flex',
        alignItems: 'center',
        gap: 6,
        flexShrink: 0,
        borderLeft: `1px solid ${theme.borderSoft}`,
        paddingLeft: 8,
      }}>
        {showApprove && (
          <ActionButton
            label="Approve"
            icon={ICONS.approve}
            tone="primary"
            enabled={actions.approveEnabled && busy == null}
            busy={busy === 'approve'}
            title="Approve mission (absoloop approve)"
            onClick={() => void run('approve')}
            theme={theme}
          />
        )}
        {showResume && (
          <ActionButton
            label={primaryIsExtend ? 'Extend' : 'Resume'}
            icon={ICONS.resume}
            tone="primary"
            enabled={busy == null}
            busy={busy === 'resume'}
            title={primaryIsExtend
              ? 'Start a follow-on run with fresh budgets (absoloop extend)'
              : 'Continue the loop from the last checkpoint (absoloop resume)'}
            onClick={() => {
              if (primaryIsExtend) onRequestExtend();
              else void run('resume');
            }}
            theme={theme}
          />
        )}
        <ActionButton
          label={narrow ? '' : 'Report'}
          icon={ICONS.report}
          tone="neutral"
          enabled={actions.reportEnabled && busy == null}
          busy={busy === 'report'}
          title={actions.reportEnabled
            ? 'Open mission report (absoloop report)'
            : 'Report is available once a mission exists'}
          onClick={() => void run('report')}
          theme={theme}
        />
        <ActionButton
          label={narrow ? '' : 'Abort'}
          icon={ICONS.abort}
          tone="danger"
          enabled={actions.abortEnabled && busy == null}
          busy={busy === 'abort'}
          title={actions.abortEnabled
            ? 'Stop the live loop now (absoloop abort)'
            : 'Abort is available while the loop is running'}
          onClick={() => void run('abort')}
          theme={theme}
        />
        <ViewModeToggle
          mode="compact"
          onToggle={onToggleView}
          darkMode={darkMode}
          borderColor={theme.border}
          textColor={theme.text}
        />
        <SettingsMenu
          metrics={metrics}
          darkMode={darkMode}
          borderColor={theme.border}
          textColor={theme.text}
          mutedColor={theme.muted}
          onThemeChange={onThemeChange}
          onRefresh={onRefresh}
        />
      </div>

      {/* Action result flash — announced politely, floats under the header */}
      <div aria-live="polite" style={{ position: 'absolute', top: '100%', right: 12, zIndex: 30 }}>
        {flash && (
          <span style={{
            display: 'inline-block',
            marginTop: 6,
            fontSize: 11,
            fontWeight: 600,
            color: flash.ok ? ACCENT.green : ACCENT.red,
            background: theme.cardBg,
            border: `1px solid ${flash.ok ? `${ACCENT.green}44` : `${ACCENT.red}44`}`,
            borderRadius: 7,
            padding: '4px 9px',
            maxWidth: 320,
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            whiteSpace: 'nowrap',
            boxShadow: '0 6px 16px rgba(0,0,0,0.3)',
          }} title={flash.text}>
            {flash.text}
          </span>
        )}
      </div>
    </div>
  );
}

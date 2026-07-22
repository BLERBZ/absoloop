import type { Agent, Task } from '../../hooks/usePolling';
import type { CompactTheme, PhaseSnapshot, RunStateInfo } from './runState';
import { ACCENT } from './runState';

function MetricPill({ theme, value, label, color, tinted }: {
  theme: CompactTheme;
  value: number;
  label: string;
  color: string;
  tinted: boolean;
}) {
  return (
    <div
      title={`${value} ${label.toLowerCase()}`}
      style={{
        display: 'flex',
        alignItems: 'baseline',
        gap: 5,
        padding: '5px 9px',
        borderRadius: 8,
        background: tinted ? `${color}10` : theme.cardBg,
        border: `1px solid ${tinted ? `${color}30` : theme.borderSoft}`,
        whiteSpace: 'nowrap',
      }}
    >
      <span style={{
        fontSize: 15,
        fontWeight: 800,
        color,
        fontVariantNumeric: 'tabular-nums',
        lineHeight: 1,
        minWidth: 12,
        textAlign: 'right',
      }}>
        {value}
      </span>
      <span style={{
        fontSize: 11,
        fontWeight: 600,
        color: theme.muted,
        letterSpacing: '0.03em',
        textTransform: 'uppercase',
      }}>
        {label}
      </span>
    </div>
  );
}

const STAGE_SHORT: Record<string, string> = {
  'Scaffold': 'Scaf',
  'Execute': 'Exec',
  'Integrity': 'Integ',
  'Critic': 'Critic',
  'Human Gate': 'Gate',
  'Deliver': 'Deliv',
};

/** Bottom rail — compact run metrics + the six-stage workflow pipeline. */
export function CompactFooter({ theme, tasks, agents, phases, runState, width }: {
  theme: CompactTheme;
  tasks: Task[];
  agents: Agent[];
  phases: PhaseSnapshot;
  runState: RunStateInfo;
  width: number;
}) {
  const total = tasks.length;
  const done = tasks.filter(t => t.status === 'done').length;
  const active = tasks.filter(t => t.status === 'in_progress').length;
  const failed = tasks.filter(t => t.status === 'failed').length;

  // Width budget: metrics ~340px; decide stage label density from the rest.
  const stageBudget = width - 360;
  const perStage = phases.phases.length > 0 ? stageBudget / phases.phases.length : 0;
  const labelMode: 'full' | 'short' | 'iconOnly' =
    perStage >= 124 ? 'full' : perStage >= 88 ? 'short' : 'iconOnly';
  const failureStage = runState.tone === 'danger';

  return (
    <div style={{
      display: 'flex',
      alignItems: 'center',
      gap: 12,
      padding: '8px 12px',
      background: theme.headerBg,
      borderTop: `1px solid ${theme.border}`,
      borderRadius: '0 0 16px 16px',
      flexShrink: 0,
      minHeight: 58,
      overflow: 'hidden',
    }}>
      {/* Metrics */}
      <div style={{ display: 'flex', gap: 5, alignItems: 'center', flexShrink: 0 }}>
        <MetricPill theme={theme} value={total} label="Total" color={theme.text} tinted={false} />
        <MetricPill theme={theme} value={done} label="Done" color={ACCENT.green} tinted={done > 0} />
        <MetricPill theme={theme} value={active} label="Active" color={ACCENT.blue} tinted={active > 0} />
        <MetricPill
          theme={theme}
          value={failed}
          label="Failed"
          color={failed > 0 ? ACCENT.red : theme.muted}
          tinted={failed > 0}
        />
        {width >= 900 && (
          <MetricPill theme={theme} value={agents.length} label="Agents" color={ACCENT.purple} tinted={false} />
        )}
      </div>

      {/* Workflow stage rail */}
      {phases.phases.length > 0 && (
        <div
          role="list"
          aria-label="Workflow stages"
          style={{
            display: 'flex',
            alignItems: 'center',
            marginLeft: 'auto',
            minWidth: 0,
            overflow: 'hidden',
          }}
        >
          {phases.phases.map((p, i) => {
            const isCurrent = i === phases.currentIndex && !phases.allComplete;
            const isComplete = p.progress === 100 || (phases.allComplete && p.progress === 100);
            const isFailedStage = isCurrent && failureStage;
            const color = isFailedStage
              ? ACCENT.red
              : isComplete
                ? ACCENT.green
                : isCurrent
                  ? ACCENT.blue
                  : theme.muted;
            const label = labelMode === 'full' ? p.name : (STAGE_SHORT[p.name] || p.name.slice(0, 5));
            const showLabel = labelMode !== 'iconOnly' || isCurrent;
            return (
              <div key={p.phase} role="listitem" style={{ display: 'flex', alignItems: 'center', minWidth: 0 }}>
                <div
                  title={`${p.name}: ${isComplete ? 'complete' : isCurrent ? `active · ${p.progress}%` : 'upcoming'}`}
                  className={isCurrent ? 'compact-stage-active' : undefined}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: 5,
                    padding: showLabel ? '4px 8px' : '4px 5px',
                    borderRadius: 7,
                    background: isCurrent ? `${color}16` : 'transparent',
                    border: `1px solid ${isCurrent ? `${color}55` : 'transparent'}`,
                    minWidth: 0,
                  }}
                >
                  {/* Stage state glyph — never color-only */}
                  {isComplete ? (
                    <svg width="12" height="12" viewBox="0 0 16 16" aria-hidden="true" style={{ flexShrink: 0 }}>
                      <circle cx="8" cy="8" r="7" fill={`${color}22`} />
                      <path d="M4.5 8.5 L7 11 L11.5 5.5" fill="none" stroke={color} strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" />
                    </svg>
                  ) : isFailedStage ? (
                    <svg width="12" height="12" viewBox="0 0 16 16" aria-hidden="true" style={{ flexShrink: 0 }}>
                      <circle cx="8" cy="8" r="7" fill={`${color}22`} />
                      <path d="M5.5 5.5 L10.5 10.5 M10.5 5.5 L5.5 10.5" stroke={color} strokeWidth="1.7" strokeLinecap="round" />
                    </svg>
                  ) : isCurrent ? (
                    <span
                      aria-hidden="true"
                      className="compact-pulse-dot"
                      style={{
                        width: 8,
                        height: 8,
                        borderRadius: '50%',
                        background: color,
                        flexShrink: 0,
                        boxShadow: `0 0 0 3px ${color}22`,
                      }}
                    />
                  ) : (
                    <span aria-hidden="true" style={{
                      width: 8,
                      height: 8,
                      borderRadius: '50%',
                      border: `1.5px solid ${theme.muted}`,
                      flexShrink: 0,
                      opacity: 0.6,
                    }} />
                  )}
                  {showLabel && (
                    <span style={{
                      fontSize: 11,
                      fontWeight: isCurrent ? 800 : 600,
                      color: isCurrent || isComplete ? color : theme.muted,
                      textTransform: 'uppercase',
                      letterSpacing: '0.03em',
                      whiteSpace: 'nowrap',
                      overflow: 'hidden',
                      textOverflow: 'ellipsis',
                    }}>
                      {label}
                    </span>
                  )}
                </div>
                {i < phases.phases.length - 1 && (
                  <svg width="10" height="10" viewBox="0 0 12 12" aria-hidden="true" style={{ flexShrink: 0, opacity: 0.45 }}>
                    <path
                      d="M4 2 L8 6 L4 10"
                      fill="none"
                      stroke={isComplete ? ACCENT.green : theme.muted}
                      strokeWidth="1.5"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                    />
                  </svg>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

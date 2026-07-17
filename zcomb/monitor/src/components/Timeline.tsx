import { useMemo } from 'react';
import type { Task, Metrics } from '../hooks/usePolling';

type MilestoneStatus = 'complete' | 'active' | 'attention' | 'pending';

interface Milestone {
  id: number;
  name: string;
  done: number;
  total: number;
  failed: number;
  inProgress: number;
  pct: number;
  status: MilestoneStatus;
  tasks: Task[];
}

const statusConfig: Record<MilestoneStatus, {
  color: string;
  label: string;
}> = {
  complete: { color: '#3fb950', label: 'Complete' },
  active: { color: '#58a6ff', label: 'In Progress' },
  attention: { color: '#f85149', label: 'Attention' },
  pending: { color: '#7d8590', label: 'Upcoming' },
};

/**
 * Builds a generalized milestone list from whatever data is available:
 * named phases from metrics take priority, tasks grouped by phase fill
 * in counts, and anything unnamed falls back to "Milestone N".
 */
function buildMilestones(tasks: Task[], metrics?: Metrics): Milestone[] {
  const phaseNameMap = new Map<number, string>();
  (metrics?.phases || []).forEach(p => {
    if (p.name) phaseNameMap.set(p.phase, p.name);
  });

  const taskMap = new Map<number, Task[]>();
  tasks.forEach(t => {
    const list = taskMap.get(t.phase) || [];
    list.push(t);
    taskMap.set(t.phase, list);
  });

  // Union of phase ids seen in tasks and in metrics
  const ids = Array.from(new Set([
    ...taskMap.keys(),
    ...(metrics?.phases || []).map(p => p.phase),
  ])).sort((a, b) => a - b);

  return ids.map(id => {
    const pTasks = taskMap.get(id) || [];
    const total = pTasks.length;
    const done = pTasks.filter(t => t.status === 'done').length;
    const failed = pTasks.filter(t => t.status === 'failed').length;
    const inProgress = pTasks.filter(t => t.status === 'in_progress').length;
    const metricPct = (metrics?.phases || []).find(p => p.phase === id)?.progress ?? 0;
    const pct = total > 0 ? Math.round((done / total) * 100) : metricPct;

    let status: MilestoneStatus;
    if (failed > 0) status = 'attention';
    else if (pct === 100 && (total > 0 || metricPct === 100)) status = 'complete';
    else if (inProgress > 0 || pct > 0) status = 'active';
    else status = 'pending';

    return {
      id,
      name: phaseNameMap.get(id) || `Milestone ${id + 1}`,
      done,
      total,
      failed,
      inProgress,
      pct,
      status,
      tasks: pTasks,
    };
  });
}

function StatusIcon({ status, size = 24 }: { status: MilestoneStatus; size?: number }) {
  const { color } = statusConfig[status];
  const common = {
    width: size,
    height: size,
    borderRadius: '50%',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    flexShrink: 0,
  } as const;

  if (status === 'complete') {
    return (
      <div style={{ ...common, background: color, boxShadow: `0 0 10px ${color}55` }}>
        <svg width={size * 0.55} height={size * 0.55} viewBox="0 0 16 16">
          <path d="M13.78 4.22a.75.75 0 0 1 0 1.06l-7.25 7.25a.75.75 0 0 1-1.06 0L2.22 9.28a.75.75 0 1 1 1.06-1.06L6 10.94l6.72-6.72a.75.75 0 0 1 1.06 0Z" fill="#fff" />
        </svg>
      </div>
    );
  }
  if (status === 'active') {
    return (
      <div style={{ ...common, background: `${color}1c`, border: `2px solid ${color}` }}>
        <span
          className="timeline-active-dot"
          style={{ width: size * 0.32, height: size * 0.32, borderRadius: '50%', background: color }}
        />
      </div>
    );
  }
  if (status === 'attention') {
    return (
      <div style={{ ...common, background: `${color}1c`, border: `2px solid ${color}` }}>
        <span style={{ color, fontSize: size * 0.55, fontWeight: 800, lineHeight: 1 }}>!</span>
      </div>
    );
  }
  return (
    <div style={{ ...common, border: `2px dashed ${statusConfig.pending.color}66`, background: 'transparent' }} />
  );
}

/** Arrow connector drawn between milestone cards */
function Connector({ fromComplete, darkMode }: { fromComplete: boolean; darkMode: boolean }) {
  const color = fromComplete ? '#3fb950' : (darkMode ? '#30363d' : '#d0d7de');
  return (
    <div style={{
      display: 'flex',
      alignItems: 'center',
      flexShrink: 0,
      alignSelf: 'center',
      padding: '0 2px',
    }}>
      <svg width="22" height="10" viewBox="0 0 22 10" style={{ display: 'block' }}>
        <line
          x1="1" y1="5" x2="15" y2="5"
          stroke={color}
          strokeWidth="1.8"
          strokeLinecap="round"
          strokeDasharray={fromComplete ? undefined : '2 4'}
        />
        <path
          d="M15 1.5 L20 5 L15 8.5"
          fill="none"
          stroke={color}
          strokeWidth="1.8"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
    </div>
  );
}

export function Timeline({ tasks, metrics, darkMode }: {
  tasks: Task[];
  metrics?: Metrics;
  darkMode: boolean;
}) {
  const mutedColor = darkMode ? '#7d8590' : '#656d76';
  const textColor = darkMode ? '#e6edf3' : '#1f2328';
  const cardBg = darkMode ? '#161b22' : '#ffffff';
  const borderColor = darkMode ? '#30363d' : '#d0d7de';
  const barBg = darkMode ? '#21262d' : '#e1e4e8';

  const milestones = useMemo(() => buildMilestones(tasks, metrics), [tasks, metrics]);

  if (milestones.length === 0) return null;

  const completeCount = milestones.filter(m => m.status === 'complete').length;

  return (
    <div style={{ minWidth: 0 }}>
      {/* Section header */}
      <div style={{
        display: 'flex',
        alignItems: 'baseline',
        justifyContent: 'space-between',
        gap: 10,
        margin: '0 0 6px',
        flexWrap: 'wrap',
      }}>
        <div style={{ display: 'flex', alignItems: 'baseline', gap: 8 }}>
          <h3 style={{
            margin: 0,
            fontSize: 11,
            fontWeight: 700,
            textTransform: 'uppercase',
            color: mutedColor,
            letterSpacing: 1.5,
          }}>
            Timeline
          </h3>
          <span style={{
            fontSize: 10,
            color: mutedColor,
            fontWeight: 500,
            background: darkMode ? '#21262d' : '#eaeef2',
            padding: '1px 7px',
            borderRadius: 8,
            whiteSpace: 'nowrap',
          }}>
            {completeCount}/{milestones.length} complete
          </span>
        </div>
      </div>

      {/* Horizontal milestone track — scrolls when it doesn't fit */}
      <div
        className="timeline-scroll"
        style={{
          display: 'flex',
          alignItems: 'stretch',
          overflowX: 'auto',
          paddingBottom: 6,
          gap: 0,
        }}
      >
        {milestones.map((m, i) => {
          const cfg = statusConfig[m.status];
          const isActive = m.status === 'active';
          const isPending = m.status === 'pending';
          const taskSummary = m.tasks.length > 0
            ? m.tasks.map(t => `${t.status === 'done' ? '✓' : t.status === 'failed' ? '✕' : '·'} ${t.title}`).join('\n')
            : 'No tasks yet';

          return (
            <div key={m.id} style={{ display: 'flex', alignItems: 'stretch', flexShrink: 0 }}>
              <div
                className={`timeline-card${isActive ? ' timeline-card-active' : ''}`}
                title={taskSummary}
                style={{
                  display: 'flex',
                  flexDirection: 'column',
                  gap: 5,
                  width: 'clamp(138px, 13vw, 172px)',
                  flexShrink: 0,
                  background: isPending
                    ? (darkMode ? '#0d111766' : '#f6f8fa')
                    : cardBg,
                  border: `1px solid ${isActive ? `${cfg.color}55` : m.status === 'complete' ? `${cfg.color}33` : borderColor}`,
                  borderTop: `2px solid ${isPending ? borderColor : cfg.color}`,
                  borderRadius: 8,
                  padding: '7px 9px 8px',
                  opacity: isPending ? 0.75 : 1,
                  position: 'relative',
                }}
              >
                {/* Icon + index + status pill */}
                <div style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  gap: 6,
                }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 6, minWidth: 0 }}>
                    <StatusIcon status={m.status} size={17} />
                    <span style={{
                      fontSize: 9,
                      fontWeight: 700,
                      fontFamily: 'monospace',
                      color: mutedColor,
                      letterSpacing: 0.5,
                    }}>
                      {String(i + 1).padStart(2, '0')}
                    </span>
                  </div>
                  <span style={{
                    fontSize: 8,
                    fontWeight: 700,
                    textTransform: 'uppercase',
                    letterSpacing: 0.4,
                    color: cfg.color,
                    background: `${cfg.color}16`,
                    padding: '1px 6px',
                    borderRadius: 8,
                    whiteSpace: 'nowrap',
                    flexShrink: 0,
                  }}>
                    {cfg.label}
                  </span>
                </div>

                {/* Name — single line, full text in tooltip */}
                <div style={{
                  fontSize: 11.5,
                  fontWeight: 700,
                  color: isPending ? mutedColor : textColor,
                  lineHeight: 1.3,
                  whiteSpace: 'nowrap',
                  overflow: 'hidden',
                  textOverflow: 'ellipsis',
                }}>
                  {m.name}
                </div>

                {/* Progress */}
                <div style={{ marginTop: 'auto' }}>
                  <div style={{
                    height: 4,
                    borderRadius: 2,
                    background: barBg,
                    overflow: 'hidden',
                    marginBottom: 4,
                  }}>
                    <div style={{
                      width: `${m.pct}%`,
                      height: '100%',
                      borderRadius: 3,
                      background: m.status === 'attention'
                        ? `linear-gradient(90deg, ${cfg.color}aa, ${cfg.color})`
                        : m.status === 'complete'
                          ? '#3fb950'
                          : `linear-gradient(90deg, #1f6feb, #58a6ff)`,
                      transition: 'width 0.5s ease',
                    }} />
                  </div>
                  <div style={{
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    gap: 6,
                  }}>
                    <span style={{
                      fontSize: 9,
                      color: mutedColor,
                      fontVariantNumeric: 'tabular-nums',
                      whiteSpace: 'nowrap',
                    }}>
                      {m.total > 0 ? `${m.done}/${m.total} tasks` : 'no tasks'}
                    </span>
                    <span style={{
                      fontSize: 9,
                      fontWeight: 700,
                      color: isPending ? mutedColor : cfg.color,
                      fontVariantNumeric: 'tabular-nums',
                    }}>
                      {m.pct}%
                    </span>
                  </div>
                  {m.failed > 0 && (
                    <div style={{
                      marginTop: 3,
                      fontSize: 9,
                      fontWeight: 600,
                      color: '#f85149',
                    }}>
                      {m.failed} failed task{m.failed > 1 ? 's' : ''}
                    </div>
                  )}
                </div>
              </div>

              {i < milestones.length - 1 && (
                <Connector fromComplete={m.status === 'complete'} darkMode={darkMode} />
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

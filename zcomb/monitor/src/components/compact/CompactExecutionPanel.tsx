import type { Agent, Task } from '../../hooks/usePolling';
import type { CompactTheme, RunActionState, TaskStatus } from './runState';
import { ACCENT, STATUS_META, formatClock } from './runState';

const PRIORITY: Record<string, { label: string; color: string }> = {
  high: { label: 'High', color: ACCENT.red },
  medium: { label: 'Med', color: ACCENT.amber },
  low: { label: 'Low', color: ACCENT.gray },
};

/** Six-state Kanban status rail — each segment is a Current Work filter. */
function KanbanStatusRail({ theme, tasks, filter, onFilter, condensed }: {
  theme: CompactTheme;
  tasks: Task[];
  filter: TaskStatus;
  onFilter: (s: TaskStatus) => void;
  condensed: boolean;
}) {
  return (
    <div
      role="tablist"
      aria-label="Task states"
      style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(6, minmax(0, 1fr))',
        gap: 4,
        flexShrink: 0,
      }}
    >
      {STATUS_META.map(meta => {
        const count = tasks.filter(t => t.status === meta.key).length;
        const active = filter === meta.key;
        const label = condensed ? meta.short : meta.label;
        return (
          <button
            key={meta.key}
            type="button"
            role="tab"
            aria-selected={active}
            className="compact-rail-segment"
            title={`${meta.label}: ${count} task${count === 1 ? '' : 's'} — click to show in Current Work`}
            onClick={() => onFilter(meta.key)}
            style={{
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              gap: 2,
              minHeight: 44,
              padding: '5px 2px 4px',
              borderRadius: 8,
              background: active ? `${meta.color}18` : theme.cardBg,
              border: `1px solid ${active ? `${meta.color}66` : theme.borderSoft}`,
              boxShadow: active ? `inset 0 -2px 0 ${meta.color}` : 'none',
              cursor: 'pointer',
              minWidth: 0,
              overflow: 'hidden',
            }}
          >
            <span style={{
              fontSize: 15,
              fontWeight: 800,
              color: count > 0 ? meta.color : theme.muted,
              fontVariantNumeric: 'tabular-nums',
              lineHeight: 1,
            }}>
              {count}
            </span>
            <span style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: 3,
              fontSize: 11,
              fontWeight: active ? 700 : 600,
              color: active ? meta.color : theme.muted,
              whiteSpace: 'nowrap',
              overflow: 'hidden',
              textOverflow: 'ellipsis',
              maxWidth: '100%',
              lineHeight: 1.1,
            }}>
              <span aria-hidden="true" style={{ color: meta.color, fontSize: 11 }}>{meta.icon}</span>
              {label}
            </span>
          </button>
        );
      })}
    </div>
  );
}

function CompactTaskCard({ theme, task, assigneeName, dominant, onSelect }: {
  theme: CompactTheme;
  task: Task;
  assigneeName: string;
  dominant: boolean;
  onSelect: (task: Task) => void;
}) {
  const meta = STATUS_META.find(m => m.key === task.status) || STATUS_META[0];
  const priority = PRIORITY[task.priority] || PRIORITY.low;
  const running = task.status === 'in_progress';
  const firstDescLine = (task.description || '').split('\n').find(l => l.trim()) || '';
  return (
    <div
      role="button"
      tabIndex={0}
      className="compact-task-card"
      title="Click for details"
      onClick={() => onSelect(task)}
      onKeyDown={e => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          onSelect(task);
        }
      }}
      style={{
        position: 'relative',
        background: theme.cardBg,
        border: `1px solid ${running ? `${meta.color}3a` : theme.borderSoft}`,
        borderRadius: 10,
        padding: dominant ? '9px 11px 9px 14px' : '7px 10px 7px 13px',
        cursor: 'pointer',
        overflow: 'hidden',
        flexShrink: 0,
      }}
    >
      <span aria-hidden="true" style={{
        position: 'absolute',
        left: 0,
        top: 0,
        bottom: 0,
        width: 3,
        background: `linear-gradient(180deg, ${meta.color}, ${meta.color}80)`,
      }} />
      <div style={{ display: 'flex', alignItems: 'flex-start', gap: 7 }}>
        <span style={{
          fontSize: dominant ? 13 : 12,
          fontWeight: 600,
          color: theme.text,
          lineHeight: 1.35,
          minWidth: 0,
          flex: 1,
          display: '-webkit-box',
          WebkitLineClamp: dominant ? 2 : 1,
          WebkitBoxOrient: 'vertical',
          overflow: 'hidden',
          wordBreak: 'break-word',
        }}>
          {task.title.replace(/^Phase \d+: /, '')}
        </span>
        {running && (
          <span style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: 5,
            fontSize: 11,
            fontWeight: 700,
            letterSpacing: '0.05em',
            textTransform: 'uppercase',
            color: meta.color,
            background: `${meta.color}16`,
            borderRadius: 5,
            padding: '2px 7px',
            flexShrink: 0,
            whiteSpace: 'nowrap',
          }}>
            <span aria-hidden="true" className="compact-pulse-dot" style={{
              width: 5, height: 5, borderRadius: '50%', background: meta.color,
            }} />
            Running
          </span>
        )}
      </div>
      {dominant && firstDescLine && (
        <div
          title={task.description}
          style={{
            marginTop: 4,
            fontSize: 11,
            color: theme.subText,
            fontVariantNumeric: 'tabular-nums',
            whiteSpace: 'nowrap',
            overflow: 'hidden',
            textOverflow: 'ellipsis',
          }}
        >
          {firstDescLine}
        </div>
      )}
      <div style={{
        display: 'flex',
        alignItems: 'center',
        gap: 6,
        marginTop: dominant ? 7 : 5,
        minWidth: 0,
      }}>
        <span aria-hidden="true" style={{
          width: 13,
          height: 13,
          borderRadius: '50%',
          background: task.assignee ? `${meta.color}2e` : theme.track,
          border: `1.5px solid ${task.assignee ? meta.color : theme.muted}`,
          display: 'inline-block',
          flexShrink: 0,
        }} />
        <span style={{
          fontSize: 11,
          color: theme.subText,
          whiteSpace: 'nowrap',
          overflow: 'hidden',
          textOverflow: 'ellipsis',
          minWidth: 0,
          flex: 1,
        }}>
          {assigneeName}
        </span>
        <span style={{
          fontSize: 11,
          fontWeight: 700,
          color: priority.color,
          background: `${priority.color}14`,
          borderRadius: 4,
          padding: '1px 6px',
          flexShrink: 0,
        }}>
          {priority.label}
        </span>
        <span style={{
          fontSize: 11,
          fontWeight: 700,
          color: theme.subText,
          background: theme.track,
          borderRadius: 4,
          padding: '1px 6px',
          fontVariantNumeric: 'tabular-nums',
          flexShrink: 0,
        }}>
          P{task.phase}
        </span>
      </div>
    </div>
  );
}

/** High-signal alert card — failures / blocks / pending human gate. */
function AlertCard({ theme, kind, title, detail, actionHint }: {
  theme: CompactTheme;
  kind: 'danger' | 'warn';
  title: string;
  detail: string;
  actionHint: string;
}) {
  const color = kind === 'danger' ? ACCENT.red : ACCENT.amber;
  return (
    <div
      role="alert"
      style={{
        display: 'flex',
        gap: 9,
        alignItems: 'flex-start',
        background: `${color}10`,
        border: `1px solid ${color}44`,
        borderLeft: `3px solid ${color}`,
        borderRadius: 10,
        padding: '8px 11px',
        flexShrink: 0,
      }}
    >
      <svg width="15" height="15" viewBox="0 0 16 16" aria-hidden="true" style={{ flexShrink: 0, marginTop: 1 }}>
        <path
          d="M8 1.5 L15 13.5 H1 Z"
          fill="none"
          stroke={color}
          strokeWidth="1.5"
          strokeLinejoin="round"
        />
        <path d="M8 6 V9.5 M8 11.2 V11.6" stroke={color} strokeWidth="1.6" strokeLinecap="round" />
      </svg>
      <div style={{ minWidth: 0, flex: 1 }}>
        <div style={{ fontSize: 12, fontWeight: 700, color, lineHeight: 1.3 }}>
          {title}
        </div>
        <div
          title={detail}
          style={{
            fontSize: 11,
            color: theme.text,
            marginTop: 2,
            lineHeight: 1.4,
            display: '-webkit-box',
            WebkitLineClamp: 2,
            WebkitBoxOrient: 'vertical',
            overflow: 'hidden',
            wordBreak: 'break-word',
          }}
        >
          {detail}
        </div>
        <div style={{ fontSize: 11, color: theme.muted, marginTop: 3 }}>
          {actionHint}
        </div>
      </div>
    </div>
  );
}

/** Region B — dominant execution focus: status rail, alerts, current work. */
export function CompactExecutionPanel({
  theme,
  tasks,
  agents,
  actions,
  statusFilter,
  onStatusFilter,
  onSelectTask,
  onViewCompleted,
  condensed,
  railCondensed,
  maxCards,
}: {
  theme: CompactTheme;
  tasks: Task[];
  agents: Agent[];
  actions: RunActionState;
  statusFilter: TaskStatus;
  onStatusFilter: (s: TaskStatus) => void;
  onSelectTask: (task: Task) => void;
  onViewCompleted: () => void;
  condensed: boolean;
  /** Rail segments get abbreviated labels before the panel itself condenses. */
  railCondensed: boolean;
  /** How many task cards fit given current height (1 or 2). */
  maxCards: number;
}) {
  const agentMap = new Map(agents.map(a => [a.id, a.name]));
  const filterMeta = STATUS_META.find(m => m.key === statusFilter) || STATUS_META[2];

  const filtered = tasks.filter(t => t.status === statusFilter);
  // Freshest work first for live states; done keeps natural (latest last) → reverse.
  const ordered = statusFilter === 'done' ? [...filtered].reverse() : filtered;

  const failedTasks = tasks.filter(t => t.status === 'failed');
  const doneTasks = tasks.filter(t => t.status === 'done');
  const latestDone = doneTasks[doneTasks.length - 1];
  const gateTask = tasks.find(t => t.id === 'task-gate');

  const showFailureAlert = failedTasks.length > 0 && statusFilter !== 'failed';
  const showGateAlert = actions.atHumanGate;
  const alertCount = (showFailureAlert ? 1 : 0) + (showGateAlert ? 1 : 0);
  const visibleCards = Math.max(1, maxCards - alertCount);
  const shown = ordered.slice(0, visibleCards);
  const hiddenCount = ordered.length - shown.length;

  return (
    <div style={{
      display: 'flex',
      flexDirection: 'column',
      gap: 8,
      height: '100%',
      minHeight: 0,
    }}>
      <KanbanStatusRail
        theme={theme}
        tasks={tasks}
        filter={statusFilter}
        onFilter={onStatusFilter}
        condensed={railCondensed}
      />

      <div style={{
        display: 'flex',
        alignItems: 'baseline',
        gap: 7,
        flexShrink: 0,
        marginTop: 2,
      }}>
        <span style={{
          fontSize: 12,
          fontWeight: 700,
          textTransform: 'uppercase',
          letterSpacing: '0.08em',
          color: theme.muted,
        }}>
          {statusFilter === 'in_progress' ? 'Current Work' : filterMeta.label}
        </span>
        <span style={{
          fontSize: 11,
          fontWeight: 700,
          color: filterMeta.color,
          background: `${filterMeta.color}16`,
          borderRadius: 7,
          padding: '0 7px',
          lineHeight: '16px',
          fontVariantNumeric: 'tabular-nums',
        }}>
          {ordered.length}
        </span>
      </div>

      <div style={{
        display: 'flex',
        flexDirection: 'column',
        gap: 6,
        flex: 1,
        minHeight: 0,
        overflow: 'hidden',
      }}>
        {showGateAlert && (
          <AlertCard
            theme={theme}
            kind="warn"
            title="Human approval required"
            detail={gateTask
              ? gateTask.title.replace(/^Phase \d+: /, '')
              : 'The run is holding at the human gate for your decision.'}
            actionHint="Use Approve in the header to continue delivery."
          />
        )}
        {showFailureAlert && (
          <AlertCard
            theme={theme}
            kind="danger"
            title={`${failedTasks.length} failed task${failedTasks.length === 1 ? '' : 's'}`}
            detail={failedTasks[0].title.replace(/^Phase \d+: /, '')}
            actionHint="Select Failed in the rail above to inspect."
          />
        )}

        {shown.map((task, i) => (
          <CompactTaskCard
            key={task.id}
            theme={theme}
            task={task}
            assigneeName={task.assignee ? (agentMap.get(task.assignee) || task.assignee) : '—'}
            dominant={i === 0}
            onSelect={onSelectTask}
          />
        ))}

        {shown.length === 0 && alertCount === 0 && (
          <div style={{
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            justifyContent: 'center',
            gap: 4,
            padding: '14px 8px',
            borderRadius: 10,
            border: `1px dashed ${theme.borderSoft}`,
            color: theme.muted,
            fontSize: 12,
          }}>
            <span aria-hidden="true" style={{ fontSize: 15, color: filterMeta.color, opacity: 0.6 }}>
              {filterMeta.icon}
            </span>
            No tasks in {filterMeta.label}
          </div>
        )}

        {hiddenCount > 0 && (
          <div style={{
            fontSize: 11,
            color: theme.muted,
            padding: '1px 2px',
            flexShrink: 0,
          }}>
            +{hiddenCount} more in {filterMeta.label}
          </div>
        )}
      </div>

      {/* Completed aggregation — one calm summary line, never a column */}
      <button
        type="button"
        onClick={onViewCompleted}
        title="View completed tasks"
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 7,
          minHeight: 32,
          padding: '5px 10px',
          background: theme.cardBg,
          border: `1px solid ${theme.borderSoft}`,
          borderRadius: 9,
          cursor: 'pointer',
          color: theme.text,
          flexShrink: 0,
          textAlign: 'left',
        }}
        className="compact-done-summary"
      >
        <span aria-hidden="true" style={{ color: ACCENT.green, fontSize: 12, fontWeight: 700 }}>✓</span>
        <span style={{ fontSize: 12, fontWeight: 600, whiteSpace: 'nowrap' }}>
          <span style={{ color: ACCENT.green, fontVariantNumeric: 'tabular-nums' }}>{doneTasks.length}</span>
          {' '}completed
        </span>
        {latestDone && !condensed && (
          <span style={{
            fontSize: 11,
            color: theme.muted,
            fontVariantNumeric: 'tabular-nums',
            whiteSpace: 'nowrap',
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            minWidth: 0,
          }}>
            latest {formatClock(latestDone.updatedAt)}
          </span>
        )}
        <span style={{ marginLeft: 'auto', fontSize: 11, color: theme.muted, whiteSpace: 'nowrap' }}>
          View all ▸
        </span>
      </button>
    </div>
  );
}

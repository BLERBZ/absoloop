import { useMemo } from 'react';
import type { Activity, Agent } from '../../hooks/usePolling';
import type { CompactTheme } from './runState';
import { ACCENT, formatClock } from './runState';

const TYPE_COLOR: Record<string, string> = {
  error: ACCENT.red,
  task_failed: ACCENT.red,
  task_completed: ACCENT.green,
  task_started: ACCENT.blue,
  status_change: ACCENT.blue,
  phase_start: ACCENT.blue,
  self_reflection: ACCENT.purple,
  research: ACCENT.amber,
  spawned: ACCENT.blue,
  session_start: ACCENT.green,
  heartbeat: ACCENT.gray,
};

const TYPE_BADGE: Record<string, string> = {
  error: 'ERROR',
  task_failed: 'FAILED',
  task_completed: 'DONE',
  task_started: 'START',
  status_change: 'SAY',
  phase_start: 'PHASE',
  self_reflection: 'REFLECT',
  research: 'RESEARCH',
  spawned: 'SPAWNED',
  session_start: 'SESSION',
  heartbeat: 'BEAT',
};

/** Lower = more important. Errors and gates outrank routine progress. */
function priorityOf(type: string): number {
  if (type === 'error' || type === 'task_failed') return 0;
  if (type.includes('approval') || type.includes('gate')) return 1;
  if (type === 'task_started' || type === 'task_completed' || type === 'phase_start') return 2;
  if (type === 'status_change' || type === 'self_reflection' || type === 'research') return 3;
  return 4;
}

/** Region C — what just happened. Latest N events, critical first. */
export function CompactActivityPanel({ theme, activity, agents, maxEntries, onViewAll, onSelectEntry }: {
  theme: CompactTheme;
  activity: Activity[];
  agents: Agent[];
  maxEntries: number;
  onViewAll: () => void;
  onSelectEntry: () => void;
}) {
  const agentNames = useMemo(
    () => new Map(agents.map(a => [a.id, a.name])),
    [agents],
  );

  const entries = useMemo(() => {
    // Recency window first, then promote by priority within it so a recent
    // error outranks routine chatter without resurrecting ancient events.
    const recent = activity.slice(-24).reverse();
    return recent
      .map((item, idx) => ({ item, idx }))
      .sort((a, b) => {
        const pa = priorityOf(a.item.type);
        const pb = priorityOf(b.item.type);
        if (pa !== pb) return pa - pb;
        return a.idx - b.idx;
      })
      .slice(0, maxEntries)
      // Re-present chronologically (newest first) once selected.
      .sort((a, b) => a.idx - b.idx)
      .map(e => e.item);
  }, [activity, maxEntries]);

  const hasMore = activity.length > entries.length;

  return (
    <div style={{
      display: 'flex',
      flexDirection: 'column',
      height: '100%',
      minHeight: 0,
    }}>
      <div style={{
        fontSize: 12,
        fontWeight: 700,
        textTransform: 'uppercase',
        letterSpacing: '0.08em',
        color: theme.muted,
        marginBottom: 6,
        flexShrink: 0,
      }}>
        Live Activity
      </div>

      <div
        className={hasMore ? 'compact-activity-fade' : undefined}
        style={{
          flex: 1,
          minHeight: 0,
          overflowY: 'auto',
          overflowX: 'hidden',
          display: 'flex',
          flexDirection: 'column',
        }}
      >
        {entries.length === 0 && (
          <div style={{ color: theme.muted, fontSize: 12, padding: '10px 2px' }}>
            Waiting for agent activity…
          </div>
        )}
        {entries.map((item, i) => {
          const color = TYPE_COLOR[item.type] || theme.muted;
          const badge = TYPE_BADGE[item.type] || item.type.replace(/_/g, ' ').toUpperCase();
          const agentName = agentNames.get(item.agentId) || item.agentId;
          const critical = priorityOf(item.type) === 0;
          return (
            <button
              key={`${item.timestamp}-${i}`}
              type="button"
              className="compact-activity-entry"
              title="Open full activity"
              onClick={onSelectEntry}
              style={{
                display: 'block',
                width: '100%',
                textAlign: 'left',
                background: critical ? `${ACCENT.red}0c` : 'none',
                border: 'none',
                borderBottom: `1px solid ${theme.borderSoft}`,
                borderRadius: critical ? 6 : 0,
                padding: '7px 2px',
                cursor: 'pointer',
                color: theme.text,
              }}
            >
              <span style={{
                display: 'flex',
                alignItems: 'center',
                gap: 5,
                marginBottom: 3,
                minWidth: 0,
              }}>
                <span style={{
                  fontSize: 11,
                  fontFamily: 'ui-monospace, monospace',
                  color: theme.muted,
                  fontVariantNumeric: 'tabular-nums',
                  flexShrink: 0,
                }}>
                  {formatClock(item.timestamp)}
                </span>
                <span style={{
                  fontSize: 11,
                  fontWeight: 600,
                  color: theme.subText,
                  minWidth: 0,
                  overflow: 'hidden',
                  textOverflow: 'ellipsis',
                  whiteSpace: 'nowrap',
                  flex: 1,
                }}>
                  {agentName}
                </span>
                <span style={{
                  fontSize: 11,
                  fontWeight: 700,
                  color,
                  background: `${color}18`,
                  padding: '0 6px',
                  borderRadius: 4,
                  letterSpacing: '0.03em',
                  lineHeight: '15px',
                  flexShrink: 0,
                }}>
                  {badge}
                </span>
              </span>
              <span style={{
                display: '-webkit-box',
                WebkitLineClamp: 3,
                WebkitBoxOrient: 'vertical',
                overflow: 'hidden',
                fontSize: 11.5,
                lineHeight: 1.4,
                color: theme.text,
                overflowWrap: 'anywhere',
                wordBreak: 'break-word',
              }}>
                {item.message}
              </span>
            </button>
          );
        })}
      </div>

      <button
        type="button"
        onClick={onViewAll}
        style={{
          marginTop: 6,
          minHeight: 30,
          padding: '4px 8px',
          fontSize: 11,
          fontWeight: 600,
          color: theme.subText,
          background: 'none',
          border: `1px solid ${theme.borderSoft}`,
          borderRadius: 8,
          cursor: 'pointer',
          flexShrink: 0,
        }}
        className="compact-view-all"
      >
        View all activity
      </button>
    </div>
  );
}

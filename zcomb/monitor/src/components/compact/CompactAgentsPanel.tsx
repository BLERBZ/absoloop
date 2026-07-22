import { useState } from 'react';
import type { Agent } from '../../hooks/usePolling';
import type { CompactTheme } from './runState';
import { ACCENT } from './runState';

const AGENT_STATUS: Record<Agent['status'], { label: string; color: string }> = {
  active: { label: 'Active', color: ACCENT.green },
  idle: { label: 'Idle', color: ACCENT.gray },
  blocked: { label: 'Blocked', color: ACCENT.amber },
  done: { label: 'Done', color: ACCENT.blue },
};

function AgentStatusBadge({ status }: { status: Agent['status'] }) {
  const meta = AGENT_STATUS[status] || AGENT_STATUS.idle;
  return (
    <span style={{
      display: 'inline-flex',
      alignItems: 'center',
      gap: 5,
      fontSize: 11,
      fontWeight: 700,
      letterSpacing: '0.04em',
      textTransform: 'uppercase',
      color: meta.color,
      background: `${meta.color}16`,
      borderRadius: 5,
      padding: '2px 7px',
      whiteSpace: 'nowrap',
      flexShrink: 0,
    }}>
      {status === 'active' && (
        <span
          aria-hidden="true"
          className="compact-pulse-dot"
          style={{ width: 5, height: 5, borderRadius: '50%', background: meta.color }}
        />
      )}
      {meta.label}
    </span>
  );
}

/** Region A — who is working and what are they doing right now. */
export function CompactAgentsPanel({ theme, agents, condensed }: {
  theme: CompactTheme;
  agents: Agent[];
  /** True at narrow widths — secondary rows collapse harder. */
  condensed: boolean;
}) {
  const [expandedId, setExpandedId] = useState<string | null>(null);

  if (agents.length === 0) {
    return (
      <div style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        height: '100%',
        color: theme.muted,
        fontSize: 12,
        padding: 12,
        textAlign: 'center',
      }}>
        No agents spawned yet
      </div>
    );
  }

  const sorted = [...agents].sort((a, b) => {
    const rank = (s: Agent['status']) => (s === 'active' ? 0 : s === 'blocked' ? 1 : s === 'done' ? 2 : 3);
    return rank(a.status) - rank(b.status);
  });
  const [primary, ...secondary] = sorted;
  const primaryMeta = AGENT_STATUS[primary.status] || AGENT_STATUS.idle;
  const maxTasks = Math.max(...agents.map(a => a.metrics.tasksCompleted), 1);
  const primaryPct = Math.round((primary.metrics.tasksCompleted / maxTasks) * 100);

  return (
    <div style={{
      display: 'flex',
      flexDirection: 'column',
      gap: 6,
      height: '100%',
      minHeight: 0,
      overflowY: 'auto',
    }}>
      {/* Active worker card */}
      <div
        className={primary.status === 'active' ? 'compact-agent-active' : undefined}
        style={{
          background: theme.cardBg,
          border: `1px solid ${primary.status === 'active' ? `${primaryMeta.color}44` : theme.borderSoft}`,
          borderLeft: `3px solid ${primaryMeta.color}`,
          borderRadius: 10,
          padding: '9px 10px',
          flexShrink: 0,
        }}
      >
        <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 6 }}>
          <span style={{
            fontSize: 13,
            fontWeight: 700,
            color: theme.text,
            lineHeight: 1.25,
            minWidth: 0,
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            whiteSpace: 'nowrap',
          }}>
            {primary.name}
          </span>
          <AgentStatusBadge status={primary.status} />
        </div>
        <div
          title={primary.role}
          style={{
            fontSize: 11,
            color: theme.muted,
            marginTop: 3,
            whiteSpace: 'nowrap',
            overflow: 'hidden',
            textOverflow: 'ellipsis',
          }}
        >
          {primary.role}
        </div>
        {primary.currentTask && (
          <div
            title={primary.currentTask}
            style={{
              fontSize: 11,
              color: theme.text,
              background: theme.shellBg,
              border: `1px solid ${theme.borderSoft}`,
              borderLeft: `2px solid ${primaryMeta.color}`,
              padding: '5px 8px',
              borderRadius: 6,
              marginTop: 7,
              fontFamily: 'ui-monospace, monospace',
              lineHeight: 1.4,
              overflowWrap: 'anywhere',
              wordBreak: 'break-word',
              display: '-webkit-box',
              WebkitLineClamp: 2,
              WebkitBoxOrient: 'vertical',
              overflow: 'hidden',
            }}
          >
            {primary.currentTask}
          </div>
        )}
        <div style={{
          display: 'flex',
          alignItems: 'center',
          gap: 10,
          marginTop: 7,
          fontSize: 11,
          color: theme.muted,
        }}>
          <span>
            Tasks{' '}
            <strong style={{ color: theme.text, fontVariantNumeric: 'tabular-nums' }}>
              {primary.metrics.tasksCompleted}
            </strong>
          </span>
          <span>
            Errors{' '}
            <strong style={{
              color: primary.metrics.errors > 0 ? ACCENT.red : theme.text,
              fontVariantNumeric: 'tabular-nums',
            }}>
              {primary.metrics.errors}
            </strong>
          </span>
          <span style={{
            flex: 1,
            height: 4,
            borderRadius: 2,
            background: theme.track,
            overflow: 'hidden',
            minWidth: 24,
          }}>
            <span style={{
              display: 'block',
              width: `${primaryPct}%`,
              height: '100%',
              borderRadius: 2,
              background: primaryMeta.color,
              transition: 'width 0.6s ease',
            }} />
          </span>
        </div>
      </div>

      {/* Secondary agents — compact expandable rows */}
      {secondary.map(agent => {
        const meta = AGENT_STATUS[agent.status] || AGENT_STATUS.idle;
        const expanded = expandedId === agent.id;
        return (
          <div key={agent.id} style={{ flexShrink: 0 }}>
            <button
              type="button"
              className="compact-agent-row"
              aria-expanded={expanded}
              title={condensed ? `${agent.name} — ${meta.label}` : undefined}
              onClick={() => setExpandedId(expanded ? null : agent.id)}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 7,
                width: '100%',
                minHeight: 32,
                padding: '5px 8px',
                background: expanded ? theme.cardBg : 'transparent',
                border: `1px solid ${expanded ? theme.borderSoft : 'transparent'}`,
                borderRadius: expanded ? '8px 8px 0 0' : 8,
                cursor: 'pointer',
                textAlign: 'left',
                color: theme.text,
              }}
            >
              <span aria-hidden="true" style={{
                width: 7,
                height: 7,
                borderRadius: '50%',
                background: meta.color,
                flexShrink: 0,
              }} />
              <span style={{
                fontSize: 12,
                fontWeight: 600,
                minWidth: 0,
                overflow: 'hidden',
                textOverflow: 'ellipsis',
                whiteSpace: 'nowrap',
                flex: 1,
              }}>
                {agent.name}
              </span>
              {agent.metrics.errors > 0 && (
                <span
                  title={`${agent.metrics.errors} errors`}
                  style={{
                    fontSize: 11,
                    fontWeight: 700,
                    color: ACCENT.red,
                    fontVariantNumeric: 'tabular-nums',
                    flexShrink: 0,
                  }}
                >
                  ✕{agent.metrics.errors}
                </span>
              )}
              <span style={{
                fontSize: 11,
                fontWeight: 600,
                color: meta.color,
                textTransform: 'uppercase',
                letterSpacing: '0.03em',
                flexShrink: 0,
              }}>
                {meta.label}
              </span>
            </button>
            {expanded && (
              <div style={{
                background: theme.cardBg,
                border: `1px solid ${theme.borderSoft}`,
                borderTop: 'none',
                borderRadius: '0 0 8px 8px',
                padding: '7px 9px',
                fontSize: 11,
                color: theme.subText,
                lineHeight: 1.45,
              }}>
                <div style={{
                  display: '-webkit-box',
                  WebkitLineClamp: 2,
                  WebkitBoxOrient: 'vertical',
                  overflow: 'hidden',
                }} title={agent.role}>
                  {agent.role}
                </div>
                {agent.currentTask && (
                  <div
                    title={agent.currentTask}
                    style={{
                      marginTop: 5,
                      fontFamily: 'ui-monospace, monospace',
                      color: theme.text,
                      overflowWrap: 'anywhere',
                      display: '-webkit-box',
                      WebkitLineClamp: 2,
                      WebkitBoxOrient: 'vertical',
                      overflow: 'hidden',
                    }}
                  >
                    {agent.currentTask}
                  </div>
                )}
                <div style={{ marginTop: 5, color: theme.muted }}>
                  Tasks{' '}
                  <strong style={{ color: theme.text }}>{agent.metrics.tasksCompleted}</strong>
                  {' · '}Errors{' '}
                  <strong style={{ color: agent.metrics.errors > 0 ? ACCENT.red : theme.text }}>
                    {agent.metrics.errors}
                  </strong>
                </div>
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

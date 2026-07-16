import type { Agent } from '../hooks/usePolling';

const statusColors: Record<string, string> = {
  active: '#3fb950',
  idle: '#7d8590',
  blocked: '#d29922',
  done: '#58a6ff'
};

const statusLabels: Record<string, string> = {
  active: 'ACTIVE',
  idle: 'IDLE',
  blocked: 'BLOCKED',
  done: 'DONE'
};

function Sparkline({ value, max, color, darkMode }: { value: number; max: number; color: string; darkMode: boolean }) {
  const pct = max > 0 ? Math.round((value / max) * 100) : 0;
  return (
    <div style={{
      display: 'flex',
      alignItems: 'center',
      gap: 6,
      marginTop: 6,
    }}>
      <div style={{
        flex: 1,
        height: 4,
        borderRadius: 2,
        background: darkMode ? '#21262d' : '#e1e4e8',
        overflow: 'hidden',
      }}>
        <div style={{
          width: `${pct}%`,
          height: '100%',
          borderRadius: 2,
          background: `linear-gradient(90deg, ${color}80, ${color})`,
          transition: 'width 0.6s ease',
        }} />
      </div>
      <span style={{
        fontSize: 9,
        fontWeight: 700,
        color,
        fontVariantNumeric: 'tabular-nums',
        width: 24,
        textAlign: 'right',
      }}>
        {pct}%
      </span>
    </div>
  );
}

export function AgentCards({ agents, darkMode }: { agents: Agent[]; darkMode: boolean }) {
  const cardBg = darkMode ? '#161b22' : '#ffffff';
  const borderColor = darkMode ? '#30363d' : '#d0d7de';
  const mutedColor = darkMode ? '#7d8590' : '#656d76';
  const textColor = darkMode ? '#e6edf3' : '#1f2328';

  if (agents.length === 0) {
    return (
      <div style={{ color: mutedColor, fontSize: 13, textAlign: 'center', padding: 20 }}>
        No agents spawned yet...
      </div>
    );
  }

  const maxTasks = Math.max(...agents.map(a => a.metrics.tasksCompleted), 1);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
      {agents.map(agent => {
        const color = statusColors[agent.status] || '#7d8590';
        return (
          <div
            key={agent.id}
            className={agent.status === 'active' ? 'agent-card-active' : ''}
            style={{
              background: cardBg,
              border: `1px solid ${agent.status === 'active' ? `${color}44` : borderColor}`,
              borderRadius: 8,
              padding: '14px 14px 12px',
              borderLeft: `3px solid ${color}`,
              transition: 'border-color 0.3s ease, box-shadow 0.3s ease',
              '--pulse-color': `${color}30`,
            } as React.CSSProperties}
          >
            {/* Name + Status Badge */}
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
              <span style={{ fontWeight: 700, fontSize: 14, color: textColor }}>{agent.name}</span>
              <span style={{
                fontSize: 10,
                fontWeight: 700,
                color: color,
                background: `${color}18`,
                padding: '2px 8px',
                borderRadius: 4,
                letterSpacing: 0.5,
                textTransform: 'uppercase',
                display: 'inline-flex',
                alignItems: 'center',
                gap: 5,
              }}>
                {agent.status === 'active' && (
                  <span style={{
                    width: 6,
                    height: 6,
                    borderRadius: '50%',
                    background: color,
                    boxShadow: `0 0 6px ${color}`,
                    animation: 'pulse-healthy 2.5s ease-in-out infinite',
                    flexShrink: 0,
                  }} />
                )}
                {statusLabels[agent.status] || agent.status}
              </span>
            </div>

            {/* Role */}
            <div style={{
              fontSize: 11,
              color: mutedColor,
              marginBottom: 8,
              lineHeight: 1.4
            }}>
              {agent.role}
            </div>

            {/* Current Task */}
            {agent.currentTask && (
              <div style={{
                fontSize: 11,
                color: textColor,
                background: darkMode ? '#0d1117' : '#f6f8fa',
                padding: '6px 10px',
                borderRadius: 6,
                marginBottom: 8,
                borderLeft: `2px solid ${color}`,
                fontFamily: 'monospace',
                lineHeight: 1.4
              }}>
                {agent.currentTask}
              </div>
            )}

            {/* Metrics + Sparkline */}
            <div style={{
              paddingTop: 4,
              borderTop: `1px solid ${darkMode ? '#21262d' : '#e8e8e8'}`
            }}>
              <div style={{
                display: 'flex',
                gap: 16,
                fontSize: 11,
                color: mutedColor,
              }}>
                <span>Tasks <strong style={{ color: textColor }}>{agent.metrics.tasksCompleted}</strong></span>
                <span>Errors <strong style={{ color: agent.metrics.errors > 0 ? '#f85149' : textColor }}>{agent.metrics.errors}</strong></span>
              </div>
              <Sparkline
                value={agent.metrics.tasksCompleted}
                max={maxTasks}
                color={color}
                darkMode={darkMode}
              />
            </div>
          </div>
        );
      })}
    </div>
  );
}

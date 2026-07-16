import type { Activity } from '../hooks/usePolling';

const typeColors: Record<string, string> = {
  task_started: '#58a6ff',
  task_completed: '#3fb950',
  task_failed: '#f85149',
  self_reflection: '#a371f7',
  heartbeat: '#7d8590',
  research: '#d29922',
  spawned: '#79c0ff',
  status_change: '#d2a8ff',
  error: '#f85149',
  phase_start: '#58a6ff',
  session_start: '#3fb950'
};

const typeBadgeLabels: Record<string, string> = {
  task_started: 'STARTED',
  task_completed: 'COMPLETED',
  task_failed: 'FAILED',
  self_reflection: 'REFLECTION',
  heartbeat: 'HEARTBEAT',
  research: 'RESEARCH',
  spawned: 'SPAWNED',
  status_change: 'STATUS',
  error: 'ERROR',
  phase_start: 'PHASE',
  session_start: 'SESSION'
};

function formatTime(ts: string): string {
  try {
    const d = new Date(ts);
    const h = d.getHours().toString().padStart(2, '0');
    const m = d.getMinutes().toString().padStart(2, '0');
    return `${h}:${m}`;
  } catch {
    return '--:--';
  }
}

// Map agent IDs to friendly display names
const agentDisplayNames: Record<string, string> = {
  'architect-01': 'Lead Architect',
  'ui-engineer-01': 'UI Engineer',
  'ux-designer-01': 'UX Designer',
  'frontend-dev-01': 'Frontend Developer',
  'qa-specialist-01': 'QA Specialist',
  'remotion-dev-01': 'Remotion Developer',
  'motion-designer-01': 'Motion Designer',
  'audio-engineer-01': 'Audio Engineer',
  'qa-validator-01': 'QA Validator'
};

export function ActivityFeed({ activity, filter, darkMode, agents }: {
  activity: Activity[];
  filter: string;
  darkMode: boolean;
  agents?: { id: string; name: string }[];
}) {
  const mutedColor = darkMode ? '#7d8590' : '#656d76';
  const borderColor = darkMode ? '#21262d' : '#e1e4e8';
  const textColor = darkMode ? '#c9d1d9' : '#1f2328';

  // Build agent name lookup from props or fallback to static map
  const agentNameMap = new Map<string, string>();
  if (agents) {
    agents.forEach(a => agentNameMap.set(a.id, a.name));
  }

  const filtered = filter === 'all' ? activity : activity.filter(a => a.agentId === filter);
  const reversed = [...filtered].reverse();

  if (reversed.length === 0) {
    return (
      <div style={{ color: mutedColor, fontSize: 12, textAlign: 'center', padding: 20 }}>
        Waiting for agent activity...
      </div>
    );
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 0 }}>
      {reversed.map((item, i) => {
        const color = typeColors[item.type] || mutedColor;
        const agentName = agentNameMap.get(item.agentId) || agentDisplayNames[item.agentId] || item.agentId;
        const badge = typeBadgeLabels[item.type] || item.type.replace(/_/g, ' ').toUpperCase();

        return (
          <div
            key={i}
            style={{
              padding: '10px 0',
              borderBottom: `1px solid ${borderColor}`,
              fontSize: 12
            }}
          >
            {/* Timestamp + Agent Name + Type Badge */}
            <div style={{
              display: 'flex',
              alignItems: 'center',
              gap: 6,
              marginBottom: 4,
              flexWrap: 'wrap'
            }}>
              <span style={{
                color: mutedColor,
                fontSize: 10,
                fontFamily: 'monospace',
                flexShrink: 0
              }}>
                {formatTime(item.timestamp)}
              </span>
              <span style={{ color: mutedColor, fontSize: 10 }}>on</span>
              <span style={{
                fontWeight: 600,
                color: textColor,
                fontSize: 11
              }}>
                {agentName}
              </span>
              <span style={{
                fontSize: 9,
                fontWeight: 700,
                color: color,
                background: `${color}18`,
                padding: '1px 6px',
                borderRadius: 3,
                letterSpacing: 0.3,
                flexShrink: 0
              }}>
                {badge}
              </span>
            </div>

            {/* Message */}
            <div style={{
              color: textColor,
              lineHeight: 1.45,
              fontSize: 12,
              paddingLeft: 2
            }}>
              {item.message}
            </div>
          </div>
        );
      })}
    </div>
  );
}

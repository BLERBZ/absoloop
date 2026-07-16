import type { Task, Agent, Metrics } from '../hooks/usePolling';

/** Mini donut (ring) chart rendered as SVG */
function MiniDonut({ progress, color, size = 32, strokeWidth = 3.5, darkMode }: {
  progress: number;
  color: string;
  size?: number;
  strokeWidth?: number;
  darkMode: boolean;
}) {
  const radius = (size - strokeWidth) / 2;
  const circumference = 2 * Math.PI * radius;
  const offset = circumference - (progress / 100) * circumference;
  const trackColor = darkMode ? '#21262d' : '#e1e4e8';

  return (
    <svg
      width={size}
      height={size}
      viewBox={`0 0 ${size} ${size}`}
      style={{ transform: 'rotate(-90deg)', flexShrink: 0 }}
    >
      {/* Background track */}
      <circle
        cx={size / 2}
        cy={size / 2}
        r={radius}
        fill="none"
        stroke={trackColor}
        strokeWidth={strokeWidth}
      />
      {/* Progress arc */}
      <circle
        className="donut-track"
        cx={size / 2}
        cy={size / 2}
        r={radius}
        fill="none"
        stroke={color}
        strokeWidth={strokeWidth}
        strokeDasharray={circumference}
        strokeDashoffset={offset}
        strokeLinecap="round"
        style={{
          filter: progress === 100 ? `drop-shadow(0 0 3px ${color})` : 'none',
        }}
      />
    </svg>
  );
}

export function MetricsPanel({ tasks, agents, metrics, darkMode }: {
  tasks: Task[];
  agents: Agent[];
  metrics?: Metrics;
  darkMode: boolean;
}) {
  const mutedColor = darkMode ? '#7d8590' : '#656d76';
  const textColor = darkMode ? '#e6edf3' : '#1f2328';
  const borderColor = darkMode ? '#30363d' : '#d0d7de';
  const barBg = darkMode ? '#21262d' : '#e1e4e8';

  const totalTasks = tasks.length;
  const doneTasks = tasks.filter(t => t.status === 'done').length;
  const activeTasks = tasks.filter(t => t.status === 'in_progress').length;
  const failedTasks = tasks.filter(t => t.status === 'failed').length;
  const phases = metrics?.phases || [];

  return (
    <div style={{
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'space-between',
      gap: 16,
      flexWrap: 'wrap'
    }}>
      {/* Large Stat Counters */}
      <div style={{
        display: 'flex',
        gap: 24,
        alignItems: 'center'
      }}>
        <BigStat value={totalTasks} label="TOTAL TASKS" color={textColor} />
        <div style={{ width: 1, height: 32, background: borderColor }} />
        <BigStat value={doneTasks} label="COMPLETED" color="#3fb950" />
        <div style={{ width: 1, height: 32, background: borderColor }} />
        <BigStat value={activeTasks} label="ACTIVE" color="#58a6ff" />
        <div style={{ width: 1, height: 32, background: borderColor }} />
        <BigStat value={failedTasks} label="FAILED" color={failedTasks > 0 ? '#f85149' : textColor} />
        <div style={{ width: 1, height: 32, background: borderColor }} />
        <BigStat value={agents.length} label="AGENTS" color="#a371f7" />
      </div>

      {/* Phase Tabs */}
      {phases.length > 0 && (
        <div style={{
          display: 'flex',
          gap: 2,
          alignItems: 'center',
          flexWrap: 'wrap'
        }}>
          {phases.map(p => {
            const isComplete = p.progress === 100;
            const isActive = p.progress > 0 && p.progress < 100;
            const ringColor = isComplete ? '#3fb950' : isActive ? '#58a6ff' : '#30363d';
            return (
              <div
                key={p.phase}
                style={{
                  display: 'flex',
                  flexDirection: 'column',
                  alignItems: 'center',
                  padding: '4px 10px',
                  borderRadius: 4,
                  background: isActive ? (darkMode ? '#1f6feb22' : '#ddf4ff') :
                    isComplete ? (darkMode ? '#23863618' : '#dafbe1') : 'transparent',
                  border: `1px solid ${isActive ? '#58a6ff44' : isComplete ? '#3fb95033' : 'transparent'}`,
                  minWidth: 70,
                  cursor: 'default',
                  gap: 2,
                }}
              >
                {/* Mini donut chart */}
                <div style={{ position: 'relative', width: 30, height: 30 }}>
                  <MiniDonut
                    progress={p.progress}
                    color={ringColor}
                    size={30}
                    strokeWidth={3}
                    darkMode={darkMode}
                  />
                  {/* Centered percentage text */}
                  <span style={{
                    position: 'absolute',
                    top: '50%',
                    left: '50%',
                    transform: 'translate(-50%, -50%)',
                    fontSize: 7,
                    fontWeight: 700,
                    color: isActive ? '#58a6ff' : isComplete ? '#3fb950' : mutedColor,
                    fontVariantNumeric: 'tabular-nums',
                  }}>
                    {p.progress}
                  </span>
                </div>
                <span style={{
                  fontSize: 9,
                  fontWeight: 600,
                  color: isActive ? '#58a6ff' : isComplete ? '#3fb950' : mutedColor,
                  textTransform: 'uppercase',
                  letterSpacing: 0.3,
                  whiteSpace: 'nowrap'
                }}>
                  {p.name}
                </span>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

function BigStat({ value, label, color }: { value: number; label: string; color: string }) {
  return (
    <div style={{ textAlign: 'center' }}>
      <div style={{
        fontSize: 28,
        fontWeight: 800,
        color,
        fontVariantNumeric: 'tabular-nums',
        lineHeight: 1
      }}>
        {value}
      </div>
      <div style={{
        fontSize: 9,
        fontWeight: 600,
        color: '#7d8590',
        letterSpacing: 0.8,
        marginTop: 4,
        textTransform: 'uppercase'
      }}>
        {label}
      </div>
    </div>
  );
}

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
      <circle
        cx={size / 2}
        cy={size / 2}
        r={radius}
        fill="none"
        stroke={trackColor}
        strokeWidth={strokeWidth}
      />
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

function StatCard({ value, label, color, darkMode, emphasize }: {
  value: number;
  label: string;
  color: string;
  darkMode: boolean;
  emphasize?: boolean;
}) {
  const tinted = emphasize || value > 0;
  return (
    <div className="footer-stat-card" style={{
      display: 'flex',
      flexDirection: 'column',
      alignItems: 'center',
      justifyContent: 'center',
      gap: 3,
      padding: '8px 14px',
      minWidth: 78,
      borderRadius: 10,
      background: tinted
        ? `${color}0e`
        : (darkMode ? '#161b2266' : '#f6f8fa'),
      border: `1px solid ${tinted ? `${color}2e` : (darkMode ? '#21262d' : '#e1e4e8')}`,
    }}>
      <span style={{
        fontSize: 'clamp(18px, 2.2vw, 26px)',
        fontWeight: 800,
        color,
        fontVariantNumeric: 'tabular-nums',
        lineHeight: 1,
      }}>
        {value}
      </span>
      <span style={{
        fontSize: 8.5,
        fontWeight: 700,
        color: '#7d8590',
        letterSpacing: 0.8,
        textTransform: 'uppercase',
        whiteSpace: 'nowrap',
      }}>
        {label}
      </span>
    </div>
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
      flexWrap: 'wrap',
      minWidth: 0,
    }}>
      {/* Stat cards */}
      <div style={{
        display: 'flex',
        gap: 8,
        alignItems: 'stretch',
        flexWrap: 'wrap',
        minWidth: 0,
      }}>
        <StatCard value={totalTasks} label="Total Tasks" color={textColor} darkMode={darkMode} />
        <StatCard value={doneTasks} label="Completed" color="#3fb950" darkMode={darkMode} />
        <StatCard value={activeTasks} label="Active" color="#58a6ff" darkMode={darkMode} />
        <StatCard
          value={failedTasks}
          label="Failed"
          color={failedTasks > 0 ? '#f85149' : mutedColor}
          darkMode={darkMode}
        />
        <StatCard value={agents.length} label="Agents" color="#a371f7" darkMode={darkMode} />
      </div>

      {/* Pipeline gates */}
      {phases.length > 0 && (
        <div style={{
          display: 'flex',
          alignItems: 'center',
          gap: 0,
          flexWrap: 'wrap',
          minWidth: 0,
          rowGap: 6,
        }}>
          {phases.map((p, i) => {
            const isComplete = p.progress === 100;
            const isActive = p.progress > 0 && p.progress < 100;
            const ringColor = isComplete ? '#3fb950' : isActive ? '#58a6ff' : '#30363d';
            const labelColor = isActive ? '#58a6ff' : isComplete ? '#3fb950' : mutedColor;
            return (
              <div key={p.phase} style={{ display: 'flex', alignItems: 'center' }}>
                <div
                  title={`${p.name}: ${p.progress}%`}
                  style={{
                    display: 'flex',
                    flexDirection: 'column',
                    alignItems: 'center',
                    padding: '5px 9px 4px',
                    borderRadius: 8,
                    background: isActive ? (darkMode ? '#1f6feb1c' : '#ddf4ff') :
                      isComplete ? (darkMode ? '#23863614' : '#dafbe1') : 'transparent',
                    border: `1px solid ${isActive ? '#58a6ff44' : isComplete ? '#3fb95030' : 'transparent'}`,
                    minWidth: 62,
                    cursor: 'default',
                    gap: 3,
                  }}
                >
                  <div style={{ position: 'relative', width: 28, height: 28 }}>
                    <MiniDonut
                      progress={p.progress}
                      color={ringColor}
                      size={28}
                      strokeWidth={3}
                      darkMode={darkMode}
                    />
                    <span style={{
                      position: 'absolute',
                      top: '50%',
                      left: '50%',
                      transform: 'translate(-50%, -50%)',
                      fontSize: isComplete ? 11 : 7,
                      fontWeight: 700,
                      color: labelColor,
                      fontVariantNumeric: 'tabular-nums',
                      lineHeight: 1,
                    }}>
                      {isComplete ? '✓' : p.progress}
                    </span>
                  </div>
                  <span style={{
                    fontSize: 8.5,
                    fontWeight: 700,
                    color: labelColor,
                    textTransform: 'uppercase',
                    letterSpacing: 0.4,
                    whiteSpace: 'nowrap',
                    maxWidth: 82,
                    overflow: 'hidden',
                    textOverflow: 'ellipsis',
                  }}>
                    {p.name}
                  </span>
                </div>
                {i < phases.length - 1 && (
                  <svg width="12" height="12" viewBox="0 0 12 12" style={{ flexShrink: 0, opacity: 0.5 }}>
                    <path
                      d="M4 2 L8 6 L4 10"
                      fill="none"
                      stroke={isComplete ? '#3fb950' : mutedColor}
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

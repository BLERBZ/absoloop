import { useState, useEffect } from 'react';
import { usePolling } from './hooks/usePolling';
import { AgentCards } from './components/AgentCards';
import { KanbanBoard } from './components/KanbanBoard';
import { ActivityFeed } from './components/ActivityFeed';
import { MetricsPanel } from './components/MetricsPanel';
import { GanttChart } from './components/GanttChart';

function formatElapsed(startTime: number): string {
  const s = Math.floor((Date.now() - startTime) / 1000);
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = s % 60;
  return `${h.toString().padStart(2, '0')}:${m.toString().padStart(2, '0')}:${sec.toString().padStart(2, '0')}`;
}

export default function App() {
  const { state, error, startTime, lastUpdate, connectionHealth } = usePolling(3000);
  const [darkMode, setDarkMode] = useState(true);
  const [activityFilter, setActivityFilter] = useState<string>('all');
  const [elapsed, setElapsed] = useState('00:00:00');

  // Update elapsed time every second
  useEffect(() => {
    const id = setInterval(() => setElapsed(formatElapsed(startTime)), 1000);
    return () => clearInterval(id);
  }, [startTime]);

  const tasks = state?.tasks?.tasks || [];
  const agents = state?.agents?.agents || [];
  const totalTasks = tasks.length;
  const doneTasks = tasks.filter(t => t.status === 'done').length;
  const overallProgress = totalTasks > 0 ? Math.round((doneTasks / totalTasks) * 100) : 0;

  const bg = darkMode ? '#0d1117' : '#ffffff';
  const borderColor = darkMode ? '#30363d' : '#d0d7de';
  const textColor = darkMode ? '#e6edf3' : '#1f2328';
  const mutedColor = darkMode ? '#7d8590' : '#656d76';
  const headerBg = darkMode ? '#010409' : '#f6f8fa';

  return (
    <div style={{
      height: '100vh',
      background: bg,
      color: textColor,
      fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", "Noto Sans", Helvetica, Arial, sans-serif',
      fontSize: 14,
      display: 'flex',
      flexDirection: 'column',
      overflow: 'hidden',
    }}>
      {/* Top Bar */}
      <header style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        padding: '8px 16px',
        borderBottom: `1px solid ${borderColor}`,
        background: headerBg,
        flexShrink: 0,
        gap: 12,
        flexWrap: 'wrap',
        minHeight: 44,
      }}>
        {/* Left: Brand */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <img
            src="/absoloop-logo-mark.png"
            alt="AbsoLoop"
            // Mark is ~2.3:1 landscape; size by height so 1.23× is visible
            // (a square box with object-fit:contain kept the glyph ~12px tall).
            height={34}
            style={{
              height: 34,          // 28 × 1.23
              width: 'auto',
              objectFit: 'contain',
              display: 'block',
              flexShrink: 0,
            }}
          />
          <div style={{
            display: 'flex',
            alignItems: 'baseline',
            gap: 8,
            borderLeft: `1px solid ${borderColor}`,
            paddingLeft: 12,
          }}>
            <h1 style={{
              margin: 0,
              fontSize: 17,
              fontWeight: 700,
              color: textColor,
              letterSpacing: '-0.02em',
              lineHeight: 1.2,
            }}>
              ZComb Kanban
            </h1>
            <span style={{
              color: mutedColor,
              fontSize: 12,
              fontWeight: 500,
              letterSpacing: '0.02em',
            }}>
              Monitor
            </span>
          </div>
        </div>

        {/* Right: Progress + Timer + Connection + Theme */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 20 }}>
          {/* Progress */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <div style={{
              width: 140,
              height: 6,
              borderRadius: 3,
              background: darkMode ? '#21262d' : '#e1e4e8',
              overflow: 'hidden'
            }}>
              <div style={{
                width: `${overallProgress}%`,
                height: '100%',
                borderRadius: 3,
                background: overallProgress === 100 ? '#3fb950' : '#58a6ff',
                transition: 'width 0.5s ease'
              }} />
            </div>
            <span style={{
              fontSize: 16,
              fontWeight: 800,
              color: overallProgress === 100 ? '#3fb950' : '#58a6ff',
              fontVariantNumeric: 'tabular-nums'
            }}>
              {overallProgress}% <span style={{ fontSize: 11, fontWeight: 500, color: mutedColor }}>Complete</span>
            </span>
          </div>

          {/* Timer */}
          <div style={{
            color: mutedColor,
            fontSize: 14,
            fontFamily: 'monospace',
            fontWeight: 600,
            letterSpacing: 1
          }}>
            {elapsed}
          </div>

          {/* Connection Health */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <div style={{
              width: 8,
              height: 8,
              borderRadius: '50%',
              background: connectionHealth === 'connected' ? '#3fb950' :
                connectionHealth === 'degraded' ? '#d29922' : '#f85149',
              boxShadow: `0 0 6px ${connectionHealth === 'connected' ? '#3fb950' :
                connectionHealth === 'degraded' ? '#d29922' : '#f85149'}`,
              animation: connectionHealth === 'connected' ? 'pulse-healthy 2.5s ease-in-out infinite' : 'pulse 1.5s infinite'
            }} />
            <span style={{ color: mutedColor, fontSize: 11 }}>
              {lastUpdate ? `${Math.round((Date.now() - lastUpdate) / 1000)}s ago` : 'connecting...'}
            </span>
          </div>

          {error && <span style={{ color: '#f85149', fontSize: 12 }}>Connection error</span>}

          {/* Theme Toggle */}
          <button
            onClick={() => setDarkMode(!darkMode)}
            style={{
              background: 'none',
              border: `1px solid ${borderColor}`,
              borderRadius: 6,
              padding: '4px 12px',
              cursor: 'pointer',
              color: textColor,
              fontSize: 12,
              fontWeight: 500,
              transition: 'background 0.2s'
            }}
            onMouseEnter={e => (e.currentTarget.style.background = darkMode ? '#21262d' : '#e1e4e8')}
            onMouseLeave={e => (e.currentTarget.style.background = 'none')}
          >
            {darkMode ? 'Light' : 'Dark'}
          </button>
        </div>
      </header>

      {/* Main Layout — sidebars scale with viewport, center fills remainder */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: 'clamp(120px, 16vw, 250px) 1fr clamp(140px, 18vw, 290px)',
        flex: 1,
        overflow: 'hidden',
        minHeight: 0,
      }}>
        {/* Left: Agent Cards — independent scroll */}
        <div style={{
          borderRight: `1px solid ${borderColor}`,
          overflow: 'hidden',
          display: 'flex',
          flexDirection: 'column',
          minHeight: 0,
        }}>
          <div style={{ padding: '14px 14px 0', flexShrink: 0 }}>
            <h3 style={{
              margin: '0 0 12px',
              fontSize: 12,
              fontWeight: 700,
              textTransform: 'uppercase',
              color: mutedColor,
              letterSpacing: 1.5
            }}>
              Agents
            </h3>
          </div>
          <div style={{ flex: 1, overflowY: 'auto', padding: '0 14px 14px', minHeight: 0 }}>
            <AgentCards agents={agents} darkMode={darkMode} />
          </div>
        </div>

        {/* Center: Task Board + Gantt — independent scroll */}
        <div style={{
          overflow: 'hidden',
          display: 'flex',
          flexDirection: 'column',
          minHeight: 0,
        }}>
          <KanbanBoard tasks={tasks} agents={agents} darkMode={darkMode} />
          <div style={{ flexShrink: 0, padding: '0 14px 14px', overflowX: 'auto' }}>
            <GanttChart tasks={tasks} metrics={state?.metrics} darkMode={darkMode} />
          </div>
        </div>

        {/* Right: Activity Feed — independent scroll */}
        <div style={{
          borderLeft: `1px solid ${borderColor}`,
          overflow: 'hidden',
          display: 'flex',
          flexDirection: 'column',
          minHeight: 0,
        }}>
          <div style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            padding: '14px 14px 10px',
            flexShrink: 0,
          }}>
            <h3 style={{
              margin: 0,
              fontSize: 12,
              fontWeight: 700,
              textTransform: 'uppercase',
              color: mutedColor,
              letterSpacing: 1.5
            }}>
              Activity Feed
            </h3>
            <select
              value={activityFilter}
              onChange={e => setActivityFilter(e.target.value)}
              style={{
                background: darkMode ? '#161b22' : '#ffffff',
                border: `1px solid ${borderColor}`,
                borderRadius: 6,
                padding: '3px 8px',
                color: textColor,
                fontSize: 11,
                cursor: 'pointer',
                outline: 'none'
              }}
            >
              <option value="all">All Agents</option>
              {agents.map(a => (
                <option key={a.id} value={a.id}>{a.name}</option>
              ))}
            </select>
          </div>
          <div style={{ flex: 1, overflowY: 'auto', padding: '0 14px 14px', minHeight: 0 }}>
            <ActivityFeed
              activity={state?.activity || []}
              filter={activityFilter}
              darkMode={darkMode}
              agents={agents}
            />
          </div>
        </div>
      </div>

      {/* Bottom: Metrics Bar */}
      <div style={{
        borderTop: `1px solid ${borderColor}`,
        padding: '12px 24px',
        background: headerBg,
        flexShrink: 0
      }}>
        <MetricsPanel
          tasks={tasks}
          agents={agents}
          metrics={state?.metrics}
          darkMode={darkMode}
        />
      </div>
    </div>
  );
}

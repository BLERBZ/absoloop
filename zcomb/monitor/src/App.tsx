import { useState, useEffect, useRef } from 'react';
import { usePolling } from './hooks/usePolling';
import { AgentCards } from './components/AgentCards';
import { KanbanBoard } from './components/KanbanBoard';
import { ActivityFeed } from './components/ActivityFeed';
import { MetricsPanel } from './components/MetricsPanel';
import { Timeline } from './components/Timeline';
import { MissionControls, triggerAction } from './components/MissionControls';
import { ObjectiveDropdown } from './components/ObjectiveDropdown';
import { matchesActivityFilter } from './components/ActivityFeed';

function formatElapsed(startTime: number): string {
  const s = Math.floor((Date.now() - startTime) / 1000);
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = s % 60;
  return `${h.toString().padStart(2, '0')}:${m.toString().padStart(2, '0')}:${sec.toString().padStart(2, '0')}`;
}

/** Chevron button used to collapse / expand the side panels */
function PanelToggle({ direction, onClick, mutedColor, title }: {
  direction: 'left' | 'right';
  onClick: () => void;
  mutedColor: string;
  title: string;
}) {
  return (
    <button
      type="button"
      className="panel-toggle"
      onClick={onClick}
      title={title}
      aria-label={title}
      style={{
        background: 'none',
        border: 'none',
        cursor: 'pointer',
        padding: 4,
        borderRadius: 6,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        color: mutedColor,
        flexShrink: 0,
      }}
    >
      <svg width="14" height="14" viewBox="0 0 16 16" style={{ display: 'block' }}>
        <path
          d={direction === 'left' ? 'M10.5 3 L5.5 8 L10.5 13' : 'M5.5 3 L10.5 8 L5.5 13'}
          fill="none"
          stroke="currentColor"
          strokeWidth="1.8"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
    </button>
  );
}

/** Slim vertical rail shown when a side panel is collapsed */
function CollapsedRail({ label, side, count, onExpand, darkMode, mutedColor, borderColor }: {
  label: string;
  side: 'left' | 'right';
  count: number;
  onExpand: () => void;
  darkMode: boolean;
  mutedColor: string;
  borderColor: string;
}) {
  return (
    <button
      type="button"
      className="collapsed-rail"
      onClick={onExpand}
      title={`Expand ${label}`}
      aria-label={`Expand ${label}`}
      style={{
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        gap: 10,
        padding: '12px 0',
        width: '100%',
        height: '100%',
        background: darkMode ? '#0d1117' : '#f6f8fa',
        border: 'none',
        borderLeft: side === 'right' ? `1px solid ${borderColor}` : 'none',
        borderRight: side === 'left' ? `1px solid ${borderColor}` : 'none',
        cursor: 'pointer',
        color: mutedColor,
      }}
    >
      <svg width="13" height="13" viewBox="0 0 16 16" style={{ display: 'block', flexShrink: 0 }}>
        <path
          d={side === 'left' ? 'M5.5 3 L10.5 8 L5.5 13' : 'M10.5 3 L5.5 8 L10.5 13'}
          fill="none"
          stroke="currentColor"
          strokeWidth="1.8"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
      {count > 0 && (
        <span style={{
          fontSize: 9,
          fontWeight: 700,
          background: darkMode ? '#21262d' : '#e1e4e8',
          color: mutedColor,
          borderRadius: 8,
          padding: '1px 5px',
          fontVariantNumeric: 'tabular-nums',
        }}>
          {count}
        </span>
      )}
      <span style={{
        writingMode: 'vertical-rl',
        fontSize: 10,
        fontWeight: 700,
        textTransform: 'uppercase',
        letterSpacing: 1.5,
        color: mutedColor,
      }}>
        {label}
      </span>
    </button>
  );
}

export default function App() {
  const {
    state, error, startTime, lastUpdate, connectionHealth,
    runEpoch, markRunRestarting,
  } = usePolling(3000);
  const [darkMode, setDarkMode] = useState(true);
  const [activityFilter, setActivityFilter] = useState<string>('focused');
  const [elapsed, setElapsed] = useState('00:00:00');
  const [agentsOpen, setAgentsOpen] = useState(() => localStorage.getItem('zc-panel-agents') !== '0');
  const [feedOpen, setFeedOpen] = useState(() => localStorage.getItem('zc-panel-feed') !== '0');
  const [objectiveCopied, setObjectiveCopied] = useState(false);
  const [extendMode, setExtendMode] = useState(false);
  const [extendNote, setExtendNote] = useState('');
  const [extendBusy, setExtendBusy] = useState(false);
  const [extendError, setExtendError] = useState<string | null>(null);
  const extendInputRef = useRef<HTMLTextAreaElement | null>(null);

  const toggleAgents = () => setAgentsOpen(open => {
    localStorage.setItem('zc-panel-agents', open ? '0' : '1');
    return !open;
  });
  const toggleFeed = () => setFeedOpen(open => {
    localStorage.setItem('zc-panel-feed', open ? '0' : '1');
    return !open;
  });

  // Reset activity filter when a new run/project identity arrives.
  useEffect(() => {
    setActivityFilter('focused');
    setExtendMode(false);
    setExtendNote('');
    setExtendError(null);
  }, [runEpoch]);

  useEffect(() => {
    if (!extendMode) return;
    const id = window.setTimeout(() => {
      extendInputRef.current?.focus();
      extendInputRef.current?.select();
    }, 40);
    return () => window.clearTimeout(id);
  }, [extendMode]);

  // Update elapsed time every second
  useEffect(() => {
    const id = setInterval(() => setElapsed(formatElapsed(startTime)), 1000);
    return () => clearInterval(id);
  }, [startTime]);

  const tasks = state?.tasks?.tasks || [];
  const agents = state?.agents?.agents || [];
  const metrics = state?.metrics;
  const awaitingRun = Boolean(metrics?.awaitingRun);
  const objective = (metrics?.objective || '').trim();
  const objectiveHistory = metrics?.objectiveHistory || [];
  const latestContinuation = [...objectiveHistory]
    .reverse()
    .find(e => e.kind === 'continuation')?.text;
  const displayedObjective = (
    metrics?.displayedObjective || latestContinuation || objective
  ).trim();
  const projectName = (metrics?.projectName || '').trim();
  const totalTasks = tasks.length;
  const doneTasks = tasks.filter(t => t.status === 'done').length;
  const overallProgress = awaitingRun
    ? 0
    : (totalTasks > 0 ? Math.round((doneTasks / totalTasks) * 100) : 0);

  const bg = darkMode ? '#0d1117' : '#ffffff';
  const borderColor = darkMode ? '#30363d' : '#d0d7de';
  const textColor = darkMode ? '#e6edf3' : '#1f2328';
  const mutedColor = darkMode ? '#7d8590' : '#656d76';
  const headerBg = darkMode ? '#010409' : '#f6f8fa';
  const showObjectiveRow = extendMode || awaitingRun
    || Boolean(displayedObjective || objective || projectName);

  const openExtendEditor = () => {
    setExtendMode(true);
    setExtendError(null);
    setExtendNote('');
  };

  const cancelExtend = () => {
    if (extendBusy) return;
    setExtendMode(false);
    setExtendNote('');
    setExtendError(null);
  };

  const confirmExtend = async () => {
    const note = extendNote.trim();
    if (!note) {
      setExtendError('Enter a continuation objective for the follow-on run.');
      extendInputRef.current?.focus();
      return;
    }
    setExtendBusy(true);
    setExtendError(null);
    try {
      const result = await triggerAction('extend', { note });
      if (!result.ok) {
        setExtendError(result.message);
        return;
      }
      setExtendMode(false);
      setExtendNote('');
      markRunRestarting();
    } catch (err: any) {
      setExtendError(err?.message || 'Failed to start extend');
    } finally {
      setExtendBusy(false);
    }
  };

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
        {/* Left: Brand + mission controls */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
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
          <MissionControls
            metrics={metrics}
            darkMode={darkMode}
            borderColor={borderColor}
            textColor={textColor}
            mutedColor={mutedColor}
            extendMode={extendMode}
            onRequestExtend={openExtendEditor}
            onRunRestarting={markRunRestarting}
          />
        </div>

        {/* Right: Progress + Timer + Connection + Theme */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 'clamp(10px, 1.5vw, 20px)', flexWrap: 'wrap', minWidth: 0 }}>
          {/* Progress */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <div style={{
              width: 'clamp(70px, 10vw, 140px)',
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

      {/* Objective / new-run banner — editable + highlighted during Extend */}
      {showObjectiveRow && (
        <div
          className={extendMode ? 'extend-objective-banner' : undefined}
          style={{
            display: 'flex',
            alignItems: extendMode ? 'stretch' : 'center',
            gap: 12,
            padding: extendMode ? '10px 16px 12px' : '8px 16px',
            borderBottom: `1px solid ${extendMode
              ? (darkMode ? '#d2992266' : '#bf8700aa')
              : borderColor}`,
            background: extendMode
              ? (darkMode ? '#3d2e0a' : '#fff8c5')
              : awaitingRun
                ? (darkMode ? '#1f6feb22' : '#ddf4ff')
                : headerBg,
            flexShrink: 0,
            flexWrap: 'wrap',
            minHeight: extendMode ? 72 : 36,
            boxShadow: extendMode
              ? (darkMode
                ? 'inset 3px 0 0 #d29922, 0 0 0 1px #d2992233'
                : 'inset 3px 0 0 #bf8700, 0 0 0 1px #bf870033')
              : undefined,
          }}
        >
          {!extendMode && displayedObjective && (
            <button
              type="button"
              onClick={async () => {
                try {
                  await navigator.clipboard.writeText(displayedObjective);
                  setObjectiveCopied(true);
                  window.setTimeout(() => setObjectiveCopied(false), 1500);
                } catch {
                  // Clipboard may be unavailable in insecure contexts
                }
              }}
              title={objectiveCopied ? 'Copied!' : 'Copy displayed objective'}
              aria-label={objectiveCopied ? 'Copied!' : 'Copy displayed objective'}
              style={{
                background: 'none',
                border: 'none',
                cursor: 'pointer',
                padding: 4,
                borderRadius: 6,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                color: objectiveCopied ? '#3fb950' : mutedColor,
                flexShrink: 0,
              }}
              onMouseEnter={e => {
                if (!objectiveCopied) e.currentTarget.style.color = textColor;
              }}
              onMouseLeave={e => {
                if (!objectiveCopied) e.currentTarget.style.color = mutedColor;
              }}
            >
              {objectiveCopied ? (
                <svg width="14" height="14" viewBox="0 0 16 16" style={{ display: 'block' }}>
                  <path
                    d="M3.5 8.5 L6.5 11.5 L12.5 4.5"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="1.8"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  />
                </svg>
              ) : (
                <svg width="14" height="14" viewBox="0 0 16 16" style={{ display: 'block' }}>
                  <rect
                    x="5.5"
                    y="5.5"
                    width="8"
                    height="8"
                    rx="1.5"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="1.4"
                  />
                  <path
                    d="M10.5 5.5 V4 A1.5 1.5 0 0 0 9 2.5 H4 A1.5 1.5 0 0 0 2.5 4 V9 A1.5 1.5 0 0 0 4 10.5 H5.5"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="1.4"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  />
                </svg>
              )}
            </button>
          )}
          {extendMode ? (
            <div style={{
              display: 'flex',
              flexDirection: 'column',
              gap: 8,
              flex: 1,
              minWidth: 240,
            }}>
              <div style={{
                display: 'flex',
                alignItems: 'center',
                gap: 10,
                flexWrap: 'wrap',
              }}>
                <span style={{
                  fontSize: 11,
                  fontWeight: 800,
                  letterSpacing: '0.08em',
                  textTransform: 'uppercase',
                  color: darkMode ? '#e3b341' : '#9a6700',
                  whiteSpace: 'nowrap',
                }}>
                  Extend · continuation objective
                </span>
                {projectName && (
                  <span style={{
                    fontSize: 12,
                    fontWeight: 600,
                    color: textColor,
                    whiteSpace: 'nowrap',
                  }}>
                    {projectName}
                  </span>
                )}
                {displayedObjective && (
                  <span style={{
                    fontSize: 11,
                    color: mutedColor,
                    overflow: 'hidden',
                    textOverflow: 'ellipsis',
                    whiteSpace: 'nowrap',
                    minWidth: 0,
                    flex: 1,
                  }}
                    title={`Current: ${displayedObjective}`}
                  >
                    current: {displayedObjective}
                  </span>
                )}
              </div>
              <div style={{
                display: 'flex',
                alignItems: 'flex-start',
                gap: 8,
                flexWrap: 'wrap',
              }}>
                <textarea
                  ref={extendInputRef}
                  value={extendNote}
                  disabled={extendBusy}
                  rows={2}
                  placeholder="What should the follow-on run accomplish?"
                  onChange={e => {
                    setExtendNote(e.target.value);
                    if (extendError) setExtendError(null);
                  }}
                  onKeyDown={e => {
                    if (e.key === 'Escape') {
                      e.preventDefault();
                      cancelExtend();
                    }
                    if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) {
                      e.preventDefault();
                      void confirmExtend();
                    }
                  }}
                  aria-label="Extend continuation objective"
                  style={{
                    flex: 1,
                    minWidth: 220,
                    resize: 'vertical',
                    minHeight: 44,
                    maxHeight: 120,
                    padding: '8px 10px',
                    borderRadius: 8,
                    border: `1px solid ${darkMode ? '#d29922' : '#bf8700'}`,
                    background: darkMode ? '#0d1117' : '#ffffff',
                    color: textColor,
                    fontSize: 13,
                    fontFamily: 'inherit',
                    lineHeight: 1.4,
                    outline: 'none',
                    boxShadow: darkMode
                      ? '0 0 0 3px #d2992233'
                      : '0 0 0 3px #bf870033',
                  }}
                />
                <div style={{
                  display: 'flex',
                  flexDirection: 'column',
                  gap: 6,
                  flexShrink: 0,
                }}>
                  <button
                    type="button"
                    disabled={extendBusy}
                    onClick={() => void confirmExtend()}
                    style={{
                      borderRadius: 6,
                      padding: '7px 14px',
                      fontSize: 12,
                      fontWeight: 700,
                      border: '1px solid #bf8700',
                      background: '#bf8700',
                      color: '#0d1117',
                      cursor: extendBusy ? 'wait' : 'pointer',
                      opacity: extendBusy ? 0.7 : 1,
                      whiteSpace: 'nowrap',
                    }}
                  >
                    {extendBusy ? 'Starting…' : 'Start extend'}
                  </button>
                  <button
                    type="button"
                    disabled={extendBusy}
                    onClick={cancelExtend}
                    style={{
                      borderRadius: 6,
                      padding: '6px 14px',
                      fontSize: 12,
                      fontWeight: 600,
                      border: `1px solid ${borderColor}`,
                      background: 'none',
                      color: mutedColor,
                      cursor: extendBusy ? 'not-allowed' : 'pointer',
                      whiteSpace: 'nowrap',
                    }}
                  >
                    Cancel
                  </button>
                </div>
              </div>
              <div style={{
                display: 'flex',
                alignItems: 'center',
                gap: 10,
                flexWrap: 'wrap',
              }}>
                <span style={{ fontSize: 11, color: mutedColor }}>
                  ⌘/Ctrl+Enter to start · Esc to cancel · becomes a definition-of-done item
                </span>
                {extendError && (
                  <span style={{ fontSize: 11, color: '#f85149' }} title={extendError}>
                    {extendError}
                  </span>
                )}
              </div>
            </div>
          ) : (
            <>
              {awaitingRun && (
                <span style={{
                  fontSize: 11,
                  fontWeight: 700,
                  letterSpacing: '0.06em',
                  textTransform: 'uppercase',
                  color: '#58a6ff',
                  whiteSpace: 'nowrap',
                }}>
                  Waiting for new run
                </span>
              )}
              {projectName && (
                <span style={{
                  fontSize: 12,
                  fontWeight: 600,
                  color: textColor,
                  whiteSpace: 'nowrap',
                }}>
                  {projectName}
                </span>
              )}
              {displayedObjective && (
                <ObjectiveDropdown
                  key={runEpoch}
                  displayedText={displayedObjective}
                  history={objectiveHistory.length > 0
                    ? objectiveHistory
                    : [{ kind: 'objective', text: displayedObjective }]}
                  darkMode={darkMode}
                  borderColor={borderColor}
                  textColor={textColor}
                  mutedColor={mutedColor}
                />
              )}
              {metrics?.loopId && (
                <span style={{
                  fontSize: 11,
                  fontFamily: 'monospace',
                  color: mutedColor,
                  whiteSpace: 'nowrap',
                }}>
                  {metrics.loopId}
                </span>
              )}
            </>
          )}
        </div>
      )}

      {/* Main Layout — collapsible sidebars, center fills remainder */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: `${agentsOpen ? 'clamp(160px, 16vw, 260px)' : '34px'} minmax(0, 1fr) ${feedOpen ? 'clamp(180px, 18vw, 300px)' : '34px'}`,
        flex: 1,
        overflow: 'hidden',
        minHeight: 0,
        transition: 'grid-template-columns 0.25s ease',
      }}>
        {/* Left: Agent Cards — collapsible, independent scroll */}
        {agentsOpen ? (
          <div style={{
            borderRight: `1px solid ${borderColor}`,
            overflow: 'hidden',
            display: 'flex',
            flexDirection: 'column',
            minHeight: 0,
            minWidth: 0,
          }}>
            <div style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              padding: '12px 10px 10px 14px',
              flexShrink: 0,
              gap: 6,
            }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 7, minWidth: 0 }}>
                <h3 style={{
                  margin: 0,
                  fontSize: 12,
                  fontWeight: 700,
                  textTransform: 'uppercase',
                  color: mutedColor,
                  letterSpacing: 1.5,
                  whiteSpace: 'nowrap',
                  overflow: 'hidden',
                  textOverflow: 'ellipsis',
                }}>
                  Agents
                </h3>
                {agents.length > 0 && (
                  <span style={{
                    fontSize: 9,
                    fontWeight: 700,
                    background: darkMode ? '#21262d' : '#eaeef2',
                    color: mutedColor,
                    borderRadius: 8,
                    padding: '1px 6px',
                    fontVariantNumeric: 'tabular-nums',
                    flexShrink: 0,
                  }}>
                    {agents.length}
                  </span>
                )}
              </div>
              <PanelToggle
                direction="left"
                onClick={toggleAgents}
                mutedColor={mutedColor}
                title="Collapse agents panel"
              />
            </div>
            <div style={{ flex: 1, overflowY: 'auto', padding: '0 14px 14px', minHeight: 0 }}>
              <AgentCards agents={agents} darkMode={darkMode} />
            </div>
          </div>
        ) : (
          <CollapsedRail
            label="Agents"
            side="left"
            count={agents.length}
            onExpand={toggleAgents}
            darkMode={darkMode}
            mutedColor={mutedColor}
            borderColor={borderColor}
          />
        )}

        {/* Center: Task Board + Timeline — independent scroll */}
        <div style={{
          overflow: 'hidden',
          display: 'flex',
          flexDirection: 'column',
          minHeight: 0,
          minWidth: 0,
        }}>
          <KanbanBoard key={runEpoch} tasks={tasks} agents={agents} darkMode={darkMode} />
          <div style={{ flexShrink: 0, padding: '2px 14px 8px', minWidth: 0 }}>
            <Timeline tasks={tasks} metrics={metrics} darkMode={darkMode} />
          </div>
        </div>

        {/* Right: Activity Feed — collapsible, independent scroll */}
        {feedOpen ? (
          <div style={{
            borderLeft: `1px solid ${borderColor}`,
            overflow: 'hidden',
            display: 'flex',
            flexDirection: 'column',
            minHeight: 0,
            minWidth: 0,
          }}>
            <div style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              padding: '12px 14px 10px 10px',
              flexShrink: 0,
              gap: 6,
              flexWrap: 'wrap',
            }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 4, minWidth: 0 }}>
                <PanelToggle
                  direction="right"
                  onClick={toggleFeed}
                  mutedColor={mutedColor}
                  title="Collapse activity feed"
                />
                <h3 style={{
                  margin: 0,
                  fontSize: 12,
                  fontWeight: 700,
                  textTransform: 'uppercase',
                  color: mutedColor,
                  letterSpacing: 1.5,
                  whiteSpace: 'nowrap',
                }}>
                  Activity
                </h3>
              </div>
              <select
                value={activityFilter}
                onChange={e => setActivityFilter(e.target.value)}
                title="Focused shows CLI blue agent messages (say); All shows every event"
                style={{
                  background: darkMode ? '#161b22' : '#ffffff',
                  border: `1px solid ${borderColor}`,
                  borderRadius: 6,
                  padding: '3px 6px',
                  color: textColor,
                  fontSize: 11,
                  cursor: 'pointer',
                  outline: 'none',
                  maxWidth: 120,
                  flexShrink: 1,
                  minWidth: 0,
                }}
              >
                <option value="focused">Focused</option>
                <option value="all">All messages</option>
                {agents.length > 0 && (
                  <option value="__agents__" disabled>
                    ── Agents ──
                  </option>
                )}
                {agents.map(a => (
                  <option key={a.id} value={a.id}>{a.name}</option>
                ))}
              </select>
            </div>
            <div style={{ flex: 1, overflowY: 'auto', padding: '0 14px 14px', minHeight: 0 }}>
              <ActivityFeed
                key={runEpoch}
                activity={state?.activity || []}
                filter={activityFilter}
                darkMode={darkMode}
                agents={agents}
              />
            </div>
          </div>
        ) : (
          <CollapsedRail
            label="Activity"
            side="right"
            count={(state?.activity || []).filter(a => matchesActivityFilter(a, activityFilter)).length}
            onExpand={toggleFeed}
            darkMode={darkMode}
            mutedColor={mutedColor}
            borderColor={borderColor}
          />
        )}
      </div>

      {/* Bottom: Metrics Bar */}
      <div style={{
        borderTop: `1px solid ${borderColor}`,
        padding: 'clamp(8px, 1vw, 12px) clamp(12px, 2vw, 24px)',
        background: headerBg,
        flexShrink: 0
      }}>
        <MetricsPanel
          tasks={tasks}
          agents={agents}
          metrics={metrics}
          darkMode={darkMode}
        />
      </div>
    </div>
  );
}

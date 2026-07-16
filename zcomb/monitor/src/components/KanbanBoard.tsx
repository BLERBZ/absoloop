import { useState, useRef, useEffect, useCallback, useMemo } from 'react';
import type { Task, Agent } from '../hooks/usePolling';

const columns = [
  { key: 'inbox', label: 'Inbox', icon: '○', color: '#7d8590', glow: '#7d859020' },
  { key: 'assigned', label: 'Assigned', icon: '◎', color: '#d29922', glow: '#d2992218' },
  { key: 'in_progress', label: 'In Progress', icon: '◉', color: '#58a6ff', glow: '#58a6ff18' },
  { key: 'review', label: 'Review', icon: '◈', color: '#a371f7', glow: '#a371f718' },
  { key: 'done', label: 'Done', icon: '✓', color: '#3fb950', glow: '#3fb95018' },
  { key: 'failed', label: 'Failed', icon: '✕', color: '#f85149', glow: '#f8514918' }
] as const;

const priorityConfig: Record<string, { color: string; label: string; bg: string }> = {
  high: { color: '#f85149', label: 'Hi', bg: '#f8514915' },
  medium: { color: '#d29922', label: 'Md', bg: '#d2992215' },
  low: { color: '#7d8590', label: 'Lo', bg: '#7d859015' }
};

function getInitials(name: string): string {
  return name.split(' ').map(w => w[0]).join('').slice(0, 2).toUpperCase();
}

function getAvatarColor(name: string): string {
  const colors = ['#58a6ff', '#a371f7', '#3fb950', '#d29922', '#f0883e', '#f85149', '#db61a2', '#79c0ff'];
  let hash = 0;
  for (let i = 0; i < name.length; i++) hash = name.charCodeAt(i) + ((hash << 5) - hash);
  return colors[Math.abs(hash) % colors.length];
}

/** Animated badge that pops when count changes */
function ColumnBadge({ count, color, px }: { count: number; color: string; px: (base: number, min?: number) => number }) {
  const prevCount = useRef(count);
  const [pop, setPop] = useState(false);

  useEffect(() => {
    if (count !== prevCount.current) {
      prevCount.current = count;
      setPop(true);
      const t = setTimeout(() => setPop(false), 400);
      return () => clearTimeout(t);
    }
  }, [count]);

  return (
    <span
      className={`kanban-badge${pop ? ' kanban-badge-pop' : ''}`}
      style={{
        fontSize: px(9),
        fontWeight: 700,
        background: `${color}18`,
        color: color,
        padding: `0 ${px(5)}px`,
        borderRadius: px(8),
        lineHeight: `${px(16)}px`,
        flexShrink: 0,
        display: 'inline-flex',
        alignItems: 'center',
        justifyContent: 'center',
        minWidth: px(16),
      }}
    >
      {count}
    </span>
  );
}

/** Highlights matching search text within a string */
function HighlightText({ text, query, color }: { text: string; query: string; color: string }) {
  if (!query) return <>{text}</>;
  const idx = text.toLowerCase().indexOf(query.toLowerCase());
  if (idx === -1) return <>{text}</>;
  return (
    <>
      {text.slice(0, idx)}
      <mark style={{
        background: `${color}33`,
        color: 'inherit',
        borderRadius: 2,
        padding: '0 1px',
      }}>
        {text.slice(idx, idx + query.length)}
      </mark>
      {text.slice(idx + query.length)}
    </>
  );
}

export function KanbanBoard({ tasks, agents, darkMode }: { tasks: Task[]; agents: Agent[]; darkMode: boolean }) {
  const [searchQuery, setSearchQuery] = useState('');
  const [phaseFilter, setPhaseFilter] = useState<string>('all');
  const searchRef = useRef<HTMLInputElement>(null);
  const gridRef = useRef<HTMLDivElement>(null);
  const [containerW, setContainerW] = useState(1200);

  const borderColor = darkMode ? '#30363d' : '#d0d7de';
  const mutedColor = darkMode ? '#7d8590' : '#656d76';
  const textColor = darkMode ? '#e6edf3' : '#1f2328';
  const subText = darkMode ? '#8b949e' : '#57606a';

  const agentMap = new Map(agents.map(a => [a.id, a.name]));

  // Measure container width for proportional scaling
  useEffect(() => {
    const el = gridRef.current;
    if (!el) return;
    const ro = new ResizeObserver(entries => {
      const w = entries[0].contentRect.width;
      if (w > 0) setContainerW(w);
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  // Scale factor: 1.0 at >=1100px, proportionally smaller below, floor at 0.42
  const s = Math.min(1, Math.max(0.42, containerW / 1100));

  // Scaled pixel helper — all sizes go through this
  const px = useCallback((base: number, min = 1) => Math.max(min, Math.round(base * s)), [s]);

  // Keyboard shortcut
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'f' || e.key === 'F') {
        const tag = (e.target as HTMLElement)?.tagName;
        if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return;
        e.preventDefault();
        searchRef.current?.focus();
      }
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, []);

  const uniquePhases = Array.from(new Set(tasks.map(t => t.phase))).sort((a, b) => a - b);

  const filteredTasks = tasks.filter(t => {
    const matchesSearch = searchQuery === '' || t.title.toLowerCase().includes(searchQuery.toLowerCase());
    const matchesPhase = phaseFilter === 'all' || t.phase === Number(phaseFilter);
    return matchesSearch && matchesPhase;
  });

  return (
    <div style={{
      display: 'flex',
      flexDirection: 'column',
      flex: 1,
      minHeight: 0,
      overflow: 'hidden',
    }}>
      {/* Header toolbar — scales with container */}
      <div style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        padding: `${px(10)}px ${px(12)}px ${px(8)}px`,
        gap: px(6),
        flexShrink: 0,
        flexWrap: 'wrap',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: px(6) }}>
          <h3 style={{
            margin: 0,
            fontSize: px(12),
            fontWeight: 700,
            textTransform: 'uppercase',
            color: mutedColor,
            letterSpacing: px(1),
            whiteSpace: 'nowrap',
          }}>
            Task Board
          </h3>
          <span style={{
            fontSize: px(10),
            color: subText,
            fontWeight: 500,
            background: darkMode ? '#21262d' : '#eaeef2',
            padding: `${px(1)}px ${px(6)}px`,
            borderRadius: px(8),
          }}>
            {filteredTasks.length}
          </span>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: px(5) }}>
          <div style={{ position: 'relative' }}>
            <svg
              width={px(12)} height={px(12)} viewBox="0 0 16 16"
              style={{
                position: 'absolute',
                left: px(7),
                top: '50%',
                transform: 'translateY(-50%)',
                pointerEvents: 'none',
              }}
            >
              <path
                d="M11.5 7a4.5 4.5 0 1 1-9 0 4.5 4.5 0 0 1 9 0Zm-.82 4.74a6 6 0 1 1 1.06-1.06l3.04 3.04a.75.75 0 0 1-1.06 1.06l-3.04-3.04Z"
                fill={mutedColor}
                fillRule="evenodd"
              />
            </svg>
            <input
              ref={searchRef}
              type="text"
              placeholder="Search..."
              value={searchQuery}
              onChange={e => setSearchQuery(e.target.value)}
              style={{
                background: darkMode ? '#0d1117' : '#ffffff',
                border: `1px solid ${borderColor}`,
                borderRadius: px(6),
                padding: `${px(4)}px ${px(8)}px ${px(4)}px ${px(24)}px`,
                color: textColor,
                fontSize: px(11),
                outline: 'none',
                width: px(120),
                transition: 'border-color 0.2s ease, box-shadow 0.2s ease',
              }}
              onFocus={e => {
                e.currentTarget.style.borderColor = '#58a6ff';
                e.currentTarget.style.boxShadow = '0 0 0 2px #58a6ff22';
              }}
              onBlur={e => {
                e.currentTarget.style.borderColor = borderColor;
                e.currentTarget.style.boxShadow = 'none';
              }}
            />
          </div>
          <select
            value={phaseFilter}
            onChange={e => setPhaseFilter(e.target.value)}
            style={{
              background: darkMode ? '#0d1117' : '#ffffff',
              border: `1px solid ${borderColor}`,
              borderRadius: px(6),
              padding: `${px(4)}px ${px(6)}px`,
              color: textColor,
              fontSize: px(11),
              cursor: 'pointer',
              outline: 'none',
            }}
          >
            <option value="all">All</option>
            {uniquePhases.map(p => (
              <option key={p} value={p}>P{p}</option>
            ))}
          </select>
        </div>
      </div>

      {/* Column grid — always fits, never overflows horizontally */}
      <div ref={gridRef} style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(6, 1fr)',
        gap: px(6),
        flex: 1,
        minHeight: 0,
        overflow: 'hidden',
        padding: `0 ${px(10)}px ${px(10)}px`,
      }}>
        {columns.map(col => {
          const colTasks = filteredTasks.filter(t => t.status === col.key);
          return (
            <div key={col.key} className="kanban-column" style={{
              background: darkMode
                ? `linear-gradient(180deg, ${col.glow} 0%, #0d1117 100%)`
                : `linear-gradient(180deg, ${col.glow} 0%, #f6f8fa 100%)`,
              borderRadius: px(8),
              display: 'flex',
              flexDirection: 'column',
              minHeight: 0,
              border: `1px solid ${darkMode ? '#1c2128' : '#e1e4e8'}`,
              overflow: 'hidden',
            }}>
              {/* Column header — pinned, never scrolls */}
              <div style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                padding: `${px(7)}px ${px(7)}px ${px(5)}px`,
                borderBottom: `2px solid ${col.color}20`,
                flexShrink: 0,
                gap: px(3),
              }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: px(4), minWidth: 0, overflow: 'hidden' }}>
                  <span style={{
                    fontSize: px(11),
                    color: col.color,
                    lineHeight: 1,
                    fontWeight: 700,
                    flexShrink: 0,
                  }}>
                    {col.icon}
                  </span>
                  <span style={{
                    fontSize: px(10),
                    fontWeight: 700,
                    color: col.color,
                    letterSpacing: 0.2,
                    whiteSpace: 'nowrap',
                    overflow: 'hidden',
                    textOverflow: 'ellipsis',
                  }}>
                    {col.label}
                  </span>
                </div>
                <ColumnBadge count={colTasks.length} color={col.color} px={px} />
              </div>

              {/* Cards area — scrolls vertically within column */}
              <div className="kanban-card-scroll" style={{
                flex: 1,
                overflowY: 'auto',
                padding: px(5),
                minHeight: 0,
                display: 'flex',
                flexDirection: 'column',
                gap: px(5),
              }}>
                {colTasks.map(task => {
                  const priority = priorityConfig[task.priority] || priorityConfig.low;
                  const assigneeName = task.assignee ? (agentMap.get(task.assignee) || task.assignee) : '—';
                  const avatarColor = getAvatarColor(assigneeName);

                  return (
                    <div key={task.id} className="kanban-task-card" style={{
                      background: darkMode
                        ? 'linear-gradient(135deg, #161b22 0%, #1c2128 100%)'
                        : 'linear-gradient(135deg, #ffffff 0%, #f9fafb 100%)',
                      border: `1px solid ${darkMode ? '#30363d' : '#d0d7de'}`,
                      borderRadius: px(7),
                      padding: 0,
                      cursor: 'default',
                      overflow: 'hidden',
                      position: 'relative',
                      flexShrink: 0,
                    }}>
                      {/* Left accent bar */}
                      <div style={{
                        position: 'absolute',
                        left: 0,
                        top: 0,
                        bottom: 0,
                        width: Math.max(2, px(3)),
                        background: `linear-gradient(180deg, ${col.color}, ${col.color}80)`,
                        borderRadius: `${px(7)}px 0 0 ${px(7)}px`,
                      }} />

                      <div style={{ padding: `${px(6)}px ${px(7)}px ${px(6)}px ${px(9)}px` }}>
                        {/* Title */}
                        <div style={{
                          fontWeight: 600,
                          lineHeight: 1.35,
                          color: textColor,
                          fontSize: px(10, 7),
                          marginBottom: px(5),
                          wordBreak: 'break-word',
                        }}>
                          <HighlightText
                            text={task.title.replace(/^Phase \d+: /, '')}
                            query={searchQuery}
                            color="#58a6ff"
                          />
                        </div>

                        {/* Meta row */}
                        <div style={{
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'space-between',
                          gap: px(3),
                        }}>
                          {/* Assignee */}
                          <div style={{
                            display: 'flex',
                            alignItems: 'center',
                            gap: px(3),
                            flex: 1,
                            minWidth: 0,
                          }}>
                            <div style={{
                              width: px(14, 8),
                              height: px(14, 8),
                              borderRadius: '50%',
                              background: task.assignee
                                ? `linear-gradient(135deg, ${avatarColor}, ${avatarColor}cc)`
                                : darkMode ? '#21262d' : '#e1e4e8',
                              display: 'flex',
                              alignItems: 'center',
                              justifyContent: 'center',
                              fontSize: px(6, 4),
                              fontWeight: 700,
                              color: '#fff',
                              flexShrink: 0,
                            }}>
                              {task.assignee ? getInitials(assigneeName) : '?'}
                            </div>
                            <span style={{
                              fontSize: px(8.5, 6),
                              color: subText,
                              whiteSpace: 'nowrap',
                              overflow: 'hidden',
                              textOverflow: 'ellipsis',
                            }}>
                              {assigneeName}
                            </span>
                          </div>

                          {/* Badges */}
                          <div style={{
                            display: 'flex',
                            alignItems: 'center',
                            gap: px(2),
                            flexShrink: 0,
                          }}>
                            <span style={{
                              fontSize: px(7.5, 5),
                              fontWeight: 700,
                              color: priority.color,
                              background: priority.bg,
                              padding: `0 ${px(4)}px`,
                              borderRadius: px(3),
                              textTransform: 'uppercase',
                              lineHeight: `${px(13, 8)}px`,
                            }}>
                              {priority.label}
                            </span>
                            <span style={{
                              fontSize: px(7.5, 5),
                              fontWeight: 700,
                              background: darkMode
                                ? 'linear-gradient(135deg, #21262d, #30363d)'
                                : 'linear-gradient(135deg, #e1e4e8, #eaeef2)',
                              color: subText,
                              padding: `0 ${px(4)}px`,
                              borderRadius: px(3),
                              lineHeight: `${px(13, 8)}px`,
                            }}>
                              P{task.phase}
                            </span>
                          </div>
                        </div>

                        {/* Dependencies — compact */}
                        {task.dependencies.length > 0 && (
                          <div style={{
                            display: 'flex',
                            alignItems: 'center',
                            gap: px(2),
                            marginTop: px(4),
                            flexWrap: 'wrap',
                          }}>
                            <span style={{
                              fontSize: px(7, 5),
                              color: mutedColor,
                              opacity: 0.6,
                              flexShrink: 0,
                            }}>
                              dep:
                            </span>
                            {task.dependencies.slice(0, 3).map(dep => (
                              <span key={dep} style={{
                                fontSize: px(7, 5),
                                color: mutedColor,
                                background: darkMode ? '#161b2280' : '#f6f8fa',
                                border: `1px solid ${darkMode ? '#21262d' : '#e1e4e8'}`,
                                padding: `0 ${px(3)}px`,
                                borderRadius: px(2),
                                lineHeight: `${px(12, 8)}px`,
                                fontFamily: 'monospace',
                              }}>
                                {dep.replace('task-', '#')}
                              </span>
                            ))}
                            {task.dependencies.length > 3 && (
                              <span style={{ fontSize: px(7, 5), color: mutedColor, opacity: 0.5 }}>
                                +{task.dependencies.length - 3}
                              </span>
                            )}
                          </div>
                        )}
                      </div>
                    </div>
                  );
                })}

                {colTasks.length === 0 && (
                  <div style={{
                    textAlign: 'center',
                    padding: `${px(16)}px ${px(4)}px`,
                    opacity: 0.3,
                  }}>
                    <div style={{ fontSize: px(16), color: mutedColor, marginBottom: px(2) }}>
                      {col.icon}
                    </div>
                    <div style={{ fontSize: px(8, 6), color: mutedColor }}>
                      No tasks
                    </div>
                  </div>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

import { useState, useRef, useEffect, useCallback, type ReactNode } from 'react';
import type { Task, Agent } from '../hooks/usePolling';

/** Zoom steps relative to the responsive baseline: −2 … 0 … +2. */
const ZOOM_MIN = -2;
const ZOOM_MAX = 2;
const ZOOM_FACTORS: Record<number, number> = {
  [-2]: 0.82,
  [-1]: 0.91,
  [0]: 1,
  [1]: 1.14,
  [2]: 1.28,
};
const ZOOM_STORAGE_KEY = 'zc-kanban-zoom';

function readStoredZoom(): number {
  try {
    const raw = localStorage.getItem(ZOOM_STORAGE_KEY);
    if (raw == null) return 0;
    const n = Number(raw);
    if (Number.isInteger(n) && n >= ZOOM_MIN && n <= ZOOM_MAX) return n;
  } catch {
    /* ignore */
  }
  return 0;
}

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

function ZoomButton({
  label,
  title,
  disabled,
  onClick,
  darkMode,
  borderColor,
  mutedColor,
  textColor,
  size,
}: {
  label: ReactNode;
  title: string;
  disabled: boolean;
  onClick: () => void;
  darkMode: boolean;
  borderColor: string;
  mutedColor: string;
  textColor: string;
  size: number;
}) {
  return (
    <button
      type="button"
      title={title}
      aria-label={title}
      disabled={disabled}
      onClick={onClick}
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        justifyContent: 'center',
        width: size,
        height: size,
        padding: 0,
        borderRadius: Math.max(4, Math.round(size * 0.28)),
        border: `1px solid ${borderColor}`,
        background: darkMode ? '#0d1117' : '#ffffff',
        color: disabled ? mutedColor : textColor,
        cursor: disabled ? 'not-allowed' : 'pointer',
        opacity: disabled ? 0.45 : 1,
        flexShrink: 0,
        lineHeight: 1,
      }}
    >
      {label}
    </button>
  );
}

export function KanbanBoard({ tasks, agents, darkMode }: { tasks: Task[]; agents: Agent[]; darkMode: boolean }) {
  const [searchQuery, setSearchQuery] = useState('');
  const [phaseFilter, setPhaseFilter] = useState<string>('all');
  const [zoomLevel, setZoomLevel] = useState(readStoredZoom);
  const searchRef = useRef<HTMLInputElement>(null);
  const gridRef = useRef<HTMLDivElement>(null);
  const [containerW, setContainerW] = useState(1200);

  const borderColor = darkMode ? '#30363d' : '#d0d7de';
  const mutedColor = darkMode ? '#7d8590' : '#656d76';
  const textColor = darkMode ? '#e6edf3' : '#1f2328';
  const subText = darkMode ? '#8b949e' : '#57606a';

  const agentMap = new Map(agents.map(a => [a.id, a.name]));

  useEffect(() => {
    try {
      localStorage.setItem(ZOOM_STORAGE_KEY, String(zoomLevel));
    } catch {
      /* ignore */
    }
  }, [zoomLevel]);

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

  // Larger baseline than before (1.12 at ≥1000px, floor 0.95) × operator zoom.
  // Narrow viewports scroll horizontally instead of crushing card type.
  const responsive = Math.min(1.12, Math.max(0.95, containerW / 1000));
  const s = responsive * (ZOOM_FACTORS[zoomLevel] ?? 1);

  // Scaled pixel helper — all sizes go through this
  const px = useCallback((base: number, min = 1) => Math.max(min, Math.round(base * s)), [s]);

  const zoomIn = useCallback(() => {
    setZoomLevel(z => Math.min(ZOOM_MAX, z + 1));
  }, []);
  const zoomOut = useCallback(() => {
    setZoomLevel(z => Math.max(ZOOM_MIN, z - 1));
  }, []);

  // Keyboard: f = search, =/+ = zoom in, - = zoom out
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement)?.tagName;
      if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return;
      if (e.key === 'f' || e.key === 'F') {
        e.preventDefault();
        searchRef.current?.focus();
        return;
      }
      if (e.key === '=' || e.key === '+') {
        e.preventDefault();
        zoomIn();
        return;
      }
      if (e.key === '-' || e.key === '_') {
        e.preventDefault();
        zoomOut();
      }
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [zoomIn, zoomOut]);

  const uniquePhases = Array.from(new Set(tasks.map(t => t.phase))).sort((a, b) => a - b);

  const filteredTasks = tasks.filter(t => {
    const q = searchQuery.toLowerCase();
    const matchesSearch = q === ''
      || t.title.toLowerCase().includes(q)
      || (t.description || '').toLowerCase().includes(q)
      || (t.kind || '').toLowerCase().includes(q)
      || t.id.toLowerCase().includes(q);
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
                width: px(140),
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
          {/* Zoom −2 … +2 around the enlarged board baseline */}
          <div
            role="group"
            aria-label="Task board zoom"
            style={{ display: 'inline-flex', alignItems: 'center', gap: px(3) }}
          >
            <ZoomButton
              title={zoomLevel <= ZOOM_MIN ? 'Zoom out (minimum)' : 'Zoom out'}
              disabled={zoomLevel <= ZOOM_MIN}
              onClick={zoomOut}
              darkMode={darkMode}
              borderColor={borderColor}
              mutedColor={mutedColor}
              textColor={textColor}
              size={px(26, 22)}
              label={
                <svg width={px(14)} height={px(14)} viewBox="0 0 16 16" aria-hidden>
                  <path
                    fill="currentColor"
                    d="M6.5 1a5.5 5.5 0 0 1 4.23 9.02l3.62 3.63a.75.75 0 1 1-1.06 1.06l-3.63-3.62A5.5 5.5 0 1 1 6.5 1Zm0 1.5a4 4 0 1 0 0 8 4 4 0 0 0 0-8ZM4.75 6a.75.75 0 0 0 0 1.5h3.5a.75.75 0 0 0 0-1.5h-3.5Z"
                  />
                </svg>
              }
            />
            <span
              title={`Zoom level ${zoomLevel >= 0 ? `+${zoomLevel}` : zoomLevel}`}
              style={{
                fontSize: px(10),
                fontWeight: 700,
                fontVariantNumeric: 'tabular-nums',
                color: zoomLevel === 0 ? mutedColor : '#58a6ff',
                minWidth: px(22),
                textAlign: 'center',
                userSelect: 'none',
              }}
            >
              {zoomLevel === 0 ? '100%' : `${Math.round((ZOOM_FACTORS[zoomLevel] ?? 1) * 100)}%`}
            </span>
            <ZoomButton
              title={zoomLevel >= ZOOM_MAX ? 'Zoom in (maximum)' : 'Zoom in'}
              disabled={zoomLevel >= ZOOM_MAX}
              onClick={zoomIn}
              darkMode={darkMode}
              borderColor={borderColor}
              mutedColor={mutedColor}
              textColor={textColor}
              size={px(26, 22)}
              label={
                <svg width={px(14)} height={px(14)} viewBox="0 0 16 16" aria-hidden>
                  <path
                    fill="currentColor"
                    d="M6.5 1a5.5 5.5 0 0 1 4.23 9.02l3.62 3.63a.75.75 0 1 1-1.06 1.06l-3.63-3.62A5.5 5.5 0 1 1 6.5 1Zm0 1.5a4 4 0 1 0 0 8 4 4 0 0 0 0-8ZM6.5 3.75a.75.75 0 0 1 .75.75v1.25H8.5a.75.75 0 0 1 0 1.5H7.25V8.5a.75.75 0 0 1-1.5 0V7.25H4.5a.75.75 0 0 1 0-1.5h1.25V4.5a.75.75 0 0 1 .75-.75Z"
                  />
                </svg>
              }
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

      {/* Column grid — columns keep a readable minimum width; when the
          container is narrower than 6 columns the board scrolls horizontally */}
      <div ref={gridRef} className="kanban-board-scroll" style={{
        display: 'grid',
        gridTemplateColumns: `repeat(6, minmax(${px(196, 172)}px, 1fr))`,
        gap: px(8),
        flex: 1,
        minHeight: 0,
        overflowX: 'auto',
        overflowY: 'hidden',
        padding: `0 ${px(12)}px ${px(12)}px`,
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
                  const isPastRun = task.kind === 'past_run'
                    || task.id.startsWith('run-');

                  if (isPastRun) {
                    return (
                      <div
                        key={task.id}
                        className="kanban-task-card kanban-past-run-card"
                        title={task.description || task.title}
                        style={{
                          background: darkMode ? '#0d1117' : '#f6f8fa',
                          border: `1px solid ${darkMode ? '#21262d' : '#d8dee4'}`,
                          borderRadius: px(6),
                          padding: `${px(5)}px ${px(7)}px`,
                          cursor: 'default',
                          flexShrink: 0,
                          opacity: 0.92,
                        }}
                      >
                        <div style={{
                          display: 'flex',
                          alignItems: 'center',
                          gap: px(6),
                          minWidth: 0,
                        }}>
                          <span style={{
                            fontSize: px(8, 5.5),
                            fontWeight: 800,
                            letterSpacing: '0.06em',
                            textTransform: 'uppercase',
                            color: darkMode ? '#3fb950' : '#1a7f37',
                            flexShrink: 0,
                          }}>
                            Prior
                          </span>
                          <span style={{
                            fontSize: px(10, 7),
                            fontWeight: 600,
                            color: textColor,
                            whiteSpace: 'nowrap',
                            overflow: 'hidden',
                            textOverflow: 'ellipsis',
                            minWidth: 0,
                          }}>
                            <HighlightText
                              text={task.title}
                              query={searchQuery}
                              color="#58a6ff"
                            />
                          </span>
                        </div>
                        {task.description && (
                          <div style={{
                            marginTop: px(3),
                            fontSize: px(8.5, 6),
                            color: subText,
                            whiteSpace: 'nowrap',
                            overflow: 'hidden',
                            textOverflow: 'ellipsis',
                            fontVariantNumeric: 'tabular-nums',
                          }}>
                            <HighlightText
                              text={task.description}
                              query={searchQuery}
                              color="#58a6ff"
                            />
                          </div>
                        )}
                      </div>
                    );
                  }

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
                          fontSize: px(12, 8),
                          marginBottom: px(6),
                          wordBreak: 'break-word',
                        }}>
                          <HighlightText
                            text={task.title.replace(/^Phase \d+: /, '')}
                            query={searchQuery}
                            color="#58a6ff"
                          />
                        </div>

                        {/* Contextual description */}
                        {task.description && (
                          <div style={{
                            fontSize: px(10, 7),
                            color: subText,
                            lineHeight: 1.4,
                            marginTop: -px(2),
                            marginBottom: px(6),
                            wordBreak: 'break-word',
                            display: '-webkit-box',
                            WebkitLineClamp: 3,
                            WebkitBoxOrient: 'vertical',
                            overflow: 'hidden',
                          }}>
                            <HighlightText
                              text={task.description}
                              query={searchQuery}
                              color="#58a6ff"
                            />
                          </div>
                        )}

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

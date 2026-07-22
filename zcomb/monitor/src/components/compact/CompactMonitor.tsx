import { useEffect, useMemo, useRef, useState } from 'react';
import type { AppState, Metrics, Task } from '../../hooks/usePolling';
import { ActivityFeed } from '../ActivityFeed';
import { TaskDetailModal } from '../TaskDetailModal';
import { CompactHeader } from './CompactHeader';
import { RunContextStrip } from './RunContextStrip';
import { CompactAgentsPanel } from './CompactAgentsPanel';
import { CompactExecutionPanel } from './CompactExecutionPanel';
import { CompactActivityPanel } from './CompactActivityPanel';
import { CompactFooter } from './CompactFooter';
import { useFloatingWindow, type DockId, type ResizeDir } from './useFloatingWindow';
import {
  ACCENT,
  compactTheme,
  deriveActionState,
  derivePhases,
  deriveRunState,
  formatClock,
  type TaskStatus,
} from './runState';

const EASE = 'cubic-bezier(0.22, 1, 0.36, 1)';
const TRANSITION_MS = 200;

function prefersReducedMotion(): boolean {
  return typeof window.matchMedia === 'function'
    && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
}

const RESIZE_HANDLES: { dir: ResizeDir; style: React.CSSProperties; cursor: string }[] = [
  { dir: 'n', cursor: 'ns-resize', style: { top: -4, left: 12, right: 12, height: 8 } },
  { dir: 's', cursor: 'ns-resize', style: { bottom: -4, left: 12, right: 12, height: 8 } },
  { dir: 'e', cursor: 'ew-resize', style: { right: -4, top: 12, bottom: 12, width: 8 } },
  { dir: 'w', cursor: 'ew-resize', style: { left: -4, top: 12, bottom: 12, width: 8 } },
  { dir: 'ne', cursor: 'nesw-resize', style: { top: -5, right: -5, width: 14, height: 14 } },
  { dir: 'nw', cursor: 'nwse-resize', style: { top: -5, left: -5, width: 14, height: 14 } },
  { dir: 'sw', cursor: 'nesw-resize', style: { bottom: -5, left: -5, width: 14, height: 14 } },
  { dir: 'se', cursor: 'nwse-resize', style: { bottom: -5, right: -5, width: 14, height: 14 } },
];

/** Arrow-key dock movement for keyboard users focused on the header. */
function dockForArrow(current: DockId | null, key: string): DockId | null {
  const dock = current || 'top-right';
  const [v, hSide] = dock === 'left-center' ? ['center', 'left']
    : dock === 'right-center' ? ['center', 'right']
    : dock.split('-');
  let vert = v;
  let side = hSide;
  if (key === 'ArrowLeft') side = 'left';
  else if (key === 'ArrowRight') side = 'right';
  else if (key === 'ArrowUp') vert = vert === 'bottom' ? 'center' : 'top';
  else if (key === 'ArrowDown') vert = vert === 'top' ? 'center' : 'bottom';
  else return null;
  const next: DockId = vert === 'center'
    ? (side === 'left' ? 'left-center' : 'right-center')
    : `${vert}-${side}` as DockId;
  return next === dock ? null : next;
}

/**
 * Floating compact monitor shell — a quarter-viewport command-center view of
 * the live run. Draggable, dock-snapping, resizable, persistent.
 *
 * When `windowed` is set, the shell owns a dedicated OS window (opened via
 * window.open) and fills it edge-to-edge; drag/resize gestures move and
 * resize the actual browser window instead of an in-page panel.
 */
export function CompactMonitor({
  state,
  metrics,
  elapsed,
  progressPct,
  doneTasks,
  totalTasks,
  projectName,
  objective,
  darkMode,
  connectionError,
  statusFilter,
  onStatusFilter,
  onSwitchToFull,
  onThemeChange,
  onRequestExtend,
  onRunRestarting,
  onRefresh,
  windowed = false,
}: {
  state: AppState | null;
  metrics?: Metrics | null;
  elapsed: string;
  progressPct: number;
  doneTasks: number;
  totalTasks: number;
  projectName: string;
  objective: string;
  darkMode: boolean;
  connectionError: string | null;
  statusFilter: TaskStatus;
  onStatusFilter: (s: TaskStatus) => void;
  onSwitchToFull: () => void;
  onThemeChange: (dark: boolean) => void;
  onRequestExtend: () => void;
  onRunRestarting: (note?: string) => void;
  onRefresh: () => void;
  windowed?: boolean;
}) {
  const theme = compactTheme(darkMode);
  const win = useFloatingWindow(true, windowed);
  const { rect } = win;

  const [phase, setPhase] = useState<'enter' | 'open' | 'exit'>(
    () => (windowed || prefersReducedMotion() ? 'open' : 'enter'),
  );
  const [selectedTask, setSelectedTask] = useState<Task | null>(null);
  const [drawer, setDrawer] = useState<null | 'activity' | 'completed'>(null);
  const [secondaryTab, setSecondaryTab] = useState<'activity' | 'agents'>('activity');
  const exitTimer = useRef<number | null>(null);

  // Enter: mount at the full-board rect, then settle into the docked frame.
  useEffect(() => {
    if (phase !== 'enter') return;
    const id = window.requestAnimationFrame(() => {
      window.requestAnimationFrame(() => setPhase('open'));
    });
    return () => window.cancelAnimationFrame(id);
  }, [phase]);

  useEffect(() => () => {
    if (exitTimer.current != null) window.clearTimeout(exitTimer.current);
  }, []);

  const requestFull = () => {
    if (phase === 'exit') return;
    if (windowed || prefersReducedMotion()) {
      onSwitchToFull();
      return;
    }
    setPhase('exit');
    exitTimer.current = window.setTimeout(onSwitchToFull, TRANSITION_MS + 20);
  };

  const tasks = state?.tasks?.tasks || [];
  const agents = state?.agents?.agents || [];
  const activity = state?.activity || [];
  const failedCount = tasks.filter(t => t.status === 'failed').length;
  const runState = deriveRunState(metrics, failedCount);
  const actions = deriveActionState(metrics);
  const phases = derivePhases(metrics);
  const loopId = String(metrics?.loopId || '');

  // Breakpoints from controlled geometry (no viewport assumptions).
  const wide = rect.w >= 960;
  const twoCol = rect.w < 800;
  const condensed = !wide;
  const baseEntries = rect.h >= 620 ? 5 : rect.h >= 500 ? 4 : 3;
  const maxEntries = condensed ? Math.min(3, baseEntries) : baseEntries;
  const maxCards = rect.h >= 470 ? 2 : 1;
  const shortHeight = rect.h < 470;

  const doneList = useMemo(
    () => tasks.filter(t => t.status === 'done').reverse(),
    [tasks],
  );

  const agentMap = useMemo(() => new Map(agents.map(a => [a.id, a.name])), [agents]);

  const dangerEdge = runState.tone === 'danger';
  const expanded = phase !== 'open';
  const frame: React.CSSProperties = windowed
    ? { left: 0, top: 0, width: '100vw', height: '100vh', borderRadius: 0 }
    : expanded
      ? { left: 0, top: 0, width: '100vw', height: '100vh', borderRadius: 0 }
      : { left: rect.x, top: rect.y, width: rect.w, height: rect.h, borderRadius: 16 };
  const moving = win.dragging || win.resizing;

  const gridColumns = twoCol
    ? 'minmax(0, 58fr) minmax(0, 42fr)'
    : wide
      ? 'minmax(0, 22fr) minmax(0, 51fr) minmax(0, 27fr)'
      : 'minmax(0, 20fr) minmax(0, 52fr) minmax(0, 28fr)';

  const onHeaderKeyDown = (e: React.KeyboardEvent) => {
    const el = e.target as HTMLElement;
    if (el.closest('button, input, select, textarea')) return;
    const next = dockForArrow(win.dock, e.key);
    if (next) {
      e.preventDefault();
      win.dockTo(next);
    }
  };

  return (
    <>
      {/* Backdrop separating the floating monitor from the parked board */}
      <div
        aria-hidden="true"
        style={{
          position: 'fixed',
          inset: 0,
          background: darkMode ? '#070a0e' : '#e8ebef',
          zIndex: 8990,
        }}
      />

      {/* Snap preview ghost */}
      {win.snapPreview && (
        <div
          aria-hidden="true"
          style={{
            position: 'fixed',
            left: win.snapPreview.x,
            top: win.snapPreview.y,
            width: win.snapPreview.w,
            height: win.snapPreview.h,
            borderRadius: 16,
            border: `1.5px dashed ${ACCENT.blue}55`,
            background: `${ACCENT.blue}0a`,
            zIndex: 8994,
            pointerEvents: 'none',
          }}
        />
      )}

      <section
        role="region"
        aria-label="Compact run monitor"
        className={`compact-shell${moving ? ' compact-shell-moving' : ''}`}
        style={{
          position: 'fixed',
          ...frame,
          zIndex: 9000,
          display: 'flex',
          flexDirection: 'column',
          background: theme.shellBg,
          border: windowed ? 'none' : `1px solid ${dangerEdge ? `${ACCENT.red}66` : theme.border}`,
          boxShadow: (expanded || windowed)
            ? 'none'
            : dangerEdge
              ? `0 0 0 1px ${ACCENT.red}33, 0 18px 48px rgba(0,0,0,0.5), 0 4px 14px rgba(0,0,0,0.35)`
              : '0 18px 48px rgba(0,0,0,0.5), 0 4px 14px rgba(0,0,0,0.35)',
          color: theme.text,
          fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", "Noto Sans", Helvetica, Arial, sans-serif',
          transitionProperty: 'left, top, width, height, border-radius, box-shadow',
          transitionDuration: `${TRANSITION_MS}ms`,
          transitionTimingFunction: EASE,
        }}
      >
        <div
          tabIndex={0}
          aria-label="Compact monitor header — drag to move, arrow keys to dock"
          onKeyDown={onHeaderKeyDown}
          style={{ flexShrink: 0, outlineOffset: -2, borderRadius: '16px 16px 0 0' }}
        >
          <CompactHeader
            theme={theme}
            darkMode={darkMode}
            metrics={metrics}
            runState={runState}
            actions={actions}
            progressPct={progressPct}
            doneTasks={doneTasks}
            totalTasks={totalTasks}
            elapsed={elapsed}
            narrow={rect.w < 900}
            onDragStart={win.startDrag}
            onToggleView={requestFull}
            onThemeChange={onThemeChange}
            onRequestExtend={onRequestExtend}
            onRunRestarting={onRunRestarting}
            onRefresh={onRefresh}
          />
        </div>

        <RunContextStrip
          theme={theme}
          projectName={connectionError ? `${projectName || 'ZComb'} · connection error` : projectName}
          objective={objective}
          loopId={loopId}
        />

        {/* Main content */}
        <div style={{
          position: 'relative',
          flex: 1,
          minHeight: 0,
          display: 'grid',
          gridTemplateColumns: gridColumns,
          gap: twoCol ? 10 : wide ? 11 : 10,
          padding: 12,
        }}>
          {/* Region A — agents (own column, or tabbed at narrow widths) */}
          {!twoCol && (
            <div style={{ minWidth: 0, minHeight: 0, display: 'flex', flexDirection: 'column' }}>
              <div style={{
                fontSize: 12,
                fontWeight: 700,
                textTransform: 'uppercase',
                letterSpacing: '0.08em',
                color: theme.muted,
                marginBottom: 6,
                flexShrink: 0,
              }}>
                Agents
              </div>
              <div style={{ flex: 1, minHeight: 0 }}>
                <CompactAgentsPanel
                  theme={theme}
                  agents={agents}
                  condensed={condensed || shortHeight}
                />
              </div>
            </div>
          )}

          {/* Region B — execution focus (dominant) */}
          <div style={{ minWidth: 0, minHeight: 0 }}>
            <CompactExecutionPanel
              theme={theme}
              tasks={tasks}
              agents={agents}
              actions={actions}
              statusFilter={statusFilter}
              onStatusFilter={onStatusFilter}
              onSelectTask={setSelectedTask}
              onViewCompleted={() => setDrawer('completed')}
              condensed={condensed}
              railCondensed={rect.w < 1160}
              maxCards={maxCards}
            />
          </div>

          {/* Region C — activity (tabbed with agents when narrow) */}
          <div style={{ minWidth: 0, minHeight: 0, display: 'flex', flexDirection: 'column' }}>
            {twoCol && (
              <div
                role="tablist"
                aria-label="Secondary panels"
                style={{ display: 'flex', gap: 2, marginBottom: 6, flexShrink: 0 }}
              >
                {(['activity', 'agents'] as const).map(tab => (
                  <button
                    key={tab}
                    type="button"
                    role="tab"
                    aria-selected={secondaryTab === tab}
                    onClick={() => setSecondaryTab(tab)}
                    style={{
                      flex: 1,
                      minHeight: 28,
                      padding: '3px 8px',
                      fontSize: 11,
                      fontWeight: 700,
                      textTransform: 'uppercase',
                      letterSpacing: '0.06em',
                      color: secondaryTab === tab ? theme.text : theme.muted,
                      background: secondaryTab === tab ? theme.cardBg : 'transparent',
                      border: `1px solid ${secondaryTab === tab ? theme.borderSoft : 'transparent'}`,
                      borderRadius: 7,
                      cursor: 'pointer',
                    }}
                  >
                    {tab === 'activity' ? 'Activity' : `Agents ${agents.length || ''}`}
                  </button>
                ))}
              </div>
            )}
            <div style={{ flex: 1, minHeight: 0 }}>
              {twoCol && secondaryTab === 'agents' ? (
                <CompactAgentsPanel theme={theme} agents={agents} condensed />
              ) : (
                <CompactActivityPanel
                  theme={theme}
                  activity={activity}
                  agents={agents}
                  maxEntries={maxEntries}
                  onViewAll={() => setDrawer('activity')}
                  onSelectEntry={() => setDrawer('activity')}
                />
              )}
            </div>
          </div>

          {/* Drawer — full activity / completed history inside the shell */}
          {drawer && (
            <div
              role="dialog"
              aria-label={drawer === 'activity' ? 'Full activity' : 'Completed tasks'}
              style={{
                position: 'absolute',
                top: 0,
                right: 0,
                bottom: 0,
                width: Math.min(400, Math.max(300, rect.w * 0.42)),
                background: theme.panelBg,
                borderLeft: `1px solid ${theme.border}`,
                boxShadow: '-14px 0 34px rgba(0,0,0,0.4)',
                zIndex: 20,
                display: 'flex',
                flexDirection: 'column',
              }}
              className="compact-drawer"
            >
              <div style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                gap: 8,
                padding: '10px 12px 8px',
                borderBottom: `1px solid ${theme.borderSoft}`,
                flexShrink: 0,
              }}>
                <span style={{
                  fontSize: 12,
                  fontWeight: 700,
                  textTransform: 'uppercase',
                  letterSpacing: '0.08em',
                  color: theme.muted,
                }}>
                  {drawer === 'activity' ? 'All Activity' : `Completed · ${doneList.length}`}
                </span>
                <button
                  type="button"
                  aria-label="Close drawer"
                  title="Close"
                  onClick={() => setDrawer(null)}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    width: 32,
                    height: 32,
                    background: 'none',
                    border: `1px solid ${theme.borderSoft}`,
                    borderRadius: 8,
                    cursor: 'pointer',
                    color: theme.muted,
                  }}
                >
                  <svg width="12" height="12" viewBox="0 0 16 16" aria-hidden="true">
                    <path d="M4 4 L12 12 M12 4 L4 12" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" />
                  </svg>
                </button>
              </div>
              <div style={{ flex: 1, minHeight: 0, overflowY: 'auto', padding: '0 12px 12px' }}>
                {drawer === 'activity' ? (
                  <ActivityFeed
                    activity={activity}
                    filter="all"
                    darkMode={darkMode}
                    agents={agents}
                  />
                ) : (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 5, paddingTop: 10 }}>
                    {doneList.length === 0 && (
                      <div style={{ color: theme.muted, fontSize: 12 }}>Nothing completed yet.</div>
                    )}
                    {doneList.map(task => (
                      <button
                        key={task.id}
                        type="button"
                        onClick={() => setSelectedTask(task)}
                        title="Open task details"
                        style={{
                          display: 'flex',
                          alignItems: 'center',
                          gap: 7,
                          minHeight: 32,
                          padding: '6px 9px',
                          background: theme.cardBg,
                          border: `1px solid ${theme.borderSoft}`,
                          borderRadius: 8,
                          cursor: 'pointer',
                          color: theme.text,
                          textAlign: 'left',
                        }}
                        className="compact-done-row"
                      >
                        <span aria-hidden="true" style={{ color: ACCENT.green, flexShrink: 0, fontSize: 11 }}>✓</span>
                        <span style={{
                          fontSize: 12,
                          fontWeight: 600,
                          minWidth: 0,
                          flex: 1,
                          overflow: 'hidden',
                          textOverflow: 'ellipsis',
                          whiteSpace: 'nowrap',
                        }}>
                          {task.title.replace(/^Phase \d+: /, '')}
                        </span>
                        <span style={{
                          fontSize: 11,
                          color: theme.muted,
                          fontFamily: 'ui-monospace, monospace',
                          fontVariantNumeric: 'tabular-nums',
                          flexShrink: 0,
                        }}>
                          {formatClock(task.updatedAt)}
                        </span>
                      </button>
                    ))}
                  </div>
                )}
              </div>
            </div>
          )}
        </div>

        <CompactFooter
          theme={theme}
          tasks={tasks}
          agents={agents}
          phases={phases}
          runState={runState}
          width={rect.w}
        />

        {/* Resize handles */}
        {!expanded && RESIZE_HANDLES.map(h => (
          <div
            key={h.dir}
            onPointerDown={win.startResize(h.dir)}
            aria-hidden={h.dir !== 'se'}
            {...(h.dir === 'se' ? {
              tabIndex: 0,
              role: 'slider',
              'aria-label': 'Resize compact monitor — arrow keys adjust size',
              onKeyDown: (e: React.KeyboardEvent) => {
                const step = 24;
                if (e.key === 'ArrowRight') { e.preventDefault(); win.nudgeResize(step, 0); }
                else if (e.key === 'ArrowLeft') { e.preventDefault(); win.nudgeResize(-step, 0); }
                else if (e.key === 'ArrowDown') { e.preventDefault(); win.nudgeResize(0, step); }
                else if (e.key === 'ArrowUp') { e.preventDefault(); win.nudgeResize(0, -step); }
              },
            } : {})}
            style={{
              position: 'absolute',
              ...h.style,
              cursor: h.cursor,
              zIndex: 25,
              touchAction: 'none',
            }}
          />
        ))}
      </section>

      {selectedTask && (
        <TaskDetailModal
          task={selectedTask}
          assigneeName={selectedTask.assignee
            ? (agentMap.get(selectedTask.assignee) || selectedTask.assignee)
            : '—'}
          darkMode={darkMode}
          onClose={() => setSelectedTask(null)}
        />
      )}
    </>
  );
}

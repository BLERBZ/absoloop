import { useState, useEffect, useCallback, useRef } from 'react';

export interface Agent {
  id: string;
  name: string;
  role: string;
  status: 'active' | 'idle' | 'blocked' | 'done';
  currentTask: string | null;
  metrics: { tasksCompleted: number; errors: number };
}

/** Structured card detail emitted by the bridge for the expand modal. */
export interface TaskDetails {
  loopId?: string;
  missionId?: string;
  objective?: string;
  engine?: string;
  iteration?: number;
  maxIterations?: number;
  costUsd?: number;
  budgetUsd?: number;
  tokens?: string;
  statusLabel?: string;
  /** Distilled run outcome, e.g. "Approved & delivered". */
  outcome?: string;
  filesChanged?: number;
  /** Top changed directories, e.g. ["apps/web", "apps/desktop"]. */
  areas?: string[];
  generatedAt?: string;
  focus?: string;
  iterations?: number;
  excerpt?: string;
  nowLine?: string;
  /** Same-origin URL serving the loop's report (HTML or Markdown). */
  reportUrl?: string;
  reportFormat?: 'html' | 'md' | string;
}

export interface Task {
  id: string;
  title: string;
  status: 'inbox' | 'assigned' | 'in_progress' | 'review' | 'done' | 'failed';
  assignee: string | null;
  priority: 'high' | 'medium' | 'low';
  dependencies: string[];
  phase: number;
  createdAt: string;
  updatedAt: string;
  description?: string;
  /** Compact session past-loop card in Done. */
  kind?: 'past_run' | string;
  details?: TaskDetails;
}

export interface Activity {
  timestamp: string;
  agentId: string;
  type: string;
  message: string;
}

export interface ObjectiveHistoryEntry {
  kind: 'objective' | 'continuation';
  text: string;
  loopId?: string | null;
  previousLoopId?: string | null;
  ts?: number | null;
  /** Wall-clock seconds for this entry's loop (bridge snapshot). */
  elapsedSeconds?: number | null;
  /** Unix seconds — loop start, for live ticking in the dropdown. */
  startedAt?: number | null;
  /** Unix seconds — terminal end; absent while the loop is still running. */
  endedAt?: number | null;
}

export interface SettingsCatalogModel {
  id: string;
  label: string;
}

export interface SettingsCatalogEngine {
  id: string;
  label: string;
  available: boolean;
  models: SettingsCatalogModel[];
}

/** Gear-menu prefs from the bridge — next-loop engine/model + catalog. */
export interface LoopSettings {
  theme?: 'dark' | 'light' | string;
  engine?: string;
  model?: string;
  activeEngine?: string;
  activeModel?: string;
  pendingNextLoop?: boolean;
  engines?: SettingsCatalogEngine[];
  savedAt?: number | null;
  applyOn?: string;
}

export interface Metrics {
  completionPct: number;
  errorRate: number;
  tasksPerHour: number;
  phases: { phase: number; name: string; progress: number }[];
  missionId?: string;
  loopId?: string;
  /** Original mission objective (unchanged across extends). */
  objective?: string;
  /** Latest continuation note, else the original objective. */
  displayedObjective?: string;
  /** Original objective + each extend note (oldest first). */
  objectiveHistory?: ObjectiveHistoryEntry[];
  status?: string;
  live?: boolean;
  awaitingRun?: boolean;
  /** True when state/monitor is at the human gate (enables Approve). */
  awaitingApproval?: boolean;
  runKey?: string;
  projectName?: string;
  /** Unix seconds — mission wall-clock start (stable across polls). */
  startedAt?: number | null;
  /** Unix seconds — when terminal; freezes the header elapsed timer. */
  endedAt?: number | null;
  /** Active (or last) loop engine — header badge. */
  engine?: string | null;
  /** Active (or last) loop model — header badge. */
  model?: string | null;
  /** Gear menu: theme + next-loop engine/model. */
  settings?: LoopSettings;
}

export interface RunResultsCritic {
  wallSeconds: number;
  costUsd: number;
  tokens?: number | null;
  turns?: number | null;
  outcome: 'finished' | 'FAILED' | string;
  limitReached?: string | null;
  ts?: number | null;
  engine?: string;
}

export interface RunResultsVerdict {
  recommendation: string;
  summary: string;
  blockingFindings: string[];
  ts?: number | null;
}

export interface RunResultsSpend {
  costUsd: number;
  tokensTotal: number;
  maxCostUsd: number;
  pctUsed: number;
  remainingUsd: number;
}

export interface RunResultsMission {
  status: string;
  stopReason?: string | null;
  iteration: number;
  costUsd: number;
  tokensTotal: number;
}

export interface ProposedExtensionStep {
  role: 'prompt' | 'analysis' | 'response' | string;
  content: string;
}

/** LLM (or heuristic) continuation proposal for one-click extend. */
export interface ProposedExtension {
  status: 'ready' | 'generating' | 'unavailable' | 'error' | string;
  source?: 'llm' | 'heuristic' | string;
  engine?: string;
  fingerprint?: string;
  note: string;
  rationale?: string;
  chain?: ProposedExtensionStep[];
  generatedAt?: string;
  preview?: boolean;
  error?: string;
}

/** CLI-parity critic / spend / stop snapshot for the Run Results panel. */
export interface RunResults {
  available: boolean;
  updatedAt?: string | null;
  clock?: string | null;
  critic?: RunResultsCritic | null;
  verdict?: RunResultsVerdict | null;
  spend?: RunResultsSpend | null;
  mission?: RunResultsMission | null;
  proposedExtension?: ProposedExtension | null;
}

export interface AppState {
  agents: { agents: Agent[] };
  tasks: { tasks: Task[] };
  metrics: Metrics;
  activity: Activity[];
  riskAnalysis: any;
  runResults?: RunResults | null;
  timestamp: string;
  project?: string;
  stateDir?: string;
}

const TERMINAL_STATUSES = new Set([
  'COMPLETED',
  'BLOCKED',
  'BUDGET_EXHAUSTED',
  'REJECTED',
  'STOPPED',
  'AWAITING_APPROVAL',
]);

const RESTART_HOLD_MS = 45_000;
const BURST_POLL_MS = [
  150, 350, 600, 900, 1200, 1600, 2200, 3000, 4000, 5500, 7000, 9000, 12000,
];

interface RestartHold {
  until: number;
  prevLoopId: string;
  prevRunKey: string;
  prevStatus: string;
}

/** Identity for Kanban remounts — loop/project only (not flaky runKey clocks). */
function runIdentity(metrics?: Metrics | null): string {
  if (!metrics) return '';
  const loop = metrics.loopId || metrics.missionId || '';
  const project = metrics.projectName || '';
  if (metrics.awaitingRun) return `${project}|${loop}|pending`;
  return `${project}|${loop}`;
}

function isStaleDuringRestart(hold: RestartHold, metrics?: Metrics | null): boolean {
  if (!metrics) return true;
  if (metrics.awaitingRun || metrics.live) return false;
  const status = String(metrics.status || '').toUpperCase();
  if (status === 'STARTING' || status === 'EXECUTING' || status === 'RUNNING') {
    return false;
  }
  const loopId = String(metrics.loopId || '');
  const runKey = String(metrics.runKey || '');
  // Same loop + still terminal → old paint; ignore until bridge catches up.
  if (
    hold.prevLoopId
    && loopId
    && loopId === hold.prevLoopId
    && TERMINAL_STATUSES.has(status)
  ) {
    return true;
  }
  if (hold.prevRunKey && runKey && runKey === hold.prevRunKey) {
    return true;
  }
  if (
    !loopId
    && TERMINAL_STATUSES.has(status)
    && status === hold.prevStatus
  ) {
    return true;
  }
  return false;
}

function waitingOverlay(prev: AppState, note?: string): AppState {
  const nowIso = new Date().toISOString();
  const prevLoop = prev.metrics?.loopId || prev.metrics?.missionId || 'run';
  const metrics: Metrics = {
    ...(prev.metrics || {
      completionPct: 0,
      errorRate: 0,
      tasksPerHour: 0,
      phases: [],
    }),
    awaitingRun: true,
    live: false,
    awaitingApproval: false,
    status: 'STARTING',
    runKey: `${prevLoop}:restarting`,
    startedAt: null,
    endedAt: null,
    completionPct: 0,
    tasksPerHour: 0,
    displayedObjective: note?.trim()
      || prev.metrics?.displayedObjective
      || prev.metrics?.objective
      || '',
  };
  return {
    ...prev,
    metrics,
    runResults: { available: false },
    tasks: {
      tasks: [{
        id: 'task-waiting',
        title: 'Waiting for new Absoloop run to start',
        status: 'inbox',
        assignee: null,
        priority: 'high',
        dependencies: [],
        phase: 0,
        createdAt: nowIso,
        updatedAt: nowIso,
        description: note?.trim()
          ? `Extend starting — ${note.trim().slice(0, 160)}`
          : 'Refreshing for the new objective / project / run…',
      }],
    },
    activity: [{
      timestamp: nowIso,
      agentId: 'builder-01',
      type: 'session_start',
      message: note?.trim()
        ? `New extend starting — ${note.trim().slice(0, 120)}`
        : 'New run starting — waiting for objective and runner…',
    }],
  };
}

export function usePolling(intervalMs: number = 3000) {
  const [state, setState] = useState<AppState | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdate, setLastUpdate] = useState<number | null>(null);
  const [consecutiveErrors, setConsecutiveErrors] = useState(0);
  const [runEpoch, setRunEpoch] = useState(0);
  const prevRunKey = useRef<string>('');
  const restartHold = useRef<RestartHold | null>(null);
  const burstTimers = useRef<number[]>([]);

  const clearBurstTimers = useCallback(() => {
    for (const id of burstTimers.current) window.clearTimeout(id);
    burstTimers.current = [];
  }, []);

  const fetchState = useCallback(async () => {
    try {
      const res = await fetch('/api/state');
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data: AppState = await res.json();
      const hold = restartHold.current;
      const now = Date.now();

      if (hold && now > hold.until) {
        restartHold.current = null;
        clearBurstTimers();
      }

      const activeHold = restartHold.current;
      if (activeHold && isStaleDuringRestart(activeHold, data.metrics)) {
        // Keep optimistic STARTING surface; don't flash old COMPLETED results.
        setLastUpdate(Date.now());
        setConsecutiveErrors(0);
        setError(null);
        return;
      }

      if (activeHold) {
        const m = data.metrics;
        if (
          m?.awaitingRun
          || m?.live
          || String(m?.status || '').toUpperCase() === 'STARTING'
          || (activeHold.prevLoopId
            && m?.loopId
            && m.loopId !== activeHold.prevLoopId)
          || (m?.runKey && m.runKey !== activeHold.prevRunKey)
        ) {
          restartHold.current = null;
          clearBurstTimers();
        }
      }

      const nextKey = runIdentity(data.metrics);
      if (nextKey && prevRunKey.current && nextKey !== prevRunKey.current) {
        setRunEpoch(epoch => epoch + 1);
      }
      if (nextKey) {
        prevRunKey.current = nextKey;
      }

      setState(data);
      setError(null);
      setLastUpdate(Date.now());
      setConsecutiveErrors(0);
    } catch (e: any) {
      setError(e.message);
      setConsecutiveErrors(prev => prev + 1);
    }
  }, [clearBurstTimers]);

  useEffect(() => {
    fetchState();
    const id = setInterval(fetchState, intervalMs);
    return () => {
      clearInterval(id);
      clearBurstTimers();
    };
  }, [fetchState, intervalMs, clearBurstTimers]);

  /** Force an immediate poll (e.g. after Resume starts a new run). */
  const refreshNow = useCallback(() => {
    void fetchState();
  }, [fetchState]);

  const scheduleBurstPolls = useCallback(() => {
    clearBurstTimers();
    burstTimers.current = BURST_POLL_MS.map(ms => (
      window.setTimeout(() => { void fetchState(); }, ms)
    ));
  }, [clearBurstTimers, fetchState]);

  /**
   * Optimistically treat the board as awaiting a new run (before bridge
   * writes awaitingRun=true). Holds off stale COMPLETED polls and burst-
   * polls until the new loop identity arrives.
   */
  const markRunRestarting = useCallback((note?: string) => {
    setRunEpoch(epoch => epoch + 1);
    setState(prev => {
      if (!prev) return prev;
      const prevLoop = String(prev.metrics?.loopId || '');
      const prevKey = runIdentity(prev.metrics);
      const prevStatus = String(prev.metrics?.status || '').toUpperCase();
      restartHold.current = {
        until: Date.now() + RESTART_HOLD_MS,
        prevLoopId: prevLoop,
        prevRunKey: prevKey,
        prevStatus,
      };
      const next = waitingOverlay(prev, note);
      prevRunKey.current = runIdentity(next.metrics);
      return next;
    });
    scheduleBurstPolls();
    void fetchState();
  }, [fetchState, scheduleBurstPolls]);

  const connectionHealth: 'connected' | 'degraded' | 'disconnected' =
    consecutiveErrors === 0 ? 'connected' :
    consecutiveErrors < 3 ? 'degraded' : 'disconnected';

  return {
    state,
    error,
    lastUpdate,
    connectionHealth,
    runEpoch,
    refreshNow,
    markRunRestarting,
  };
}

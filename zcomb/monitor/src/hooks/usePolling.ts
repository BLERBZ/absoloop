import { useState, useEffect, useCallback, useRef } from 'react';

export interface Agent {
  id: string;
  name: string;
  role: string;
  status: 'active' | 'idle' | 'blocked' | 'done';
  currentTask: string | null;
  metrics: { tasksCompleted: number; errors: number };
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
  runKey?: string;
  projectName?: string;
}

export interface AppState {
  agents: { agents: Agent[] };
  tasks: { tasks: Task[] };
  metrics: Metrics;
  activity: Activity[];
  riskAnalysis: any;
  timestamp: string;
  project?: string;
  stateDir?: string;
}

function runIdentity(metrics?: Metrics | null): string {
  if (!metrics) return '';
  if (metrics.runKey) return metrics.runKey;
  const parts = [
    metrics.projectName || '',
    metrics.loopId || '',
    metrics.missionId || '',
    metrics.awaitingRun ? 'pending' : (metrics.status || ''),
  ];
  return parts.join('|');
}

export function usePolling(intervalMs: number = 3000) {
  const [state, setState] = useState<AppState | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [startTime, setStartTime] = useState(Date.now());
  const [lastUpdate, setLastUpdate] = useState<number | null>(null);
  const [consecutiveErrors, setConsecutiveErrors] = useState(0);
  const [runEpoch, setRunEpoch] = useState(0);
  const prevRunKey = useRef<string>('');

  const fetchState = useCallback(async () => {
    try {
      const res = await fetch('/api/state');
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data: AppState = await res.json();
      const nextKey = runIdentity(data.metrics);

      if (nextKey && prevRunKey.current && nextKey !== prevRunKey.current) {
        // New project / objective / run — reset session clock and epoch so
        // the Kanban treats this as a fresh mission surface.
        setStartTime(Date.now());
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
  }, []);

  useEffect(() => {
    fetchState();
    const id = setInterval(fetchState, intervalMs);
    return () => clearInterval(id);
  }, [fetchState, intervalMs]);

  /** Force an immediate poll (e.g. after Resume starts a new run). */
  const refreshNow = useCallback(() => {
    void fetchState();
  }, [fetchState]);

  /**
   * Optimistically treat the board as awaiting a new run (before bridge
   * writes awaitingRun=true). Resets the elapsed timer.
   */
  const markRunRestarting = useCallback(() => {
    setStartTime(Date.now());
    setRunEpoch(epoch => epoch + 1);
    setState(prev => {
      if (!prev) return prev;
      const metrics: Metrics = {
        ...(prev.metrics || {
          completionPct: 0,
          errorRate: 0,
          tasksPerHour: 0,
          phases: [],
        }),
        awaitingRun: true,
        live: false,
        status: 'STARTING',
        runKey: `${prev.metrics?.loopId || prev.metrics?.missionId || 'run'}:pending`,
      };
      return {
        ...prev,
        metrics,
        tasks: {
          tasks: [{
            id: 'task-waiting',
            title: 'Waiting for new Absoloop run to start',
            status: 'inbox',
            assignee: null,
            priority: 'high',
            dependencies: [],
            phase: 0,
            createdAt: new Date().toISOString(),
            updatedAt: new Date().toISOString(),
            description: 'Refreshing for the new objective / project / run…',
          }],
        },
        activity: [{
          timestamp: new Date().toISOString(),
          agentId: 'builder-01',
          type: 'session_start',
          message: 'New run starting — waiting for objective and runner…',
        }],
      };
    });
    // Poll soon so bridge awaiting/live state replaces the optimistic view.
    window.setTimeout(() => { void fetchState(); }, 500);
    window.setTimeout(() => { void fetchState(); }, 2000);
  }, [fetchState]);

  const connectionHealth: 'connected' | 'degraded' | 'disconnected' =
    consecutiveErrors === 0 ? 'connected' :
    consecutiveErrors < 3 ? 'degraded' : 'disconnected';

  return {
    state,
    error,
    startTime,
    lastUpdate,
    connectionHealth,
    runEpoch,
    refreshNow,
    markRunRestarting,
  };
}

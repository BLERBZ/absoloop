import type { Metrics, Task } from '../../hooks/usePolling';

/** Semantic accent palette shared by the compact monitor components. */
export const ACCENT = {
  blue: '#58a6ff',
  green: '#3fb950',
  amber: '#d29922',
  purple: '#a371f7',
  red: '#f85149',
  gray: '#7d8590',
} as const;

export type TaskStatus = Task['status'];

export const STATUS_META: {
  key: TaskStatus;
  label: string;
  short: string;
  icon: string;
  color: string;
}[] = [
  { key: 'inbox', label: 'Inbox', short: 'Inbox', icon: '○', color: ACCENT.gray },
  { key: 'assigned', label: 'Assigned', short: 'Asgd', icon: '◎', color: ACCENT.amber },
  { key: 'in_progress', label: 'In Progress', short: 'Active', icon: '◉', color: ACCENT.blue },
  { key: 'review', label: 'Review', short: 'Review', icon: '◈', color: ACCENT.purple },
  { key: 'done', label: 'Done', short: 'Done', icon: '✓', color: ACCENT.green },
  { key: 'failed', label: 'Failed', short: 'Failed', icon: '✕', color: ACCENT.red },
];

/** Surface tokens for the compact shell — one place instead of per-component hex. */
export function compactTheme(darkMode: boolean) {
  return darkMode
    ? {
        shellBg: '#0b0f14',
        headerBg: '#010409',
        stripBg: '#0d1117',
        panelBg: '#10151c',
        cardBg: '#161b22',
        cardBgRaised: '#1c2128',
        border: '#30363d',
        borderSoft: '#21262d',
        text: '#e6edf3',
        subText: '#8b949e',
        muted: '#7d8590',
        track: '#21262d',
        hover: '#21262d',
      }
    : {
        shellBg: '#ffffff',
        headerBg: '#f6f8fa',
        stripBg: '#eef1f4',
        panelBg: '#f6f8fa',
        cardBg: '#ffffff',
        cardBgRaised: '#ffffff',
        border: '#d0d7de',
        borderSoft: '#e1e4e8',
        text: '#1f2328',
        subText: '#57606a',
        muted: '#656d76',
        track: '#e1e4e8',
        hover: '#e1e4e8',
      };
}

export type CompactTheme = ReturnType<typeof compactTheme>;

export interface RunStateInfo {
  id: string;
  label: string;
  color: string;
  tone: 'active' | 'ok' | 'warn' | 'danger' | 'neutral';
}

function titleCase(raw: string): string {
  return raw
    .toLowerCase()
    .split(/[_\s]+/)
    .map(w => (w ? w[0].toUpperCase() + w.slice(1) : w))
    .join(' ');
}

/** Single glanceable run state derived from bridge metrics + failed count. */
export function deriveRunState(
  metrics: Metrics | null | undefined,
  failedTasks: number,
): RunStateInfo {
  const status = String(metrics?.status || '').trim().toUpperCase();
  const live = Boolean(metrics?.live);
  if (metrics?.awaitingRun) {
    return { id: 'waiting', label: 'Waiting for run', color: ACCENT.blue, tone: 'active' };
  }
  if (Boolean(metrics?.awaitingApproval) || status === 'AWAITING_APPROVAL') {
    return { id: 'gate', label: 'Approval required', color: ACCENT.amber, tone: 'warn' };
  }
  if (status === 'FINAL_REVIEW') {
    return { id: 'final-review', label: 'Final review', color: ACCENT.purple, tone: 'active' };
  }
  if (live || status === 'EXECUTING' || status === 'RUNNING') {
    if (failedTasks > 0) {
      return { id: 'executing-errors', label: 'Executing · errors', color: ACCENT.red, tone: 'danger' };
    }
    return { id: 'executing', label: 'Executing', color: ACCENT.blue, tone: 'active' };
  }
  if (status === 'STARTING') {
    return { id: 'starting', label: 'Starting', color: ACCENT.blue, tone: 'active' };
  }
  if (status === 'COMPLETED') {
    return { id: 'complete', label: 'Complete', color: ACCENT.green, tone: 'ok' };
  }
  if (status === 'STOPPED') {
    return { id: 'stopped', label: 'Stopped', color: ACCENT.gray, tone: 'neutral' };
  }
  if (status === 'BLOCKED') {
    return { id: 'blocked', label: 'Blocked', color: ACCENT.red, tone: 'danger' };
  }
  if (status === 'REJECTED') {
    return { id: 'rejected', label: 'Rejected', color: ACCENT.red, tone: 'danger' };
  }
  if (status === 'BUDGET_EXHAUSTED') {
    return { id: 'budget', label: 'Budget exhausted', color: ACCENT.amber, tone: 'warn' };
  }
  if (failedTasks > 0) {
    return { id: 'failed', label: 'Failed tasks', color: ACCENT.red, tone: 'danger' };
  }
  if (!status || status === 'IDLE') {
    return { id: 'idle', label: 'Idle', color: ACCENT.gray, tone: 'neutral' };
  }
  return { id: status.toLowerCase(), label: titleCase(status), color: ACCENT.gray, tone: 'neutral' };
}

export interface RunActionState {
  status: string;
  live: boolean;
  awaitingRun: boolean;
  atHumanGate: boolean;
  hasMission: boolean;
  runningLike: boolean;
  /** After a clean landing, Extend is the primary next step (not Resume). */
  preferExtend: boolean;
  approveEnabled: boolean;
  resumeEnabled: boolean;
  extendEnabled: boolean;
  reportEnabled: boolean;
  abortEnabled: boolean;
}

/** Mirrors MissionControls enablement so full and compact modes agree. */
export function deriveActionState(metrics: Metrics | null | undefined): RunActionState {
  const status = String(metrics?.status || '').trim().toUpperCase();
  const live = Boolean(metrics?.live);
  const awaitingRun = Boolean(metrics?.awaitingRun);
  const atHumanGate = Boolean(metrics?.awaitingApproval) || status === 'AWAITING_APPROVAL';
  const hasMission = Boolean(metrics?.missionId || status) && status !== 'IDLE';
  const runningLike = live
    || ['EXECUTING', 'FINAL_REVIEW', 'RUNNING', 'STARTING'].includes(status);
  const preferExtend = status === 'COMPLETED' || status === 'BUDGET_EXHAUSTED';
  const idleTerminal = hasMission && !live && !awaitingRun && !atHumanGate && status !== 'STARTING';
  return {
    status,
    live,
    awaitingRun,
    atHumanGate,
    hasMission,
    runningLike,
    preferExtend,
    approveEnabled: hasMission && atHumanGate,
    resumeEnabled: idleTerminal && !preferExtend,
    extendEnabled: idleTerminal,
    reportEnabled: hasMission && !awaitingRun,
    abortEnabled: hasMission && runningLike && !awaitingRun && !atHumanGate,
  };
}

export interface PhaseSnapshot {
  phases: { phase: number; name: string; progress: number }[];
  /** Index of the stage the run is currently in (-1 when unknown). */
  currentIndex: number;
  current: { name: string; progress: number } | null;
  next: { name: string } | null;
  allComplete: boolean;
}

/** Current + next workflow stage from bridge phase progress. */
export function derivePhases(metrics: Metrics | null | undefined): PhaseSnapshot {
  const phases = metrics?.phases || [];
  if (!phases.length) {
    return { phases, currentIndex: -1, current: null, next: null, allComplete: false };
  }
  let idx = phases.findIndex(p => p.progress > 0 && p.progress < 100);
  if (idx === -1) idx = phases.findIndex(p => p.progress < 100);
  const allComplete = idx === -1;
  const currentIndex = allComplete ? phases.length - 1 : idx;
  const current = phases[currentIndex] || null;
  const next = !allComplete && currentIndex + 1 < phases.length
    ? phases[currentIndex + 1]
    : null;
  return {
    phases,
    currentIndex,
    current: current ? { name: current.name, progress: current.progress } : null,
    next: next ? { name: next.name } : null,
    allComplete,
  };
}

/** HH:MM for compact timestamps. */
export function formatClock(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '--:--';
  return `${d.getHours().toString().padStart(2, '0')}:${d.getMinutes().toString().padStart(2, '0')}`;
}

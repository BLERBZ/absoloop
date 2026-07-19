import express from 'express';
import { spawn } from 'child_process';
import {
  readFileSync, writeFileSync, existsSync, mkdirSync, readdirSync,
} from 'fs';
import { join, dirname, resolve } from 'path';
import { fileURLToPath } from 'url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const app = express();
const PORT = Number(process.env.ZCOMB_PORT || process.env.PORT || 3141);

/** Mutable binding — retargetable when a new Absoloop run/project activates. */
let STATE_DIR = resolve(
  process.env.ZCOMB_STATE_DIR || join(__dirname, 'state')
);
let PROJECT_ROOT = process.env.ZCOMB_PROJECT
  ? resolve(process.env.ZCOMB_PROJECT)
  : resolve(STATE_DIR, '../../..');

const ALLOWED_ACTIONS = new Set(['approve', 'resume', 'extend', 'report', 'abort']);

app.use(express.json());

// Serve static files from the built React app
app.use(express.static(join(__dirname, 'dist')));

// Helper to read state files safely
function readStateFile(filename) {
  const filepath = join(STATE_DIR, filename);
  if (!existsSync(filepath)) return null;
  try {
    return JSON.parse(readFileSync(filepath, 'utf-8'));
  } catch {
    return null;
  }
}

function writeStateFile(filename, payload) {
  mkdirSync(STATE_DIR, { recursive: true });
  const filepath = join(STATE_DIR, filename);
  writeFileSync(filepath, `${JSON.stringify(payload, null, 2)}\n`, 'utf-8');
}

function readActivityLog() {
  const filepath = join(STATE_DIR, 'activity.jsonl');
  if (!existsSync(filepath)) return [];
  try {
    const content = readFileSync(filepath, 'utf-8').trim();
    if (!content) return [];
    return content.split('\n').filter(Boolean).map(line => {
      try { return JSON.parse(line); } catch { return null; }
    }).filter(Boolean);
  } catch {
    return [];
  }
}

/** Project root for CLI actions */
function resolveProjectRoot() {
  return PROJECT_ROOT;
}

function resolveAbsoloopBin() {
  const home = process.env.ABSOLOOP_HOME;
  if (home) {
    const script = join(home, 'bin', 'absoloop');
    if (existsSync(script)) return script;
  }
  const sibling = resolve(__dirname, '../../bin/absoloop');
  if (existsSync(sibling)) return sibling;
  return 'absoloop';
}

function resolveAbsoloopHome() {
  const home = process.env.ABSOLOOP_HOME;
  if (home && existsSync(home)) return resolve(home);
  return resolve(__dirname, '../..');
}

/**
 * Persist a restart marker + optimistic awaiting Kanban state so the UI
 * flips to STARTING immediately — before the CLI finishes rewriting
 * state.json / loop_id (which can take several seconds).
 */
function markDashboardRestarting(action, note = '') {
  const project = resolveProjectRoot();
  const metrics = readStateFile('metrics.json') || {
    completionPct: 0,
    errorRate: 0,
    tasksPerHour: 0,
    phases: [],
  };
  const prevLoop = String(metrics.loopId || '').trim();
  const nowIso = new Date().toISOString();
  const marker = {
    ts: Date.now() / 1000,
    action: String(action || ''),
    previousLoopId: prevLoop,
    note: String(note || '').slice(0, 500),
  };

  try {
    const markerDir = join(project, '.absoloop', 'zcomb');
    mkdirSync(markerDir, { recursive: true });
    writeFileSync(
      join(markerDir, 'restarting.json'),
      `${JSON.stringify(marker, null, 2)}\n`,
      'utf-8',
    );
  } catch (err) {
    console.warn('  warn: could not write restart marker:', err?.message || err);
  }

  const nextMetrics = {
    ...metrics,
    awaitingRun: true,
    live: false,
    awaitingApproval: false,
    status: 'STARTING',
    runKey: `${prevLoop || 'run'}:restarting`,
    startedAt: null,
    endedAt: null,
    completionPct: 0,
    tasksPerHour: 0,
    displayedObjective: note
      ? String(note).trim()
      : (metrics.displayedObjective || metrics.objective || ''),
  };
  writeStateFile('metrics.json', nextMetrics);
  writeStateFile('run-results.json', { available: false });
  writeStateFile('tasks.json', {
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
      description: note
        ? `Extend starting — ${String(note).trim().slice(0, 160)}`
        : `Refreshing after ${action}…`,
    }],
  });
  writeStateFile('risk-analysis.json', {
    summary: `Restarting via ${action}`
      + (prevLoop ? ` · prior ${prevLoop}` : '')
      + (note ? ` · ${String(note).trim().slice(0, 80)}` : ''),
    iteration: 0,
    maxIterations: metrics.maxIterations || 0,
    costUsd: 0,
    tokensTotal: 0,
  });

  // Kick an immediate bridge sync so files stay coherent (best-effort).
  try {
    const home = resolveAbsoloopHome();
    spawn(
      process.env.PYTHON || 'python3',
      ['-c',
        'from pathlib import Path; from absoloop_harness.zcomb import sync_state; '
        + `sync_state(Path(${JSON.stringify(project)}))`],
      {
        cwd: home,
        env: process.env,
        detached: true,
        stdio: 'ignore',
      },
    ).unref();
  } catch {
    // ignore — optimistic files above already cover the first polls
  }

  return marker;
}

/**
 * Run an Absoloop CLI action against the bridged project.
 * Resume/extend are detached (long-running loop); approve/report/abort wait.
 */
function runAbsoloopAction(action, extraArgs = []) {
  const project = resolveProjectRoot();
  const bin = resolveAbsoloopBin();
  const args = [action, '-C', project, ...extraArgs];
  const detached = action === 'resume' || action === 'extend';

  return new Promise((resolvePromise, reject) => {
    const child = spawn(bin, args, {
      cwd: project,
      env: process.env,
      detached,
      stdio: detached ? 'ignore' : ['ignore', 'pipe', 'pipe'],
    });

    if (detached) {
      child.unref();
      resolvePromise({
        ok: true,
        action,
        project,
        detached: true,
        pid: child.pid,
        message: `Started absoloop ${action} (pid ${child.pid})`,
        restarting: true,
      });
      return;
    }

    let stdout = '';
    let stderr = '';
    child.stdout?.on('data', (chunk) => { stdout += chunk; });
    child.stderr?.on('data', (chunk) => { stderr += chunk; });

    const timer = setTimeout(() => {
      child.kill('SIGTERM');
      reject(new Error(`absoloop ${action} timed out after 120s`));
    }, 120_000);

    child.on('error', (err) => {
      clearTimeout(timer);
      reject(err);
    });

    child.on('close', (code) => {
      clearTimeout(timer);
      const out = stdout.trim();
      const err = stderr.trim();
      // Prefer the CLI's human line (e.g. "already APPROVED") over a generic
      // "completed" so the Kanban flash matches what actually happened.
      const cliLine = (code === 0 ? out : err || out)
        .split('\n')
        .map((line) => line.trim())
        .find(Boolean);
      resolvePromise({
        ok: code === 0,
        action,
        project,
        detached: false,
        code: code ?? 1,
        stdout: out,
        stderr: err,
        message: cliLine
          || (code === 0
            ? `absoloop ${action} completed`
            : `absoloop ${action} exited ${code}`),
      });
    });
  });
}

/** Best-effort bridge sync so Kanban metrics match state.json after actions. */
function syncDashboardBridge() {
  const project = resolveProjectRoot();
  try {
    const home = resolveAbsoloopHome();
    const child = spawn(
      process.env.PYTHON || 'python3',
      ['-c',
        'from pathlib import Path; from absoloop_harness.zcomb import sync_state; '
        + `sync_state(Path(${JSON.stringify(project)}))`],
      {
        cwd: home,
        env: process.env,
        stdio: 'ignore',
      },
    );
    child.on('error', () => {});
  } catch {
    // ignore — approve CLI also syncs; poller will catch up
  }
}

// API: Get all state in one call
app.get('/api/state', (_req, res) => {
  res.json({
    agents: readStateFile('agents.json') || { agents: [] },
    tasks: readStateFile('tasks.json') || { tasks: [] },
    metrics: readStateFile('metrics.json') || { completionPct: 0, errorRate: 0, tasksPerHour: 0, phases: [] },
    activity: readActivityLog().slice(-200),  // Last 200 entries
    riskAnalysis: readStateFile('risk-analysis.json') || null,
    runResults: readStateFile('run-results.json') || { available: false },
    timestamp: new Date().toISOString(),
    project: PROJECT_ROOT,
    stateDir: STATE_DIR,
  });
});

// API: Get individual state files
app.get('/api/agents', (_req, res) => {
  res.json(readStateFile('agents.json') || { agents: [] });
});

app.get('/api/tasks', (_req, res) => {
  res.json(readStateFile('tasks.json') || { tasks: [] });
});

app.get('/api/activity', (_req, res) => {
  res.json(readActivityLog().slice(-500));
});

app.get('/api/metrics', (_req, res) => {
  res.json(readStateFile('metrics.json') || {});
});

// Health for launcher readiness probes
app.get('/api/health', (_req, res) => {
  res.json({
    ok: true,
    stateDir: STATE_DIR,
    project: resolveProjectRoot(),
    port: PORT,
  });
});

/**
 * Point this dashboard at a different Absoloop project / state directory.
 * Called when `absoloop --zcomb` activates a new run while the UI is already up.
 */
app.post('/api/retarget', (req, res) => {
  const project = typeof req.body?.project === 'string' ? req.body.project.trim() : '';
  const stateDir = typeof req.body?.stateDir === 'string' ? req.body.stateDir.trim() : '';
  if (!project) {
    res.status(400).json({ ok: false, error: 'project path required' });
    return;
  }
  const nextProject = resolve(project);
  if (!existsSync(nextProject)) {
    res.status(400).json({ ok: false, error: `project not found: ${nextProject}` });
    return;
  }
  const nextState = stateDir
    ? resolve(stateDir)
    : resolve(nextProject, '.absoloop', 'zcomb', 'state');
  try {
    mkdirSync(nextState, { recursive: true });
  } catch (err) {
    res.status(500).json({
      ok: false,
      error: err?.message || String(err),
    });
    return;
  }
  PROJECT_ROOT = nextProject;
  STATE_DIR = nextState;
  process.env.ZCOMB_PROJECT = nextProject;
  process.env.ZCOMB_STATE_DIR = nextState;

  // Fresh Kanban session baseline — hide archives that already exist on disk.
  try {
    const runsDir = join(nextProject, '.absoloop', 'runs');
    const baseline = [];
    if (existsSync(runsDir)) {
      for (const name of readdirSync(runsDir)) {
        if (existsSync(join(runsDir, name, 'state.json'))) baseline.push(name);
      }
    }
    const sessionDir = join(nextProject, '.absoloop', 'zcomb');
    mkdirSync(sessionDir, { recursive: true });
    writeFileSync(
      join(sessionDir, 'kanban-session.json'),
      `${JSON.stringify({
        startedAt: Date.now() / 1000,
        baselineArchiveIds: baseline.sort(),
      }, null, 2)}\n`,
      'utf-8',
    );
  } catch (err) {
    console.warn('  warn: could not reset kanban session:', err?.message || err);
  }

  console.log(`  retargeted → project ${nextProject}`);
  console.log(`               state ${nextState}`);
  res.json({
    ok: true,
    project: PROJECT_ROOT,
    stateDir: STATE_DIR,
    message: 'Dashboard retargeted to new project/run',
  });
});

// Mission quick actions → absoloop approve | resume | extend | report | abort
app.post('/api/actions/:action', async (req, res) => {
  const action = String(req.params.action || '').toLowerCase();
  if (!ALLOWED_ACTIONS.has(action)) {
    res.status(400).json({
      ok: false,
      error: `Unknown action '${action}'. Allowed: approve, resume, extend, report, abort`,
    });
    return;
  }

  const project = resolveProjectRoot();
  if (!existsSync(join(project, '.absoloop'))) {
    res.status(400).json({
      ok: false,
      error: `No .absoloop/ under ${project} — not an Absoloop project`,
    });
    return;
  }

  const extraArgs = [];
  let extendNote = '';

  if (action === 'extend') {
    const note = typeof req.body?.note === 'string' ? req.body.note.trim() : '';
    if (!note) {
      res.status(400).json({
        ok: false,
        error: 'Extend requires a continuation objective (body.note)',
      });
      return;
    }
    extendNote = note;
    extraArgs.push('-m', note);
  }
  if (action === 'abort') {
    extraArgs.push('--yes');
  }

  // Flip Kanban to STARTING before the CLI returns so polls never briefly
  // re-paint the old COMPLETED Run Results during extend/resume.
  if (action === 'extend' || action === 'resume') {
    markDashboardRestarting(action, extendNote);
  }

  try {
    const result = await runAbsoloopAction(action, extraArgs);
    // Approve/abort/report mutate mission files — refresh Kanban metrics so
    // the Approve button cannot stay green on a stale AWAITING_APPROVAL paint.
    if (action === 'approve' || action === 'abort' || action === 'report') {
      syncDashboardBridge();
    }
    res.status(result.ok || result.detached ? 200 : 500).json(result);
  } catch (err) {
    if (action === 'approve' || action === 'abort') {
      syncDashboardBridge();
    }
    res.status(500).json({
      ok: false,
      action,
      project,
      error: err?.message || String(err),
    });
  }
});

// SPA fallback
app.get('/{*splat}', (_req, res) => {
  res.sendFile(join(__dirname, 'dist', 'index.html'));
});

app.listen(PORT, () => {
  console.log(`\n  ⚡ Absoloop ZComb dashboard at http://localhost:${PORT}`);
  console.log(`     state → ${STATE_DIR}`);
  console.log(`     project → ${resolveProjectRoot()}\n`);
});

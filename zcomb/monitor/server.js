import express from 'express';
import { spawn } from 'child_process';
import { readFileSync, existsSync, mkdirSync } from 'fs';
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

const ALLOWED_ACTIONS = new Set(['approve', 'resume', 'report']);

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

/**
 * Run an Absoloop CLI action against the bridged project.
 * Resume is detached (long-running loop); approve/report wait briefly for exit.
 */
function runAbsoloopAction(action, extraArgs = []) {
  const project = resolveProjectRoot();
  const bin = resolveAbsoloopBin();
  const args = [action, '-C', project, ...extraArgs];
  const detached = action === 'resume';

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
      resolvePromise({
        ok: code === 0,
        action,
        project,
        detached: false,
        code: code ?? 1,
        stdout: stdout.trim(),
        stderr: stderr.trim(),
        message: code === 0
          ? `absoloop ${action} completed`
          : (stderr.trim() || stdout.trim() || `absoloop ${action} exited ${code}`),
      });
    });
  });
}

// API: Get all state in one call
app.get('/api/state', (_req, res) => {
  res.json({
    agents: readStateFile('agents.json') || { agents: [] },
    tasks: readStateFile('tasks.json') || { tasks: [] },
    metrics: readStateFile('metrics.json') || { completionPct: 0, errorRate: 0, tasksPerHour: 0, phases: [] },
    activity: readActivityLog().slice(-200),  // Last 200 entries
    riskAnalysis: readStateFile('risk-analysis.json') || null,
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
  console.log(`  retargeted → project ${nextProject}`);
  console.log(`               state ${nextState}`);
  res.json({
    ok: true,
    project: PROJECT_ROOT,
    stateDir: STATE_DIR,
    message: 'Dashboard retargeted to new project/run',
  });
});

// Mission quick actions → absoloop approve | resume | report
app.post('/api/actions/:action', async (req, res) => {
  const action = String(req.params.action || '').toLowerCase();
  if (!ALLOWED_ACTIONS.has(action)) {
    res.status(400).json({
      ok: false,
      error: `Unknown action '${action}'. Allowed: approve, resume, report`,
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

  const metrics = readStateFile('metrics.json') || {};
  const status = String(metrics.status || '').toUpperCase();
  const extraArgs = [];

  if (action === 'resume' && status === 'COMPLETED') {
    extraArgs.push('--extend');
  }

  try {
    const result = await runAbsoloopAction(action, extraArgs);
    res.status(result.ok || result.detached ? 200 : 500).json(result);
  } catch (err) {
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

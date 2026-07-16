import express from 'express';
import { readFileSync, existsSync } from 'fs';
import { join, dirname, resolve } from 'path';
import { fileURLToPath } from 'url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const app = express();
const PORT = Number(process.env.ZCOMB_PORT || process.env.PORT || 3141);
const STATE_DIR = resolve(
  process.env.ZCOMB_STATE_DIR || join(__dirname, 'state')
);

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

// API: Get all state in one call
app.get('/api/state', (_req, res) => {
  res.json({
    agents: readStateFile('agents.json') || { agents: [] },
    tasks: readStateFile('tasks.json') || { tasks: [] },
    metrics: readStateFile('metrics.json') || { completionPct: 0, errorRate: 0, tasksPerHour: 0, phases: [] },
    activity: readActivityLog().slice(-200),  // Last 200 entries
    riskAnalysis: readStateFile('risk-analysis.json') || null,
    timestamp: new Date().toISOString()
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
  res.json({ ok: true, stateDir: STATE_DIR, port: PORT });
});

// SPA fallback
app.get('/{*splat}', (_req, res) => {
  res.sendFile(join(__dirname, 'dist', 'index.html'));
});

app.listen(PORT, () => {
  console.log(`\n  ⚡ Absoloop ZComb dashboard at http://localhost:${PORT}`);
  console.log(`     state → ${STATE_DIR}\n`);
});

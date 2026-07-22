import { useCallback, useEffect, useRef, useState } from 'react';
import type { CSSProperties } from 'react';

/**
 * Web Mission Briefing — the browser Launch window that replaces the
 * terminal briefing card for bare `absoloop` launches.
 *
 * Two steps, minimal by design:
 *   1. Mission  — objective + project
 *   2. Launch   — engine · model · delivery, then go
 *
 * The CLI writes a pending request into the ZComb state dir and waits;
 * this modal polls GET /api/launch and POSTs the submission back.
 */

export interface LaunchModel { id: string; label: string }

export interface LaunchEngine {
  id: string;
  label: string;
  available: boolean;
  models: LaunchModel[];
}

export interface LaunchDelivery { id: string; label: string; blurb: string }

export interface LaunchRequest {
  objective: string;
  projectName: string;
  projectFolder: string;
  projectPath: string;
  adopting: boolean;
  delivery: string;
  engine: string;
  model: string;
  engines: LaunchEngine[];
  deliveries: LaunchDelivery[];
  budgets: { maxIterations: number; maxCostUsd: number; maxWallHours: number };
}

export interface LaunchState {
  status: 'none' | 'pending' | 'submitted' | 'launched' | 'cancelled'
    | 'aborted' | 'stale' | 'error' | string;
  request?: LaunchRequest;
  error?: string;
  ts?: number;
}

/** Poll the launch handshake. Fast while a request is on screen. */
export function useLaunch() {
  const [launch, setLaunch] = useState<LaunchState>({ status: 'none' });
  const activeRef = useRef(false);

  const fetchLaunch = useCallback(async () => {
    try {
      const res = await fetch('/api/launch');
      if (!res.ok) return;
      const data: LaunchState = await res.json();
      activeRef.current = data.status === 'pending' || data.status === 'submitted';
      setLaunch(data);
    } catch {
      // Server briefly unreachable — keep the last known state.
    }
  }, []);

  useEffect(() => {
    void fetchLaunch();
    let id = 0;
    const tick = () => {
      id = window.setTimeout(async () => {
        await fetchLaunch();
        tick();
      }, activeRef.current ? 900 : 2500);
    };
    tick();
    return () => window.clearTimeout(id);
  }, [fetchLaunch]);

  return { launch, refresh: fetchLaunch };
}

// Mirrors classify_mission in bin/absoloop — chips only, never authoritative.
const MISSION_PROFILES: [string, string[]][] = [
  ['tests', ['test', 'pytest', 'jest', 'vitest', 'spec', 'coverage', 'unit test', 'e2e', 'regression']],
  ['bugfix', ['fix', 'bug', 'error', 'crash', 'broken', 'fail', 'regression', 'issue', 'defect']],
  ['feature', ['add', 'implement', 'create', 'build', 'support', 'feature', 'new', 'introduce', 'generate']],
  ['refactor', ['refactor', 'clean', 'simplif', 'restructure', 'migrat', 'rename', 'extract', 'consolidat', 'moderniz']],
  ['perf', ['performance', 'speed', 'optimi', 'faster', 'latency', 'memory', 'throughput']],
  ['docs', ['doc', 'readme', 'comment', 'guide', 'tutorial', 'changelog']],
];

const FLAVOR: Record<string, string> = {
  tests: 'Red to green',
  bugfix: 'Bug hunt',
  feature: 'Build mode',
  refactor: 'Surgical pass',
  perf: 'Speed run',
  docs: 'Truth in ink',
  general: 'Open mission',
};

function classifyMission(objective: string): string[] {
  const lower = objective.toLowerCase();
  const kinds = MISSION_PROFILES
    .filter(([, keywords]) => keywords.some(k => lower.includes(k)))
    .map(([name]) => name);
  return kinds.length > 0 ? kinds : ['general'];
}

const NAME_RE = /^[A-Za-z0-9._-]+$/;

export function LaunchModal({ launch, darkMode }: {
  launch: LaunchState;
  darkMode: boolean;
}) {
  const request = launch.request as LaunchRequest;
  const engines = request.engines || [];
  const deliveries = request.deliveries || [];

  const [step, setStep] = useState<1 | 2>(1);
  const [objective, setObjective] = useState(request.objective || '');
  const [projectName, setProjectName] = useState(request.projectName || '.');
  const [engine, setEngine] = useState(() => {
    const preset = engines.find(e => e.id === request.engine);
    if (preset?.available) return preset.id;
    return engines.find(e => e.available)?.id || request.engine || '';
  });
  const [modelByEngine, setModelByEngine] = useState<Record<string, string>>(
    () => (request.engine ? { [request.engine]: request.model || '' } : {}),
  );
  const [customModel, setCustomModel] = useState('');
  const [customModelOn, setCustomModelOn] = useState(false);
  const [delivery, setDelivery] = useState(request.delivery || 'local');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const objectiveRef = useRef<HTMLTextAreaElement | null>(null);

  const submitted = launch.status === 'submitted';
  const currentEngine = engines.find(e => e.id === engine);
  const models = currentEngine?.models || [];
  const selectedModel = customModelOn
    ? customModel.trim()
    : (modelByEngine[engine] || models[0]?.id || '');

  const kinds = classifyMission(objective);
  const flavor = FLAVOR[kinds[0]] || FLAVOR.general;

  const objectiveOk = objective.trim().length > 0;
  const nameOk = projectName.trim() === '.'
    || NAME_RE.test(projectName.trim());
  const anyEngineAvailable = engines.some(e => e.available);
  const engineOk = Boolean(currentEngine?.available);

  useEffect(() => {
    if (step === 1) {
      const id = window.setTimeout(() => objectiveRef.current?.focus(), 60);
      return () => window.clearTimeout(id);
    }
  }, [step]);

  const cancel = async () => {
    if (busy) return;
    setBusy(true);
    try {
      await fetch('/api/launch', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action: 'cancel' }),
      });
    } catch {
      // CLI heartbeat expiry cleans up if the server is unreachable
    } finally {
      setBusy(false);
    }
  };

  const goNext = () => {
    if (!objectiveOk) {
      setError('Give the mission one sentence — what should be true when we stop?');
      objectiveRef.current?.focus();
      return;
    }
    if (!nameOk) {
      setError('Project name must be letters/numbers/._- or "." for this directory.');
      return;
    }
    setError(null);
    setStep(2);
  };

  const submit = async () => {
    if (busy || submitted) return;
    if (!engineOk) {
      setError(`${currentEngine?.label || engine} is not installed — pick another engine.`);
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const res = await fetch('/api/launch', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          action: 'submit',
          submission: {
            objective: objective.trim(),
            projectName: projectName.trim() || '.',
            engine,
            model: selectedModel,
            delivery,
          },
        }),
      });
      const data = await res.json();
      if (!res.ok || !data.ok) {
        setError(data.error || `Submit failed (HTTP ${res.status})`);
      }
    } catch (err: any) {
      setError(err?.message || 'Could not reach the Absoloop CLI');
    } finally {
      setBusy(false);
    }
  };

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && step === 2 && !submitted) {
        e.preventDefault();
        setStep(1);
      }
      if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) {
        e.preventDefault();
        if (submitted) return;
        if (step === 1) goNext();
        else void submit();
      }
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  });

  // ── theme tokens ──────────────────────────────────────────────────────
  const overlay = darkMode ? 'rgba(1, 4, 9, 0.82)' : 'rgba(15, 23, 42, 0.45)';
  const cardBg = darkMode ? '#161b22' : '#ffffff';
  const insetBg = darkMode ? '#0d1117' : '#f6f8fa';
  const border = darkMode ? '#30363d' : '#d0d7de';
  const hairline = darkMode ? '#21262d' : '#eaeef2';
  const text = darkMode ? '#e6edf3' : '#1f2328';
  const muted = darkMode ? '#7d8590' : '#656d76';
  const accent = '#58a6ff';
  const green = '#3fb950';

  const fieldStyle: CSSProperties = {
    width: '100%',
    padding: '10px 12px',
    borderRadius: 8,
    border: `1px solid ${border}`,
    background: insetBg,
    color: text,
    fontSize: 14,
    fontFamily: 'inherit',
    outline: 'none',
    boxSizing: 'border-box',
  };

  const labelStyle: CSSProperties = {
    display: 'block',
    fontSize: 11,
    fontWeight: 700,
    letterSpacing: '0.08em',
    textTransform: 'uppercase',
    color: muted,
    marginBottom: 8,
  };

  const primaryBtn = (enabled: boolean): CSSProperties => ({
    borderRadius: 8,
    padding: '9px 20px',
    fontSize: 13,
    fontWeight: 700,
    border: `1px solid ${enabled ? green : border}`,
    background: enabled ? '#238636' : (darkMode ? '#21262d' : '#eaeef2'),
    color: enabled ? '#ffffff' : muted,
    cursor: enabled ? 'pointer' : 'not-allowed',
    whiteSpace: 'nowrap',
  });

  const ghostBtn: CSSProperties = {
    borderRadius: 8,
    padding: '8px 16px',
    fontSize: 13,
    fontWeight: 600,
    border: `1px solid ${border}`,
    background: 'none',
    color: muted,
    cursor: 'pointer',
    whiteSpace: 'nowrap',
  };

  const projectHint = projectName.trim() === '.'
    ? `this directory (${request.projectFolder})`
    : (request.adopting && projectName === request.projectName
      ? 'existing folder — adopt'
      : 'created next to where absoloop ran');

  return (
    <div
      className="modal-backdrop-fade-in"
      role="dialog"
      aria-modal="true"
      aria-label="Mission Briefing"
      style={{
        position: 'fixed',
        inset: 0,
        background: overlay,
        backdropFilter: 'blur(3px)',
        WebkitBackdropFilter: 'blur(3px)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        zIndex: 1000,
        padding: 20,
      }}
    >
      <div
        className="modal-content-scale-in"
        style={{
          width: 'min(600px, 96vw)',
          maxHeight: '92vh',
          overflowY: 'auto',
          background: cardBg,
          border: `1px solid ${border}`,
          borderRadius: 14,
          boxShadow: darkMode
            ? '0 24px 64px rgba(0, 0, 0, 0.55)'
            : '0 24px 64px rgba(15, 23, 42, 0.25)',
          display: 'flex',
          flexDirection: 'column',
          color: text,
        }}
      >
        {/* Header */}
        <div style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          gap: 12,
          padding: '18px 24px 14px',
          borderBottom: `1px solid ${hairline}`,
        }}>
          <div style={{ display: 'flex', alignItems: 'baseline', gap: 10, minWidth: 0 }}>
            <span style={{ color: accent, fontSize: 20, lineHeight: 1 }}>∞</span>
            <span style={{ fontSize: 16, fontWeight: 700, letterSpacing: '-0.01em' }}>
              Mission Briefing
            </span>
            {!submitted && (
              <span style={{ fontSize: 12, color: muted, whiteSpace: 'nowrap' }}>
                {step === 1 ? 'Mission' : 'Launch'}
              </span>
            )}
          </div>
          {!submitted && (
            <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
              {/* Step dots */}
              <div style={{ display: 'flex', gap: 6 }} aria-hidden>
                {[1, 2].map(n => (
                  <span key={n} style={{
                    width: n === step ? 18 : 7,
                    height: 7,
                    borderRadius: 4,
                    background: n === step ? accent : (darkMode ? '#30363d' : '#d0d7de'),
                    transition: 'width 0.2s ease, background 0.2s ease',
                  }} />
                ))}
              </div>
              <button
                type="button"
                onClick={() => void cancel()}
                title="Cancel — the CLI exits without launching"
                aria-label="Cancel launch"
                style={{
                  background: 'none',
                  border: 'none',
                  color: muted,
                  cursor: 'pointer',
                  fontSize: 18,
                  lineHeight: 1,
                  padding: 4,
                  borderRadius: 6,
                }}
              >
                ×
              </button>
            </div>
          )}
        </div>

        {submitted ? (
          /* ── Igniting ──────────────────────────────────────────────── */
          <div style={{
            padding: '48px 24px 56px',
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            gap: 14,
            textAlign: 'center',
          }}>
            <span className="compact-pulse-dot" style={{ color: green, fontSize: 34, lineHeight: 1 }}>
              ∞
            </span>
            <div style={{ fontSize: 15, fontWeight: 700 }}>
              Locking in — preparing the workspace…
            </div>
            <div style={{ fontSize: 13, color: muted, maxWidth: 380 }}>
              The Absoloop CLI is scaffolding the mission and starting the loop.
              This board flips live in a few seconds.
            </div>
          </div>
        ) : step === 1 ? (
          /* ── Step 1 · Mission ──────────────────────────────────────── */
          <div style={{ padding: '20px 24px', display: 'flex', flexDirection: 'column', gap: 18 }}>
            <div>
              <label style={labelStyle} htmlFor="launch-objective">Objective</label>
              <textarea
                id="launch-objective"
                ref={objectiveRef}
                rows={3}
                value={objective}
                placeholder="One sentence — what should be true when we stop?"
                onChange={e => {
                  setObjective(e.target.value);
                  if (error) setError(null);
                }}
                style={{
                  ...fieldStyle,
                  resize: 'vertical',
                  minHeight: 76,
                  maxHeight: 200,
                  fontSize: 15,
                  lineHeight: 1.45,
                }}
              />
              <div style={{
                display: 'flex',
                alignItems: 'center',
                gap: 8,
                marginTop: 10,
                flexWrap: 'wrap',
                minHeight: 22,
              }}>
                {objectiveOk && (
                  <>
                    <span style={{
                      fontSize: 11,
                      fontWeight: 700,
                      color: accent,
                      whiteSpace: 'nowrap',
                    }}>
                      {flavor}
                    </span>
                    {kinds.map(k => (
                      <span key={k} style={{
                        fontSize: 10,
                        fontWeight: 700,
                        letterSpacing: '0.05em',
                        textTransform: 'uppercase',
                        color: muted,
                        border: `1px solid ${border}`,
                        borderRadius: 20,
                        padding: '2px 9px',
                      }}>
                        {k}
                      </span>
                    ))}
                  </>
                )}
              </div>
            </div>

            <div>
              <label style={labelStyle} htmlFor="launch-project">Project</label>
              <input
                id="launch-project"
                type="text"
                value={projectName}
                onChange={e => {
                  setProjectName(e.target.value);
                  if (error) setError(null);
                }}
                spellCheck={false}
                style={{
                  ...fieldStyle,
                  fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace',
                  fontSize: 13,
                  borderColor: nameOk ? border : '#f85149',
                }}
              />
              <div style={{ fontSize: 12, color: muted, marginTop: 6 }}>
                {nameOk
                  ? <>“.” = {projectHint}</>
                  : 'Use letters, numbers, dots, dashes, underscores — or “.” for this directory.'}
              </div>
            </div>
          </div>
        ) : (
          /* ── Step 2 · Launch ───────────────────────────────────────── */
          <div style={{ padding: '20px 24px', display: 'flex', flexDirection: 'column', gap: 18 }}>
            {/* Mission recap */}
            <div style={{
              background: insetBg,
              border: `1px solid ${hairline}`,
              borderRadius: 10,
              padding: '10px 14px',
              display: 'flex',
              alignItems: 'baseline',
              gap: 10,
            }}>
              <span style={{ color: accent, fontSize: 13, flexShrink: 0 }}>◆</span>
              <span style={{
                fontSize: 13,
                lineHeight: 1.45,
                overflow: 'hidden',
                display: '-webkit-box',
                WebkitBoxOrient: 'vertical',
                WebkitLineClamp: 2,
              }}>
                {objective.trim()}
              </span>
            </div>

            <div>
              <span style={labelStyle}>Engine</span>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 8 }}>
                {engines.map(e => {
                  const active = e.id === engine;
                  return (
                    <button
                      key={e.id}
                      type="button"
                      disabled={!e.available}
                      onClick={() => {
                        setEngine(e.id);
                        setCustomModelOn(false);
                        if (error) setError(null);
                      }}
                      title={e.available ? e.label : `${e.label} is not installed`}
                      style={{
                        borderRadius: 10,
                        padding: '10px 8px',
                        border: `1px solid ${active ? accent : border}`,
                        background: active
                          ? (darkMode ? '#388bfd1a' : '#ddf4ff')
                          : insetBg,
                        color: e.available ? text : muted,
                        cursor: e.available ? 'pointer' : 'not-allowed',
                        opacity: e.available ? 1 : 0.55,
                        display: 'flex',
                        flexDirection: 'column',
                        alignItems: 'center',
                        gap: 4,
                      }}
                    >
                      <span style={{ fontSize: 13, fontWeight: 700 }}>{e.label}</span>
                      <span style={{
                        fontSize: 10,
                        fontWeight: 600,
                        color: e.available ? green : muted,
                      }}>
                        {e.available ? '● ready' : 'not installed'}
                      </span>
                    </button>
                  );
                })}
              </div>
              {!anyEngineAvailable && (
                <div style={{ fontSize: 12, color: '#f85149', marginTop: 8 }}>
                  No engine on PATH — install claude, codex, or grok, then re-run absoloop.
                </div>
              )}
            </div>

            <div>
              <label style={labelStyle} htmlFor="launch-model">Model</label>
              {customModelOn ? (
                <div style={{ display: 'flex', gap: 8 }}>
                  <input
                    type="text"
                    autoFocus
                    value={customModel}
                    placeholder="model id / alias"
                    onChange={e => setCustomModel(e.target.value)}
                    spellCheck={false}
                    style={{
                      ...fieldStyle,
                      flex: 1,
                      fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace',
                      fontSize: 13,
                    }}
                  />
                  <button type="button" style={ghostBtn} onClick={() => setCustomModelOn(false)}>
                    Catalog
                  </button>
                </div>
              ) : (
                <select
                  id="launch-model"
                  value={modelByEngine[engine] || models[0]?.id || ''}
                  onChange={e => {
                    if (e.target.value === '__custom__') {
                      setCustomModelOn(true);
                      return;
                    }
                    setModelByEngine(prev => ({ ...prev, [engine]: e.target.value }));
                  }}
                  style={{ ...fieldStyle, cursor: 'pointer' }}
                >
                  {models.map((m, i) => (
                    <option key={m.id} value={m.id}>
                      {m.id}{m.label && m.label !== m.id ? ` — ${m.label}` : ''}{i === 0 ? ' (default)' : ''}
                    </option>
                  ))}
                  <option value="__custom__">Custom…</option>
                </select>
              )}
            </div>

            <div>
              <span style={labelStyle}>Delivery</span>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                {deliveries.map(d => {
                  const active = d.id === delivery;
                  return (
                    <button
                      key={d.id}
                      type="button"
                      onClick={() => setDelivery(d.id)}
                      style={{
                        display: 'flex',
                        alignItems: 'center',
                        gap: 10,
                        textAlign: 'left',
                        borderRadius: 8,
                        padding: '8px 12px',
                        border: `1px solid ${active ? accent : border}`,
                        background: active
                          ? (darkMode ? '#388bfd1a' : '#ddf4ff')
                          : insetBg,
                        color: text,
                        cursor: 'pointer',
                      }}
                    >
                      <span style={{
                        width: 8,
                        height: 8,
                        borderRadius: '50%',
                        flexShrink: 0,
                        background: active ? accent : 'transparent',
                        border: `1.5px solid ${active ? accent : muted}`,
                      }} />
                      <span style={{ fontSize: 13, fontWeight: 700, width: 44, flexShrink: 0 }}>
                        {d.label}
                      </span>
                      <span style={{ fontSize: 12, color: muted }}>{d.blurb}</span>
                    </button>
                  );
                })}
              </div>
            </div>

            <div style={{ fontSize: 12, color: muted }}>
              Budgets · {request.budgets.maxIterations} iterations
              {' · '}${request.budgets.maxCostUsd}
              {' · '}{request.budgets.maxWallHours}h wall
            </div>
          </div>
        )}

        {/* Footer */}
        {!submitted && (
          <div style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            gap: 12,
            padding: '14px 24px 18px',
            borderTop: `1px solid ${hairline}`,
          }}>
            <span style={{ fontSize: 11, color: error ? '#f85149' : muted, minWidth: 0 }}>
              {error || '⌘/Ctrl+Enter to continue'}
            </span>
            <div style={{ display: 'flex', gap: 8, flexShrink: 0 }}>
              {step === 2 ? (
                <>
                  <button type="button" style={ghostBtn} onClick={() => setStep(1)}>
                    Back
                  </button>
                  <button
                    type="button"
                    disabled={busy || !engineOk}
                    onClick={() => void submit()}
                    style={primaryBtn(!busy && engineOk)}
                  >
                    {busy ? 'Launching…' : '∞ Launch mission'}
                  </button>
                </>
              ) : (
                <>
                  <button type="button" style={ghostBtn} onClick={() => void cancel()}>
                    Cancel
                  </button>
                  <button
                    type="button"
                    disabled={!objectiveOk || !nameOk}
                    onClick={goNext}
                    style={primaryBtn(objectiveOk && nameOk)}
                  >
                    Continue
                  </button>
                </>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

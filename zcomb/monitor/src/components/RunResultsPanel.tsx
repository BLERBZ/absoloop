import { useEffect, useMemo, useState } from 'react';
import type { ProposedExtension, RunResults } from '../hooks/usePolling';
import { triggerAction } from './MissionControls';

const STORAGE_KEY = 'zc-run-results-open';

const VERDICT_TONE: Record<string, { fg: string; bg: string; border: string; label: string }> = {
  PASS: { fg: '#3fb950', bg: '#23863622', border: '#3fb95066', label: 'Pass' },
  HOLD: { fg: '#d29922', bg: '#9a670022', border: '#d2992266', label: 'Hold' },
  REJECT: { fg: '#f85149', bg: '#da363322', border: '#f8514966', label: 'Reject' },
  UNREADABLE: { fg: '#f85149', bg: '#da363322', border: '#f8514966', label: 'Unreadable' },
};

const STATUS_META: Record<string, { color: string; label: string }> = {
  AWAITING_APPROVAL: { color: '#3fb950', label: 'Awaiting approval' },
  COMPLETED: { color: '#3fb950', label: 'Completed' },
  BLOCKED: { color: '#d29922', label: 'Blocked' },
  BUDGET_EXHAUSTED: { color: '#f85149', label: 'Budget exhausted' },
  REJECTED: { color: '#f85149', label: 'Rejected' },
  STOPPED: { color: '#d29922', label: 'Stopped' },
  FINAL_REVIEW: { color: '#58a6ff', label: 'Final review' },
  EXECUTING: { color: '#58a6ff', label: 'Executing' },
};

const STOP_REASON_LABELS: Record<string, string> = {
  accepted_pending_human_gate: 'Critic passed — your approval is next',
  accepted_by_all_gates: 'All gates passed',
  human_approved: 'You approved this run',
  human_aborted: 'Aborted by operator',
  critic_reject: 'Critic rejected the result',
  critic_unavailable: 'Critic could not be read',
  critic_findings_not_converging: 'Critic findings not converging',
  integrity_violation: 'Integrity check failed',
  iteration_budget: 'Hit iteration budget',
  cost_budget: 'Hit cost budget',
  wall_clock_budget: 'Hit wall-clock budget',
  no_progress_window: 'No progress window exceeded',
};

function formatTokens(tokens?: number | null): string {
  if (typeof tokens !== 'number' || !(tokens > 0)) return '—';
  if (tokens >= 1_000_000) return `${(tokens / 1_000_000).toFixed(2)}M`;
  if (tokens >= 1_000) return `${(tokens / 1_000).toFixed(1)}k`;
  return String(Math.round(tokens));
}

function formatUsd(n?: number | null): string {
  if (typeof n !== 'number' || Number.isNaN(n)) return '$0.00';
  if (n >= 100) return `$${n.toFixed(0)}`;
  return `$${n.toFixed(2)}`;
}

/** Cost with a short token tally — e.g. "$13.43 / 2.3M tok". */
function formatCostWithTokens(
  usd?: number | null,
  tokens?: number | null,
): string {
  const money = formatUsd(usd);
  if (typeof tokens !== 'number' || !(tokens > 0)) return money;
  return `${money} / ${formatTokens(tokens)} tok`;
}

function formatDuration(seconds?: number | null): string {
  if (typeof seconds !== 'number' || !(seconds >= 0)) return '—';
  if (seconds < 60) return `${Math.round(seconds)}s`;
  const m = Math.floor(seconds / 60);
  const s = Math.round(seconds % 60);
  return s ? `${m}m ${s}s` : `${m}m`;
}

/** Local finished timestamp for Run Results (collapsed + expanded). */
function formatFinishedAt(
  updatedAt?: string | null,
  clock?: string | null,
): string {
  if (updatedAt) {
    const d = new Date(updatedAt);
    if (!Number.isNaN(d.getTime())) {
      const now = new Date();
      const sameDay = d.getFullYear() === now.getFullYear()
        && d.getMonth() === now.getMonth()
        && d.getDate() === now.getDate();
      const time = d.toLocaleTimeString([], {
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
        hour12: false,
      });
      if (sameDay) return time;
      return `${d.toLocaleDateString([], {
        month: 'short',
        day: 'numeric',
      })} ${time}`;
    }
  }
  return (clock || '').trim();
}

function humanStatus(status: string): { color: string; label: string } {
  return STATUS_META[status] || {
    color: '#7d8590',
    label: status.replace(/_/g, ' ').toLowerCase().replace(/\b\w/g, c => c.toUpperCase()),
  };
}

function humanStopReason(reason?: string | null): string {
  if (!reason) return '';
  return STOP_REASON_LABELS[reason] || reason.replace(/_/g, ' ');
}

function Chevron({ open }: { open: boolean }) {
  return (
    <svg
      width="12"
      height="12"
      viewBox="0 0 16 16"
      aria-hidden="true"
      style={{
        display: 'block',
        transform: open ? 'rotate(90deg)' : 'none',
        transition: 'transform 0.2s ease',
        flexShrink: 0,
      }}
    >
      <path
        d="M6 3.5 L11 8 L6 12.5"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function Metric({
  label,
  value,
  hint,
  accent,
  mutedColor,
  textColor,
  borderColor,
  background,
}: {
  label: string;
  value: string;
  hint?: string;
  accent?: string;
  mutedColor: string;
  textColor: string;
  borderColor: string;
  background: string;
}) {
  return (
    <div
      className="run-results-metric"
      style={{ borderColor, background }}
    >
      <div
        style={{
          fontSize: 10,
          fontWeight: 700,
          letterSpacing: '0.08em',
          textTransform: 'uppercase',
          color: mutedColor,
          marginBottom: 3,
        }}
      >
        {label}
      </div>
      <div
        style={{
          fontSize: value.includes(' / ') ? 14 : 17,
          fontWeight: 700,
          fontVariantNumeric: 'tabular-nums',
          letterSpacing: '-0.02em',
          color: accent || textColor,
          lineHeight: 1.2,
          wordBreak: 'break-word',
        }}
      >
        {value}
      </div>
      {hint && (
        <div
          style={{
            marginTop: 3,
            fontSize: 11,
            color: mutedColor,
            fontVariantNumeric: 'tabular-nums',
            whiteSpace: 'nowrap',
            overflow: 'hidden',
            textOverflow: 'ellipsis',
          }}
        >
          {hint}
        </div>
      )}
    </div>
  );
}

function chainRoleLabel(role: string): string {
  const r = role.toLowerCase();
  if (r === 'prompt') return 'Prompt';
  if (r === 'analysis') return 'Analysis';
  if (r === 'response') return 'Response';
  return role.replace(/_/g, ' ');
}

export function RunResultsPanel({
  runResults,
  darkMode,
  runEpoch,
  extendEnabled = false,
  onExtended,
}: {
  runResults?: RunResults | null;
  darkMode: boolean;
  runEpoch: number;
  /** True when one-click extend is allowed (mission idle / not live). */
  extendEnabled?: boolean;
  /** Called after a successful one-click extend starts. */
  onExtended?: () => void;
}) {
  const available = Boolean(runResults?.available);
  const status = String(runResults?.mission?.status || '').toUpperCase();
  const recommendation = String(runResults?.verdict?.recommendation || '').toUpperCase();
  const shouldDefaultOpen = Boolean(
    runResults?.verdict
    || runResults?.mission
    || ['AWAITING_APPROVAL', 'COMPLETED', 'BLOCKED', 'REJECTED',
        'BUDGET_EXHAUSTED', 'STOPPED'].includes(status),
  );

  const [open, setOpen] = useState(() => {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored === '0') return false;
    if (stored === '1') return true;
    return shouldDefaultOpen;
  });
  const [summaryExpanded, setSummaryExpanded] = useState(false);
  const [chainOpen, setChainOpen] = useState(false);
  const [extendBusy, setExtendBusy] = useState(false);
  const [extendError, setExtendError] = useState<string | null>(null);

  useEffect(() => {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored == null) setOpen(shouldDefaultOpen);
    setSummaryExpanded(false);
    setChainOpen(false);
    setExtendError(null);
    setExtendBusy(false);
  }, [runEpoch, shouldDefaultOpen]);

  useEffect(() => {
    if (!available) return;
    if (localStorage.getItem(STORAGE_KEY) === '0') return;
    if (shouldDefaultOpen) setOpen(true);
  }, [available, shouldDefaultOpen, recommendation, status]);

  const toggle = () => {
    setOpen(prev => {
      const next = !prev;
      localStorage.setItem(STORAGE_KEY, next ? '1' : '0');
      return next;
    });
  };

  const borderColor = darkMode ? '#30363d' : '#d0d7de';
  const textColor = darkMode ? '#e6edf3' : '#1f2328';
  const mutedColor = darkMode ? '#7d8590' : '#656d76';
  const panelBg = darkMode ? '#010409' : '#f6f8fa';
  const surface = darkMode ? '#0d1117' : '#ffffff';
  const verdictTone = VERDICT_TONE[recommendation] || {
    fg: mutedColor,
    bg: darkMode ? '#21262d' : '#eaeef2',
    border: borderColor,
    label: recommendation || '—',
  };
  const statusMeta = humanStatus(status);
  const spendPct = runResults?.spend?.pctUsed ?? 0;
  const spendColor = spendPct >= 90 ? '#f85149' : spendPct >= 75 ? '#d29922' : '#58a6ff';
  const stopReason = humanStopReason(runResults?.mission?.stopReason);
  const summary = (runResults?.verdict?.summary || '').trim();
  const summaryLong = summary.length > 180;
  const finishedAt = formatFinishedAt(runResults?.updatedAt, runResults?.clock);

  const collapsedLine = useMemo(() => {
    const parts: string[] = [];
    if (recommendation) parts.push(verdictTone.label);
    if (status) parts.push(statusMeta.label);
    if (runResults?.spend) {
      parts.push(
        `${formatCostWithTokens(
          runResults.spend.costUsd,
          runResults.spend.tokensTotal,
        )} · ${spendPct}% budget`,
      );
    }
    if (finishedAt) parts.push(`Finished ${finishedAt}`);
    return parts.join('  ·  ');
  }, [
    recommendation, verdictTone.label, status, statusMeta.label,
    runResults?.spend, spendPct, finishedAt,
  ]);

  if (!available || !runResults) return null;

  const critic = runResults.critic;
  const verdict = runResults.verdict;
  const spend = runResults.spend;
  const mission = runResults.mission;
  const findings = verdict?.blockingFindings || [];
  const proposal: ProposedExtension | null | undefined = runResults.proposedExtension;
  const proposalNote = (proposal?.note || '').trim();
  const proposalReady = Boolean(proposalNote);
  const proposalGenerating = proposal?.status === 'generating';

  const runExtend = async () => {
    if (!proposalNote || extendBusy || !extendEnabled) return;
    setExtendBusy(true);
    setExtendError(null);
    try {
      const result = await triggerAction('extend', { note: proposalNote });
      if (!result.ok) {
        setExtendError(result.message);
        return;
      }
      onExtended?.();
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Failed to start extend';
      setExtendError(message);
    } finally {
      setExtendBusy(false);
    }
  };

  return (
    <section
      className="run-results-panel"
      style={{
        flexShrink: 0,
        margin: '0 14px 8px',
        borderRadius: 10,
        border: `1px solid ${borderColor}`,
        background: panelBg,
        overflow: 'hidden',
      }}
    >
      <button
        type="button"
        onClick={toggle}
        aria-expanded={open}
        className="run-results-toggle"
        style={{
          width: '100%',
          display: 'flex',
          alignItems: 'center',
          gap: 10,
          padding: '9px 12px',
          background: surface,
          border: 'none',
          borderBottom: open ? `1px solid ${borderColor}` : 'none',
          cursor: 'pointer',
          color: textColor,
          textAlign: 'left',
        }}
      >
        <span style={{ color: mutedColor, display: 'flex' }}>
          <Chevron open={open} />
        </span>

        <div style={{ minWidth: 0, flex: 1 }}>
          <div style={{
            display: 'flex',
            alignItems: 'center',
            gap: 8,
            flexWrap: 'wrap',
            marginBottom: open ? 0 : 2,
          }}>
            <span style={{
              fontSize: 11,
              fontWeight: 800,
              letterSpacing: '0.1em',
              textTransform: 'uppercase',
              color: mutedColor,
            }}>
              Run Results
            </span>
            {recommendation && (
              <span
                className="run-results-pill"
                style={{
                  color: verdictTone.fg,
                  background: verdictTone.bg,
                  border: `1px solid ${verdictTone.border}`,
                }}
              >
                {verdictTone.label}
              </span>
            )}
            {status && (
              <span
                className="run-results-pill"
                style={{
                  color: statusMeta.color,
                  background: `${statusMeta.color}18`,
                  border: `1px solid ${statusMeta.color}44`,
                }}
              >
                {statusMeta.label}
              </span>
            )}
            {finishedAt && (
              <span
                className="run-results-pill"
                title={`Finished ${finishedAt}`}
                style={{
                  color: mutedColor,
                  background: darkMode ? '#21262d' : '#eaeef2',
                  border: `1px solid ${borderColor}`,
                  fontVariantNumeric: 'tabular-nums',
                  fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Consolas, monospace',
                  letterSpacing: '0.02em',
                  textTransform: 'none',
                  fontWeight: 650,
                }}
              >
                {finishedAt}
              </span>
            )}
          </div>
          {!open && (
            <div style={{
              fontSize: 12,
              color: mutedColor,
              overflow: 'hidden',
              textOverflow: 'ellipsis',
              whiteSpace: 'nowrap',
            }}>
              {collapsedLine || 'Critic, spend, and stop summary'}
            </div>
          )}
        </div>

        {!open && (
          <div style={{
            textAlign: 'right',
            flexShrink: 0,
            fontVariantNumeric: 'tabular-nums',
          }}>
            {spend ? (
              <>
                <div style={{ fontSize: 14, fontWeight: 700, color: textColor }}>
                  {formatCostWithTokens(spend.costUsd, spend.tokensTotal)}
                </div>
                <div style={{ fontSize: 10, color: spendColor, fontWeight: 700 }}>
                  {spendPct}% used
                </div>
              </>
            ) : finishedAt ? (
              <>
                <div style={{
                  fontSize: 10,
                  fontWeight: 700,
                  letterSpacing: '0.08em',
                  textTransform: 'uppercase',
                  color: mutedColor,
                }}>
                  Finished
                </div>
                <div style={{
                  marginTop: 2,
                  fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Consolas, monospace',
                  fontSize: 13,
                  fontWeight: 600,
                  color: textColor,
                }}>
                  {finishedAt}
                </div>
              </>
            ) : null}
          </div>
        )}
      </button>

      <div
        className={`run-results-body${open ? ' run-results-body-open' : ''}`}
        style={{
          display: 'grid',
          gridTemplateRows: open ? '1fr' : '0fr',
          transition: 'grid-template-rows 0.25s ease',
        }}
      >
        <div style={{ overflow: 'hidden', minHeight: 0 }}>
          <div style={{
            padding: '12px',
            display: 'flex',
            flexDirection: 'column',
            gap: 12,
            background: darkMode ? '#0d1117' : '#f6f8fa',
          }}>
            {/* Stance — one sentence on where we stand */}
            <div
              className="run-results-stance"
              style={{
                borderRadius: 8,
                border: `1px solid ${verdict ? verdictTone.border : borderColor}`,
                background: verdict
                  ? (darkMode
                    ? `linear-gradient(135deg, ${verdictTone.bg} 0%, #0d1117 70%)`
                    : `linear-gradient(135deg, ${verdictTone.bg} 0%, #ffffff 70%)`)
                  : surface,
                padding: '11px 13px',
                display: 'flex',
                gap: 14,
                alignItems: 'flex-start',
                flexWrap: 'wrap',
              }}
            >
              <div style={{ minWidth: 0, flex: '1 1 220px' }}>
                <div style={{
                  fontSize: 18,
                  fontWeight: 700,
                  letterSpacing: '-0.02em',
                  color: verdict ? verdictTone.fg : statusMeta.color,
                  lineHeight: 1.25,
                }}>
                  {verdict
                    ? `${verdictTone.label}${status ? ` · ${statusMeta.label}` : ''}`
                    : (statusMeta.label || 'Run in progress')}
                </div>
                {stopReason && (
                  <div style={{
                    marginTop: 4,
                    fontSize: 12.5,
                    color: mutedColor,
                    lineHeight: 1.4,
                  }}>
                    {stopReason}
                  </div>
                )}
              </div>
              {finishedAt && (
                <div style={{
                  marginLeft: 'auto',
                  textAlign: 'right',
                  flexShrink: 0,
                }}>
                  <div style={{
                    fontSize: 10,
                    fontWeight: 700,
                    letterSpacing: '0.08em',
                    textTransform: 'uppercase',
                    color: mutedColor,
                  }}>
                    Finished
                  </div>
                  <div style={{
                    marginTop: 2,
                    fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Consolas, monospace',
                    fontSize: 13,
                    fontWeight: 600,
                    color: textColor,
                    fontVariantNumeric: 'tabular-nums',
                  }}>
                    {finishedAt}
                  </div>
                </div>
              )}
            </div>

            {/* Proposed Extension — LLM chain + one-click extend */}
            {proposalReady && (
              <div
                className="run-results-propose"
                style={{
                  borderRadius: 8,
                  border: `1px solid ${darkMode ? '#388bfd55' : '#0969da44'}`,
                  background: darkMode
                    ? 'linear-gradient(135deg, #0d2140 0%, #0d1117 65%)'
                    : 'linear-gradient(135deg, #ddf4ff 0%, #ffffff 65%)',
                  padding: '11px 12px',
                }}
              >
                <div style={{
                  display: 'flex',
                  alignItems: 'flex-start',
                  gap: 10,
                  flexWrap: 'wrap',
                }}>
                  <div style={{ minWidth: 0, flex: '1 1 220px' }}>
                    <div style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: 8,
                      flexWrap: 'wrap',
                      marginBottom: 6,
                    }}>
                      <span style={{
                        fontSize: 10,
                        fontWeight: 800,
                        letterSpacing: '0.08em',
                        textTransform: 'uppercase',
                        color: darkMode ? '#79c0ff' : '#0969da',
                      }}>
                        Proposed Extension
                      </span>
                      {proposalGenerating && (
                        <span
                          className="run-results-pill"
                          style={{
                            color: '#d29922',
                            background: '#9a670022',
                            border: '1px solid #d2992266',
                          }}
                        >
                          Generating
                        </span>
                      )}
                      {!proposalGenerating && proposal?.source && (
                        <span
                          className="run-results-pill"
                          style={{
                            color: mutedColor,
                            background: darkMode ? '#21262d' : '#eaeef2',
                            border: `1px solid ${borderColor}`,
                          }}
                        >
                          {proposal.source === 'llm'
                            ? (proposal.engine || 'LLM')
                            : 'Draft'}
                        </span>
                      )}
                    </div>
                    <p style={{
                      margin: 0,
                      fontSize: 13.5,
                      lineHeight: 1.45,
                      color: textColor,
                      fontWeight: 600,
                    }}>
                      {proposalNote}
                    </p>
                    {proposal?.rationale && (
                      <p style={{
                        margin: '6px 0 0',
                        fontSize: 12,
                        lineHeight: 1.45,
                        color: mutedColor,
                      }}>
                        {proposal.rationale}
                      </p>
                    )}
                  </div>
                  <button
                    type="button"
                    className="run-results-extend-btn"
                    onClick={() => { void runExtend(); }}
                    disabled={!extendEnabled || extendBusy || !proposalNote}
                    title={
                      !extendEnabled
                        ? 'Extend available when the mission is idle / completed'
                        : 'Start follow-on run with this proposal'
                    }
                    style={{
                      flexShrink: 0,
                      marginLeft: 'auto',
                      alignSelf: 'center',
                      padding: '8px 14px',
                      borderRadius: 8,
                      border: `1px solid ${
                        (!extendEnabled || extendBusy)
                          ? borderColor
                          : '#238636'
                      }`,
                      background: (!extendEnabled || extendBusy)
                        ? (darkMode ? '#21262d' : '#e1e4e8')
                        : '#238636',
                      color: (!extendEnabled || extendBusy)
                        ? mutedColor
                        : '#ffffff',
                      fontSize: 13,
                      fontWeight: 700,
                      cursor: (!extendEnabled || extendBusy) ? 'not-allowed' : 'pointer',
                      letterSpacing: '0.01em',
                      boxShadow: (!extendEnabled || extendBusy)
                        ? 'none'
                        : '0 0 0 1px #23863655',
                    }}
                  >
                    {extendBusy ? 'Starting…' : 'Extend'}
                  </button>
                </div>

                {extendError && (
                  <div style={{
                    marginTop: 8,
                    fontSize: 12,
                    fontWeight: 600,
                    color: '#f85149',
                  }}>
                    {extendError}
                  </div>
                )}

                {Array.isArray(proposal?.chain) && proposal.chain.length > 0 && (
                  <div style={{ marginTop: 10 }}>
                    <button
                      type="button"
                      onClick={() => setChainOpen(v => !v)}
                      aria-expanded={chainOpen}
                      style={{
                        display: 'inline-flex',
                        alignItems: 'center',
                        gap: 6,
                        background: 'none',
                        border: 'none',
                        padding: 0,
                        color: darkMode ? '#79c0ff' : '#0969da',
                        fontSize: 12,
                        fontWeight: 600,
                        cursor: 'pointer',
                      }}
                    >
                      <Chevron open={chainOpen} />
                      {chainOpen ? 'Hide' : 'Show'} prompt / response chain
                      <span style={{ color: mutedColor, fontWeight: 500 }}>
                        · {proposal.chain.length}
                      </span>
                    </button>
                    {chainOpen && (
                      <div
                        className="run-results-chain"
                        style={{
                          marginTop: 8,
                          display: 'flex',
                          flexDirection: 'column',
                          gap: 8,
                        }}
                      >
                        {proposal.chain.map((step, i) => (
                          <div
                            key={`${step.role}-${i}`}
                            style={{
                              borderRadius: 6,
                              border: `1px solid ${borderColor}`,
                              background: surface,
                              padding: '8px 10px',
                            }}
                          >
                            <div style={{
                              fontSize: 10,
                              fontWeight: 800,
                              letterSpacing: '0.08em',
                              textTransform: 'uppercase',
                              color: mutedColor,
                              marginBottom: 4,
                            }}>
                              {chainRoleLabel(step.role)}
                            </div>
                            <pre
                              className="run-results-chain-body"
                              style={{
                                margin: 0,
                                fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Consolas, monospace',
                                fontSize: 11.5,
                                lineHeight: 1.45,
                                color: textColor,
                                whiteSpace: 'pre-wrap',
                                wordBreak: 'break-word',
                                maxHeight: step.role === 'prompt' ? 160 : 220,
                                overflow: 'auto',
                              }}
                            >
                              {step.content}
                            </pre>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                )}
              </div>
            )}

            {/* Metric strip */}
            <div className="run-results-metrics">
              {spend && (
                <Metric
                  label="Spend"
                  value={formatCostWithTokens(spend.costUsd, spend.tokensTotal)}
                  hint={`of ${formatUsd(spend.maxCostUsd)} · ${formatUsd(spend.remainingUsd)} left`}
                  mutedColor={mutedColor}
                  textColor={textColor}
                  borderColor={borderColor}
                  background={surface}
                />
              )}
              {spend && (
                <Metric
                  label="Budget"
                  value={`${spendPct}%`}
                  hint={`of ${formatUsd(spend.maxCostUsd)} mission`}
                  accent={spendColor}
                  mutedColor={mutedColor}
                  textColor={textColor}
                  borderColor={borderColor}
                  background={surface}
                />
              )}
              {mission && (
                <Metric
                  label="Iterations"
                  value={String(mission.iteration)}
                  hint={status ? statusMeta.label : 'this run'}
                  mutedColor={mutedColor}
                  textColor={textColor}
                  borderColor={borderColor}
                  background={surface}
                />
              )}
              {critic && (
                <Metric
                  label="Critic"
                  value={formatDuration(critic.wallSeconds)}
                  hint={[
                    critic.outcome === 'finished' ? 'finished' : critic.outcome,
                    formatCostWithTokens(critic.costUsd, critic.tokens),
                    typeof critic.turns === 'number' ? `${critic.turns} turns` : '',
                  ].filter(Boolean).join(' · ')}
                  mutedColor={mutedColor}
                  textColor={textColor}
                  borderColor={borderColor}
                  background={surface}
                />
              )}
            </div>

            {spend && (
              <div
                className="run-results-budget-track"
                style={{
                  height: 4,
                  borderRadius: 2,
                  background: darkMode ? '#21262d' : '#e1e4e8',
                  overflow: 'hidden',
                }}
                title={`${spendPct}% of mission budget used`}
              >
                <div
                  style={{
                    width: `${Math.max(0, Math.min(100, spendPct))}%`,
                    height: '100%',
                    borderRadius: 2,
                    background: spendColor,
                    transition: 'width 0.45s ease',
                  }}
                />
              </div>
            )}

            {/* Verdict summary */}
            {summary && (
              <div style={{
                borderRadius: 8,
                border: `1px solid ${borderColor}`,
                background: surface,
                padding: '10px 12px',
              }}>
                <div style={{
                  fontSize: 10,
                  fontWeight: 700,
                  letterSpacing: '0.08em',
                  textTransform: 'uppercase',
                  color: mutedColor,
                  marginBottom: 6,
                }}>
                  Critic notes
                </div>
                <p
                  className={
                    summaryExpanded || !summaryLong
                      ? 'run-results-summary'
                      : 'run-results-summary run-results-summary-clamp'
                  }
                  style={{
                    margin: 0,
                    fontSize: 13,
                    lineHeight: 1.5,
                    color: textColor,
                  }}
                >
                  {summary}
                </p>
                {summaryLong && (
                  <button
                    type="button"
                    onClick={() => setSummaryExpanded(v => !v)}
                    style={{
                      marginTop: 6,
                      background: 'none',
                      border: 'none',
                      padding: 0,
                      color: '#58a6ff',
                      fontSize: 12,
                      fontWeight: 600,
                      cursor: 'pointer',
                    }}
                  >
                    {summaryExpanded ? 'Show less' : 'Show more'}
                  </button>
                )}
              </div>
            )}

            {findings.length > 0 && (
              <div style={{
                borderRadius: 8,
                border: `1px solid ${VERDICT_TONE.HOLD.border}`,
                background: darkMode ? '#3d2e0a55' : '#fff8c5aa',
                padding: '10px 12px',
              }}>
                <div style={{
                  fontSize: 10,
                  fontWeight: 700,
                  letterSpacing: '0.08em',
                  textTransform: 'uppercase',
                  color: VERDICT_TONE.HOLD.fg,
                  marginBottom: 6,
                }}>
                  Blocking findings · {findings.length}
                </div>
                <ul style={{
                  margin: 0,
                  padding: '0 0 0 16px',
                  display: 'flex',
                  flexDirection: 'column',
                  gap: 4,
                  fontSize: 12.5,
                  lineHeight: 1.45,
                  color: textColor,
                }}>
                  {findings.map((finding, i) => (
                    <li key={`${i}-${finding.slice(0, 24)}`}>{finding}</li>
                  ))}
                </ul>
              </div>
            )}

            {critic?.limitReached && (
              <div style={{
                fontSize: 12,
                fontWeight: 600,
                color: '#f85149',
                padding: '0 2px',
              }}>
                Critic cut off by limit “{critic.limitReached}”
              </div>
            )}
          </div>
        </div>
      </div>
    </section>
  );
}

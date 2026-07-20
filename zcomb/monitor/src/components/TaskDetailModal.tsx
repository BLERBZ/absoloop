import { Fragment, useEffect, useState } from 'react';
import type { ReactNode } from 'react';
import type { Task } from '../hooks/usePolling';

const statusMeta: Record<string, { label: string; icon: string; color: string }> = {
  inbox: { label: 'Inbox', icon: '○', color: '#7d8590' },
  assigned: { label: 'Assigned', icon: '◎', color: '#d29922' },
  in_progress: { label: 'In Progress', icon: '◉', color: '#58a6ff' },
  review: { label: 'Review', icon: '◈', color: '#a371f7' },
  done: { label: 'Done', icon: '✓', color: '#3fb950' },
  failed: { label: 'Failed', icon: '✕', color: '#f85149' },
};

const priorityMeta: Record<string, { label: string; color: string }> = {
  high: { label: 'High', color: '#f85149' },
  medium: { label: 'Medium', color: '#d29922' },
  low: { label: 'Low', color: '#7d8590' },
};

const verdictColor: Record<string, string> = {
  APPROVE: '#3fb950',
  PASS: '#3fb950',
  REJECT: '#f85149',
  FAIL: '#f85149',
  REVISE: '#d29922',
};

function kindLabel(task: Task): string {
  if (task.kind === 'report') return 'Mission report';
  if (task.kind === 'past_run' || task.id.startsWith('run-')) return 'Prior loop';
  if (task.id.startsWith('iter-')) return 'Iteration';
  if (task.id.startsWith('task-')) return 'Pipeline stage';
  return 'Task';
}

function formatTimestamp(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  const abs = d.toLocaleString(undefined, {
    month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit',
  });
  const diffMs = Date.now() - d.getTime();
  if (diffMs < 0) return abs;
  const mins = Math.floor(diffMs / 60_000);
  let rel: string;
  if (mins < 1) rel = 'just now';
  else if (mins < 60) rel = `${mins}m ago`;
  else if (mins < 60 * 24) rel = `${Math.floor(mins / 60)}h ago`;
  else rel = `${Math.floor(mins / (60 * 24))}d ago`;
  return `${abs} · ${rel}`;
}

/** Shorten an absolute path to its most meaningful trailing segments. */
function shortPath(p: string): string {
  const parts = p.replace(/\/+$/, '').split('/');
  if (parts.length <= 4) return p;
  return parts.slice(-4).join('/');
}

export function TaskDetailModal({ task, assigneeName, darkMode, onClose }: {
  task: Task;
  assigneeName: string;
  darkMode: boolean;
  onClose: () => void;
}) {
  const [copied, setCopied] = useState<string | null>(null);

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.preventDefault();
        onClose();
      }
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [onClose]);

  const bgOverlay = darkMode ? 'rgba(1, 4, 9, 0.78)' : 'rgba(0, 0, 0, 0.45)';
  const cardBg = darkMode ? '#161b22' : '#ffffff';
  const insetBg = darkMode ? '#0d1117' : '#f6f8fa';
  const hairline = darkMode ? '#21262d' : '#e8e8e8';
  const borderColor = darkMode ? '#30363d' : '#d0d7de';
  const textColor = darkMode ? '#e6edf3' : '#1f2328';
  const mutedColor = darkMode ? '#7d8590' : '#656d76';
  const subText = darkMode ? '#8b949e' : '#57606a';

  const status = statusMeta[task.status] || statusMeta.inbox;
  const priority = priorityMeta[task.priority] || priorityMeta.low;
  const details = task.details || {};
  const isIteration = task.id.startsWith('iter-');

  const descLines = (task.description || '').split('\n');
  const summaryLine = descLines[0] || '';
  const body = details.excerpt
    || (details.summary ? '' : descLines.slice(1).join('\n').trim());

  const copyText = async (label: string, value: string) => {
    try {
      await navigator.clipboard.writeText(value);
      setCopied(label);
      window.setTimeout(() => setCopied(null), 1400);
    } catch {
      // Clipboard may be unavailable in insecure contexts
    }
  };

  // ── Hero stats: the 2-4 numbers that matter most, shown big ──────────
  const iterationCount = details.iterations ?? details.iteration;
  const heroStats: { label: string; value: string; accent?: string }[] = [];
  if (iterationCount != null) {
    heroStats.push({
      label: isIteration ? 'Iteration' : 'Iterations',
      value: details.maxIterations
        ? `${iterationCount}/${details.maxIterations}`
        : String(iterationCount),
    });
  }
  if (details.costUsd) {
    heroStats.push({
      label: details.budgetUsd ? `Spend of $${details.budgetUsd.toFixed(0)}` : 'Spend',
      value: `$${details.costUsd.toFixed(2)}`,
    });
  }
  if (details.filesChanged) {
    heroStats.push({
      label: isIteration ? 'Artifacts touched' : 'Files changed',
      value: String(details.filesChanged),
    });
  }
  if (details.tokens) heroStats.push({ label: 'Tokens', value: details.tokens });
  if (details.criticVerdict) {
    heroStats.push({
      label: 'Critic',
      value: details.criticVerdict,
      accent: verdictColor[details.criticVerdict] || '#a371f7',
    });
  } else if (details.outcome) {
    heroStats.push({ label: 'Outcome', value: details.outcome, accent: status.color });
  }

  // ── Secondary meta: quiet key-value rows, no boxes ────────────────────
  const metaRows: { label: string; value: string; color?: string }[] = [
    { label: 'Assignee', value: assigneeName || '—' },
    ...(details.engine ? [{ label: 'Engine', value: details.engine }] : []),
    { label: 'Priority', value: `${priority.label} · P${task.phase}`, color: priority.color },
    ...(details.statusLabel && details.statusLabel !== details.outcome
      ? [{ label: 'Run status', value: details.statusLabel }]
      : []),
    ...(details.generatedAt ? [{ label: 'Report generated', value: details.generatedAt }] : []),
    { label: 'Created', value: formatTimestamp(task.createdAt) },
    { label: 'Updated', value: formatTimestamp(task.updatedAt) },
  ];

  const chip = (label: string, color: string, icon?: string) => (
    <span style={{
      display: 'inline-flex',
      alignItems: 'center',
      gap: 5,
      fontSize: 11,
      fontWeight: 700,
      color,
      background: `${color}18`,
      border: `1px solid ${color}33`,
      padding: '2px 9px',
      borderRadius: 999,
      whiteSpace: 'nowrap',
    }}>
      {icon && <span style={{ fontSize: 10, lineHeight: 1 }}>{icon}</span>}
      {label}
    </span>
  );

  const sectionLabel = (label: string) => (
    <div style={{
      fontSize: 10,
      fontWeight: 700,
      textTransform: 'uppercase',
      letterSpacing: 1,
      color: mutedColor,
      marginBottom: 7,
    }}>
      {label}
    </div>
  );

  const section = (label: string, node: ReactNode) => (
    <div style={{ padding: '14px 0', borderTop: `1px solid ${hairline}` }}>
      {sectionLabel(label)}
      {node}
    </div>
  );

  return (
    <div
      className="modal-backdrop-fade-in"
      onClick={onClose}
      style={{
        position: 'fixed',
        inset: 0,
        background: bgOverlay,
        zIndex: 10000,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        padding: 20,
      }}
    >
      <div
        className="modal-content-scale-in"
        role="dialog"
        aria-modal="true"
        aria-label={task.title}
        onClick={e => e.stopPropagation()}
        style={{
          background: cardBg,
          border: `1px solid ${borderColor}`,
          borderRadius: 14,
          maxWidth: 620,
          width: '94vw',
          maxHeight: '86vh',
          display: 'flex',
          flexDirection: 'column',
          overflow: 'hidden',
          boxShadow: darkMode
            ? '0 16px 48px rgba(0, 0, 0, 0.5), 0 4px 16px rgba(0, 0, 0, 0.4)'
            : '0 16px 48px rgba(0, 0, 0, 0.15), 0 4px 16px rgba(0, 0, 0, 0.1)',
        }}
      >
        {/* Header */}
        <div style={{ padding: '18px 24px 0', flexShrink: 0 }}>
          <div style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            gap: 10,
            marginBottom: 12,
          }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
              {chip(status.label, status.color, status.icon)}
              {chip(kindLabel(task), '#58a6ff')}
            </div>
            <button
              onClick={onClose}
              aria-label="Close details"
              style={{
                background: 'none',
                border: 'none',
                color: mutedColor,
                fontSize: 18,
                cursor: 'pointer',
                padding: '2px 6px',
                borderRadius: 4,
                lineHeight: 1,
                flexShrink: 0,
              }}
              onMouseEnter={e => (e.currentTarget.style.color = textColor)}
              onMouseLeave={e => (e.currentTarget.style.color = mutedColor)}
            >
              ✕
            </button>
          </div>
          <h2 style={{
            margin: 0,
            fontSize: 17,
            fontWeight: 700,
            lineHeight: 1.35,
            color: textColor,
            wordBreak: 'break-word',
          }}>
            {task.title}
          </h2>
          {summaryLine && summaryLine !== task.title
            && summaryLine !== details.summary && (
            <div style={{
              marginTop: 6,
              fontSize: 12,
              color: subText,
              lineHeight: 1.45,
              wordBreak: 'break-word',
            }}>
              {summaryLine}
            </div>
          )}

          {/* Hero stat strip */}
          {heroStats.length > 0 && (
            <div style={{
              display: 'flex',
              alignItems: 'stretch',
              gap: 0,
              margin: '16px 0 0',
              background: insetBg,
              border: `1px solid ${hairline}`,
              borderRadius: 10,
              overflow: 'hidden',
            }}>
              {heroStats.map((s, idx) => (
                <div key={s.label} style={{
                  flex: 1,
                  minWidth: 0,
                  padding: '10px 14px',
                  borderLeft: idx > 0 ? `1px solid ${hairline}` : 'none',
                }}>
                  <div style={{
                    fontSize: 15,
                    fontWeight: 700,
                    color: s.accent || textColor,
                    overflow: 'hidden',
                    textOverflow: 'ellipsis',
                    whiteSpace: 'nowrap',
                    letterSpacing: -0.2,
                  }}>
                    {s.value}
                  </div>
                  <div style={{
                    fontSize: 9,
                    fontWeight: 700,
                    textTransform: 'uppercase',
                    letterSpacing: 0.8,
                    color: mutedColor,
                    marginTop: 2,
                    overflow: 'hidden',
                    textOverflow: 'ellipsis',
                    whiteSpace: 'nowrap',
                  }}>
                    {s.label}
                  </div>
                </div>
              ))}
            </div>
          )}
          <div style={{ height: 16 }} />
        </div>

        {/* Body — scrolls */}
        <div style={{ padding: '0 24px 10px', overflowY: 'auto', minHeight: 0 }}>
          {/* Builder summary (iteration cards) */}
          {details.summary && section('What the builder did',
            <div style={{
              fontSize: 13,
              lineHeight: 1.6,
              color: textColor,
              wordBreak: 'break-word',
            }}>
              {details.summary}
            </div>,
          )}

          {/* Critic verdict */}
          {details.criticVerdict && details.criticSummary && section('Critic review',
            <div style={{ fontSize: 12.5, lineHeight: 1.6, color: subText, wordBreak: 'break-word' }}>
              <span style={{
                fontWeight: 700,
                color: verdictColor[details.criticVerdict] || '#a371f7',
                marginRight: 6,
              }}>
                {details.criticVerdict}
              </span>
              {details.criticSummary}
            </div>,
          )}

          {/* Live activity */}
          {details.nowLine && section('Currently running',
            <div style={{
              fontSize: 12,
              lineHeight: 1.55,
              color: textColor,
              fontFamily: 'monospace',
              background: insetBg,
              border: `1px solid ${hairline}`,
              borderRadius: 8,
              padding: '9px 12px',
              wordBreak: 'break-word',
            }}>
              {details.nowLine}
            </div>,
          )}

          {/* Changed artifacts */}
          {details.changedArtifacts && details.changedArtifacts.length > 0 && section(
            `Changed artifacts${details.filesChanged && details.filesChanged > details.changedArtifacts.length
              ? ` · showing ${details.changedArtifacts.length} of ${details.filesChanged}` : ''}`,
            <div style={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
              {details.changedArtifacts.map(p => (
                <div key={p} style={{
                  fontSize: 11,
                  color: subText,
                  fontFamily: 'monospace',
                  overflow: 'hidden',
                  textOverflow: 'ellipsis',
                  whiteSpace: 'nowrap',
                }} title={p}>
                  {shortPath(p)}
                </div>
              ))}
            </div>,
          )}

          {/* Verification commands */}
          {details.commandsRun && details.commandsRun.length > 0 && section('Verification',
            <div style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
              {details.commandsRun.map(c => (
                <div key={c} style={{
                  fontSize: 11.5,
                  color: subText,
                  fontFamily: 'monospace',
                  lineHeight: 1.5,
                  display: 'flex',
                  gap: 7,
                  wordBreak: 'break-word',
                }}>
                  <span aria-hidden style={{ color: '#3fb950', flexShrink: 0 }}>›</span>
                  <span>{c}</span>
                </div>
              ))}
            </div>,
          )}

          {/* Open risks */}
          {details.risks && details.risks.length > 0 && section('Open risks',
            <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
              {details.risks.map(r => (
                <div key={r} style={{
                  fontSize: 12,
                  lineHeight: 1.55,
                  color: subText,
                  display: 'flex',
                  gap: 7,
                  wordBreak: 'break-word',
                }}>
                  <span aria-hidden style={{ color: '#d29922', flexShrink: 0 }}>▲</span>
                  <span>{r}</span>
                </div>
              ))}
            </div>,
          )}

          {/* Objective */}
          {details.objective && section('Objective',
            <div style={{
              fontSize: 12.5,
              lineHeight: 1.6,
              color: subText,
              borderLeft: `3px solid ${darkMode ? '#30363d' : '#d0d7de'}`,
              paddingLeft: 12,
              wordBreak: 'break-word',
            }}>
              {details.objective}
            </div>,
          )}

          {/* Top changed areas */}
          {details.areas && details.areas.length > 0 && section('Most changed areas',
            <div style={{ display: 'flex', gap: 5, flexWrap: 'wrap' }}>
              {details.areas.map(area => (
                <span key={area} style={{
                  fontSize: 11,
                  color: subText,
                  background: insetBg,
                  border: `1px solid ${hairline}`,
                  padding: '2px 8px',
                  borderRadius: 5,
                  fontFamily: 'monospace',
                }}>
                  {area}
                </span>
              ))}
            </div>,
          )}

          {/* Extend focus note */}
          {details.focus && section('Continuation focus',
            <div style={{ fontSize: 13, lineHeight: 1.55, color: textColor, wordBreak: 'break-word' }}>
              {details.focus}
            </div>,
          )}

          {/* Report / description body */}
          {body && section(details.excerpt ? 'Report excerpt' : 'Details',
            <div style={{
              fontSize: 12.5,
              lineHeight: 1.6,
              color: subText,
              whiteSpace: 'pre-wrap',
              wordBreak: 'break-word',
            }}>
              {body}
            </div>,
          )}

          {/* Meta rows + identifiers, one quiet block */}
          <div style={{ padding: '14px 0 6px', borderTop: `1px solid ${hairline}` }}>
            <div style={{
              display: 'grid',
              gridTemplateColumns: 'max-content 1fr',
              columnGap: 18,
              rowGap: 6,
              alignItems: 'baseline',
            }}>
              {metaRows.map(row => (
                <Fragment key={row.label}>
                  <div style={{
                    fontSize: 10,
                    fontWeight: 700,
                    textTransform: 'uppercase',
                    letterSpacing: 0.8,
                    color: mutedColor,
                  }}>
                    {row.label}
                  </div>
                  <div style={{
                    fontSize: 12,
                    fontWeight: 500,
                    color: row.color || textColor,
                    overflow: 'hidden',
                    textOverflow: 'ellipsis',
                    whiteSpace: 'nowrap',
                  }}>
                    {row.value}
                  </div>
                </Fragment>
              ))}
              {task.dependencies.length > 0 && (
                <>
                  <div style={{
                    fontSize: 10,
                    fontWeight: 700,
                    textTransform: 'uppercase',
                    letterSpacing: 0.8,
                    color: mutedColor,
                  }}>
                    Depends on
                  </div>
                  <div style={{ display: 'flex', gap: 5, flexWrap: 'wrap' }}>
                    {task.dependencies.map(dep => (
                      <span key={dep} style={{
                        fontSize: 10.5,
                        color: subText,
                        background: insetBg,
                        border: `1px solid ${hairline}`,
                        padding: '1px 7px',
                        borderRadius: 5,
                        fontFamily: 'monospace',
                      }}>
                        {dep.replace('task-', '#').replace('iter-', 'iter #')}
                      </span>
                    ))}
                  </div>
                </>
              )}
              {details.loopId && (
                <>
                  <div style={{
                    fontSize: 10,
                    fontWeight: 700,
                    textTransform: 'uppercase',
                    letterSpacing: 0.8,
                    color: mutedColor,
                  }}>
                    Loop
                  </div>
                  <div style={{
                    fontSize: 11,
                    color: subText,
                    fontFamily: 'monospace',
                    overflow: 'hidden',
                    textOverflow: 'ellipsis',
                    whiteSpace: 'nowrap',
                  }}>
                    {details.loopId}
                  </div>
                </>
              )}
              {details.missionId && details.missionId !== details.loopId && (
                <>
                  <div style={{
                    fontSize: 10,
                    fontWeight: 700,
                    textTransform: 'uppercase',
                    letterSpacing: 0.8,
                    color: mutedColor,
                  }}>
                    Mission
                  </div>
                  <div style={{
                    fontSize: 11,
                    color: subText,
                    fontFamily: 'monospace',
                    overflow: 'hidden',
                    textOverflow: 'ellipsis',
                    whiteSpace: 'nowrap',
                  }}>
                    {details.missionId}
                  </div>
                </>
              )}
            </div>
          </div>
        </div>

        {/* Footer — links & actions */}
        <div style={{
          padding: '12px 24px',
          borderTop: `1px solid ${hairline}`,
          display: 'flex',
          alignItems: 'center',
          gap: 8,
          flexWrap: 'wrap',
          flexShrink: 0,
          background: darkMode ? '#0d111780' : '#f6f8fa80',
        }}>
          {details.reportUrl && (
            <a
              href={details.reportUrl}
              target="_blank"
              rel="noreferrer"
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: 6,
                fontSize: 12,
                fontWeight: 700,
                color: '#0d1117',
                background: '#58a6ff',
                border: '1px solid #58a6ff',
                padding: '6px 14px',
                borderRadius: 6,
                textDecoration: 'none',
                whiteSpace: 'nowrap',
              }}
            >
              Open full report
              <span aria-hidden style={{ fontSize: 11 }}>↗</span>
            </a>
          )}
          {details.loopId && (
            <button
              type="button"
              onClick={() => void copyText('loop', details.loopId!)}
              style={{
                fontSize: 12,
                fontWeight: 600,
                color: copied === 'loop' ? '#3fb950' : subText,
                background: 'none',
                border: `1px solid ${borderColor}`,
                padding: '6px 12px',
                borderRadius: 6,
                cursor: 'pointer',
                whiteSpace: 'nowrap',
              }}
            >
              {copied === 'loop' ? 'Copied!' : 'Copy loop ID'}
            </button>
          )}
          <button
            type="button"
            onClick={() => void copyText('task', task.id)}
            style={{
              fontSize: 12,
              fontWeight: 600,
              color: copied === 'task' ? '#3fb950' : subText,
              background: 'none',
              border: `1px solid ${borderColor}`,
              padding: '6px 12px',
              borderRadius: 6,
              cursor: 'pointer',
              whiteSpace: 'nowrap',
            }}
          >
            {copied === 'task' ? 'Copied!' : 'Copy task ID'}
          </button>
          <span style={{ marginLeft: 'auto', fontSize: 10, color: mutedColor, whiteSpace: 'nowrap' }}>
            Esc to close
          </span>
        </div>
      </div>
    </div>
  );
}

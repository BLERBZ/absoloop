import { useEffect, useState } from 'react';
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
  const borderColor = darkMode ? '#30363d' : '#d0d7de';
  const textColor = darkMode ? '#e6edf3' : '#1f2328';
  const mutedColor = darkMode ? '#7d8590' : '#656d76';
  const subText = darkMode ? '#8b949e' : '#57606a';

  const status = statusMeta[task.status] || statusMeta.inbox;
  const priority = priorityMeta[task.priority] || priorityMeta.low;
  const details = task.details || {};

  // Description body: prefer the richer bridge excerpt; else everything
  // after the first summary line of the card description.
  const descLines = (task.description || '').split('\n');
  const summaryLine = descLines[0] || '';
  const body = details.excerpt || descLines.slice(1).join('\n').trim();

  const copyText = async (label: string, value: string) => {
    try {
      await navigator.clipboard.writeText(value);
      setCopied(label);
      window.setTimeout(() => setCopied(null), 1400);
    } catch {
      // Clipboard may be unavailable in insecure contexts
    }
  };

  const iterationCount = details.iterations ?? details.iteration;
  const dataPoints: { label: string; value: string; mono?: boolean }[] = [
    ...(details.outcome ? [{ label: 'Outcome', value: details.outcome }] : []),
    { label: 'Assignee', value: assigneeName || '—' },
    { label: 'Priority', value: priority.label },
    { label: 'Phase', value: `P${task.phase}` },
    ...(details.engine ? [{ label: 'Engine', value: details.engine }] : []),
    ...(iterationCount != null
      ? [{
          label: task.id.startsWith('iter-') ? 'Iteration' : 'Iterations',
          value: details.maxIterations
            ? `${iterationCount} / ${details.maxIterations}`
            : String(iterationCount),
        }]
      : []),
    ...(details.costUsd
      ? [{
          label: 'Spend',
          value: details.budgetUsd
            ? `$${details.costUsd.toFixed(2)} of $${details.budgetUsd.toFixed(2)}`
            : `$${details.costUsd.toFixed(2)}`,
        }]
      : []),
    ...(details.tokens ? [{ label: 'Tokens', value: details.tokens }] : []),
    ...(details.filesChanged
      ? [{ label: 'Files changed', value: String(details.filesChanged) }]
      : []),
    ...(details.statusLabel && details.statusLabel !== details.outcome
      ? [{ label: 'Run status', value: details.statusLabel }]
      : []),
    ...(details.generatedAt
      ? [{ label: 'Report generated', value: details.generatedAt }]
      : []),
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
      marginBottom: 6,
    }}>
      {label}
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
          borderRadius: 12,
          maxWidth: 640,
          width: '94vw',
          maxHeight: '84vh',
          display: 'flex',
          flexDirection: 'column',
          overflow: 'hidden',
          boxShadow: darkMode
            ? '0 16px 48px rgba(0, 0, 0, 0.5), 0 4px 16px rgba(0, 0, 0, 0.4)'
            : '0 16px 48px rgba(0, 0, 0, 0.15), 0 4px 16px rgba(0, 0, 0, 0.1)',
        }}
      >
        {/* Header */}
        <div style={{
          padding: '18px 22px 14px',
          borderBottom: `1px solid ${darkMode ? '#21262d' : '#e8e8e8'}`,
          flexShrink: 0,
        }}>
          <div style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            gap: 10,
            marginBottom: 10,
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
          {summaryLine && summaryLine !== task.title && (
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
        </div>

        {/* Body — scrolls */}
        <div style={{ padding: '16px 22px', overflowY: 'auto', minHeight: 0 }}>
          {/* Data points */}
          <div style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fill, minmax(150px, 1fr))',
            gap: 10,
            marginBottom: 16,
          }}>
            {dataPoints.map(dp => (
              <div key={dp.label} style={{
                background: insetBg,
                border: `1px solid ${darkMode ? '#21262d' : '#e8e8e8'}`,
                borderRadius: 8,
                padding: '7px 10px',
                minWidth: 0,
              }}>
                <div style={{
                  fontSize: 9,
                  fontWeight: 700,
                  textTransform: 'uppercase',
                  letterSpacing: 0.8,
                  color: mutedColor,
                  marginBottom: 2,
                }}>
                  {dp.label}
                </div>
                <div style={{
                  fontSize: 12,
                  fontWeight: 600,
                  color: textColor,
                  overflow: 'hidden',
                  textOverflow: 'ellipsis',
                  whiteSpace: 'nowrap',
                  fontFamily: dp.mono ? 'monospace' : undefined,
                }}>
                  {dp.value}
                </div>
              </div>
            ))}
          </div>

          {/* Objective */}
          {details.objective && (
            <div style={{ marginBottom: 16 }}>
              {sectionLabel('Objective')}
              <div style={{
                fontSize: 13,
                lineHeight: 1.55,
                color: textColor,
                background: insetBg,
                border: `1px solid ${darkMode ? '#21262d' : '#e8e8e8'}`,
                borderLeft: `3px solid #58a6ff`,
                borderRadius: 8,
                padding: '10px 12px',
                wordBreak: 'break-word',
              }}>
                {details.objective}
              </div>
            </div>
          )}

          {/* Top changed areas */}
          {details.areas && details.areas.length > 0 && (
            <div style={{ marginBottom: 16 }}>
              {sectionLabel('Most changed areas')}
              <div style={{ display: 'flex', gap: 5, flexWrap: 'wrap' }}>
                {details.areas.map(area => (
                  <span key={area} style={{
                    fontSize: 11,
                    color: subText,
                    background: insetBg,
                    border: `1px solid ${darkMode ? '#21262d' : '#e1e4e8'}`,
                    padding: '2px 8px',
                    borderRadius: 5,
                    fontFamily: 'monospace',
                  }}>
                    {area}
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* Extend focus note */}
          {details.focus && (
            <div style={{ marginBottom: 16 }}>
              {sectionLabel('Continuation focus')}
              <div style={{ fontSize: 13, lineHeight: 1.55, color: textColor, wordBreak: 'break-word' }}>
                {details.focus}
              </div>
            </div>
          )}

          {/* Live activity */}
          {details.nowLine && (
            <div style={{ marginBottom: 16 }}>
              {sectionLabel('Currently running')}
              <div style={{
                fontSize: 12,
                lineHeight: 1.55,
                color: textColor,
                fontFamily: 'monospace',
                background: insetBg,
                border: `1px solid ${darkMode ? '#21262d' : '#e8e8e8'}`,
                borderRadius: 8,
                padding: '9px 12px',
                wordBreak: 'break-word',
              }}>
                {details.nowLine}
              </div>
            </div>
          )}

          {/* Report / description body */}
          {body && (
            <div style={{ marginBottom: 16 }}>
              {sectionLabel(details.excerpt ? 'Report excerpt' : 'Details')}
              <div style={{
                fontSize: 12.5,
                lineHeight: 1.6,
                color: subText,
                whiteSpace: 'pre-wrap',
                wordBreak: 'break-word',
              }}>
                {body}
              </div>
            </div>
          )}

          {/* Dependencies */}
          {task.dependencies.length > 0 && (
            <div style={{ marginBottom: 16 }}>
              {sectionLabel('Dependencies')}
              <div style={{ display: 'flex', gap: 5, flexWrap: 'wrap' }}>
                {task.dependencies.map(dep => (
                  <span key={dep} style={{
                    fontSize: 11,
                    color: subText,
                    background: insetBg,
                    border: `1px solid ${darkMode ? '#21262d' : '#e1e4e8'}`,
                    padding: '2px 8px',
                    borderRadius: 5,
                    fontFamily: 'monospace',
                  }}>
                    {dep.replace('task-', '#')}
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* Identifiers */}
          {(details.loopId || details.missionId) && (
            <div style={{ marginBottom: 4 }}>
              {sectionLabel('Identifiers')}
              <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                {details.loopId && (
                  <div style={{ fontSize: 11, color: subText, fontFamily: 'monospace', wordBreak: 'break-all' }}>
                    loop&nbsp;&nbsp;&nbsp;&nbsp;{details.loopId}
                  </div>
                )}
                {details.missionId && details.missionId !== details.loopId && (
                  <div style={{ fontSize: 11, color: subText, fontFamily: 'monospace', wordBreak: 'break-all' }}>
                    mission&nbsp;{details.missionId}
                  </div>
                )}
              </div>
            </div>
          )}
        </div>

        {/* Footer — links & actions */}
        <div style={{
          padding: '12px 22px',
          borderTop: `1px solid ${darkMode ? '#21262d' : '#e8e8e8'}`,
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

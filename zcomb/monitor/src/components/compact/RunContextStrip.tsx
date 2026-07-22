import { useState } from 'react';
import type { CompactTheme } from './runState';
import { ACCENT } from './runState';

/**
 * 36px run-context strip: project, one-line objective, loop id + copy.
 * Fixed height — long objectives truncate and reveal via tooltip.
 */
export function RunContextStrip({ theme, projectName, objective, loopId }: {
  theme: CompactTheme;
  projectName: string;
  objective: string;
  loopId: string;
}) {
  const [copied, setCopied] = useState(false);

  const copyId = async () => {
    try {
      await navigator.clipboard.writeText(loopId);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1500);
    } catch {
      /* clipboard unavailable in insecure contexts */
    }
  };

  return (
    <div style={{
      display: 'flex',
      alignItems: 'center',
      gap: 10,
      height: 36,
      padding: '0 12px',
      background: theme.stripBg,
      borderBottom: `1px solid ${theme.borderSoft}`,
      flexShrink: 0,
      overflow: 'hidden',
    }}>
      {projectName && (
        <span style={{
          fontSize: 12,
          fontWeight: 700,
          color: theme.text,
          whiteSpace: 'nowrap',
          flexShrink: 0,
        }}>
          {projectName}
        </span>
      )}
      {objective && (
        <span
          title={objective}
          style={{
            fontSize: 12,
            color: theme.subText,
            whiteSpace: 'nowrap',
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            minWidth: 0,
            flex: 1,
          }}
        >
          {objective}
        </span>
      )}
      {!objective && <span style={{ flex: 1 }} />}
      {loopId && (
        <button
          type="button"
          onClick={() => void copyId()}
          title={copied ? 'Copied!' : `Copy run id: ${loopId}`}
          aria-label={copied ? 'Copied' : `Copy run id ${loopId}`}
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: 5,
            background: 'none',
            border: `1px solid transparent`,
            borderRadius: 6,
            padding: '3px 6px',
            cursor: 'pointer',
            color: copied ? ACCENT.green : theme.muted,
            fontSize: 11,
            fontFamily: 'ui-monospace, monospace',
            whiteSpace: 'nowrap',
            flexShrink: 0,
            maxWidth: 180,
            overflow: 'hidden',
          }}
          onMouseEnter={e => { e.currentTarget.style.borderColor = theme.border; }}
          onMouseLeave={e => { e.currentTarget.style.borderColor = 'transparent'; }}
        >
          <span style={{ overflow: 'hidden', textOverflow: 'ellipsis' }}>{loopId}</span>
          {copied ? (
            <svg width="11" height="11" viewBox="0 0 16 16" aria-hidden="true" style={{ flexShrink: 0 }}>
              <path d="M3.5 8.5 L6.5 11.5 L12.5 4.5" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          ) : (
            <svg width="11" height="11" viewBox="0 0 16 16" aria-hidden="true" style={{ flexShrink: 0 }}>
              <rect x="5.5" y="5.5" width="8" height="8" rx="1.5" fill="none" stroke="currentColor" strokeWidth="1.4" />
              <path d="M10.5 5.5 V4 A1.5 1.5 0 0 0 9 2.5 H4 A1.5 1.5 0 0 0 2.5 4 V9 A1.5 1.5 0 0 0 4 10.5 H5.5" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          )}
        </button>
      )}
    </div>
  );
}

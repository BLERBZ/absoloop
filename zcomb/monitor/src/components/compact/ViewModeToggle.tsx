export type ViewMode = 'full' | 'compact';

const IS_MAC = typeof navigator !== 'undefined' && /Mac/i.test(navigator.platform);
export const VIEW_TOGGLE_SHORTCUT = IS_MAC ? '⌥M' : 'Alt+M';

/**
 * Full/compact view toggle — lives immediately left of the settings gear.
 * Inward corners = "minimize to compact"; outward corners = "expand to full".
 */
export function ViewModeToggle({ mode, onToggle, darkMode, borderColor, textColor }: {
  mode: ViewMode;
  onToggle: () => void;
  darkMode: boolean;
  borderColor: string;
  textColor: string;
}) {
  const compact = mode === 'compact';
  const tooltip = compact
    ? `Expand to full board (${VIEW_TOGGLE_SHORTCUT})`
    : `Open compact monitor (${VIEW_TOGGLE_SHORTCUT})`;
  const label = compact
    ? 'Switch to full board mode'
    : 'Switch to compact monitor mode';
  return (
    <button
      type="button"
      className="view-mode-toggle"
      title={tooltip}
      aria-label={label}
      onClick={onToggle}
      style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        width: 36,
        height: 36,
        minWidth: 32,
        minHeight: 32,
        padding: 0,
        background: 'transparent',
        border: '1px solid transparent',
        borderRadius: 8,
        cursor: 'pointer',
        color: textColor,
        flexShrink: 0,
        transition: 'background 0.15s ease, border-color 0.15s ease',
      }}
      onMouseEnter={e => {
        e.currentTarget.style.background = darkMode ? '#21262d' : '#e1e4e8';
        e.currentTarget.style.borderColor = borderColor;
      }}
      onMouseLeave={e => {
        e.currentTarget.style.background = 'transparent';
        e.currentTarget.style.borderColor = 'transparent';
      }}
    >
      {compact ? (
        // Outward corners — expand to full board
        <svg width="16" height="16" viewBox="0 0 16 16" aria-hidden="true" className="view-mode-toggle-icon">
          <path
            d="M9.5 2.5 H13.5 V6.5 M13.5 2.5 L9 7 M6.5 13.5 H2.5 V9.5 M2.5 13.5 L7 9"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.6"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
      ) : (
        // Inward corners — minimize to compact monitor
        <svg width="16" height="16" viewBox="0 0 16 16" aria-hidden="true" className="view-mode-toggle-icon">
          <path
            d="M13.5 6.5 H9.5 V2.5 M9.5 6.5 L14 2 M2.5 9.5 H6.5 V13.5 M6.5 9.5 L2 14"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.6"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
      )}
    </button>
  );
}

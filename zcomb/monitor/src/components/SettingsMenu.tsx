import { useEffect, useRef, useState, type CSSProperties } from 'react';
import type { Metrics, SettingsCatalogEngine } from '../hooks/usePolling';

interface SettingsMenuProps {
  metrics?: Metrics | null;
  darkMode: boolean;
  borderColor: string;
  textColor: string;
  mutedColor: string;
  onThemeChange: (dark: boolean) => void;
  onRefresh?: () => void;
}

type Flash = { ok: boolean; text: string } | null;

export async function saveSettings(body: {
  theme: 'dark' | 'light';
  engine: string;
  model: string;
}): Promise<{ ok: boolean; message: string; error?: string }> {
  const res = await fetch('/api/settings', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  let payload: {
    ok?: boolean;
    message?: string;
    error?: string;
  } = {};
  try {
    payload = await res.json();
  } catch {
    payload = {};
  }
  if (!res.ok || payload.ok === false) {
    return {
      ok: false,
      message: payload.error || payload.message || `Save failed (HTTP ${res.status})`,
      error: payload.error,
    };
  }
  return {
    ok: true,
    message: payload.message || 'Saved — applies on the next loop',
  };
}

function availableEngines(settings: Metrics['settings']): SettingsCatalogEngine[] {
  return (settings?.engines || []).filter((e) => e.available);
}

export function SettingsMenu({
  metrics,
  darkMode,
  borderColor,
  textColor,
  mutedColor,
  onThemeChange,
  onRefresh,
}: SettingsMenuProps) {
  const [open, setOpen] = useState(false);
  const [flash, setFlash] = useState<Flash>(null);
  const [saving, setSaving] = useState(false);
  const [draftTheme, setDraftTheme] = useState<'dark' | 'light'>(darkMode ? 'dark' : 'light');
  const [draftEngine, setDraftEngine] = useState('');
  const [draftModel, setDraftModel] = useState('');
  const [modelOpen, setModelOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement | null>(null);

  const settings = metrics?.settings;
  const engines = availableEngines(settings);
  const selectedEngine = engines.find((e) => e.id === draftEngine) || engines[0];
  const models = selectedEngine?.models || [];
  const modelLabel = models.find((m) => m.id === draftModel)?.label || draftModel;
  const live = Boolean(metrics?.live);

  // Seed drafts from bridge when the menu is closed (poll updates).
  useEffect(() => {
    if (!settings || open) return;
    setDraftTheme(settings.theme === 'light' ? 'light' : 'dark');
    if (settings.engine) setDraftEngine(settings.engine);
    if (settings.model) setDraftModel(settings.model);
  }, [settings?.engine, settings?.model, settings?.theme, open]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!open) {
      setModelOpen(false);
      return;
    }
    const onDoc = (event: MouseEvent) => {
      if (!menuRef.current?.contains(event.target as Node)) {
        setOpen(false);
        setModelOpen(false);
      }
    };
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        if (modelOpen) setModelOpen(false);
        else setOpen(false);
      }
    };
    document.addEventListener('mousedown', onDoc);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('mousedown', onDoc);
      document.removeEventListener('keydown', onKey);
    };
  }, [open, modelOpen]);

  // Keep model valid when engine changes.
  useEffect(() => {
    if (!selectedEngine) return;
    const ids = selectedEngine.models.map((m) => m.id);
    if (!ids.length) return;
    if (!ids.includes(draftModel)) {
      setDraftModel(ids[0]);
    }
  }, [selectedEngine?.id, draftModel]); // eslint-disable-line react-hooks/exhaustive-deps

  const onSave = async () => {
    if (saving) return;
    setSaving(true);
    setFlash(null);
    const theme = draftTheme;
    const result = await saveSettings({
      theme,
      engine: draftEngine || selectedEngine?.id || '',
      model: draftModel,
    });
    setSaving(false);
    if (result.ok) {
      onThemeChange(theme === 'dark');
      localStorage.setItem('zc-theme', theme);
      setFlash({ ok: true, text: result.message });
      onRefresh?.();
      window.setTimeout(() => setFlash(null), 3200);
    } else {
      setFlash({ ok: false, text: result.message });
    }
  };

  const menuBg = darkMode ? '#161b22' : '#ffffff';
  const menuHover = darkMode ? '#21262d' : '#eaeef2';
  const accent = darkMode ? '#58a6ff' : '#0969da';

  const segmentBtn = (active: boolean): CSSProperties => ({
    flex: 1,
    padding: '5px 8px',
    fontSize: 11,
    fontWeight: active ? 600 : 500,
    border: 'none',
    borderRadius: 5,
    cursor: 'pointer',
    background: active ? (darkMode ? '#30363d' : '#ffffff') : 'transparent',
    color: active ? textColor : mutedColor,
    boxShadow: active
      ? (darkMode ? '0 0 0 1px #484f58' : '0 0 0 1px #d0d7de')
      : 'none',
  });

  return (
    <div ref={menuRef} style={{ position: 'relative' }}>
      <button
        type="button"
        aria-label="Settings"
        aria-haspopup="menu"
        aria-expanded={open}
        title="Settings"
        onClick={() => {
          if (!open && settings) {
            setDraftTheme(settings.theme === 'light' ? 'light' : (darkMode ? 'dark' : 'light'));
            if (settings.engine) setDraftEngine(settings.engine);
            if (settings.model) setDraftModel(settings.model);
          }
          setOpen((v) => !v);
          setFlash(null);
        }}
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          width: 32,
          height: 28,
          background: open ? (darkMode ? '#21262d' : '#e1e4e8') : 'none',
          border: `1px solid ${borderColor}`,
          borderRadius: 6,
          cursor: 'pointer',
          color: textColor,
          padding: 0,
        }}
        onMouseEnter={(e) => {
          if (!open) e.currentTarget.style.background = darkMode ? '#21262d' : '#e1e4e8';
        }}
        onMouseLeave={(e) => {
          if (!open) e.currentTarget.style.background = 'none';
        }}
      >
        <svg width="14" height="14" viewBox="0 0 16 16" aria-hidden="true" fill="currentColor">
          <path d="M8 4.754a3.246 3.246 0 1 0 0 6.492 3.246 3.246 0 0 0 0-6.492zM5.754 8a2.246 2.246 0 1 1 4.492 0 2.246 2.246 0 0 1-4.492 0z" />
          <path d="M9.796 1.343c-.527-1.79-3.065-1.79-3.592 0l-.094.319a.873.873 0 0 1-1.255.52l-.292-.16c-1.64-.892-3.433.902-2.54 2.541l.159.292a.873.873 0 0 1-.52 1.255l-.319.094c-1.79.527-1.79 3.065 0 3.592l.319.094a.873.873 0 0 1 .52 1.255l-.16.292c-.892 1.64.901 3.434 2.541 2.54l.292-.159a.873.873 0 0 1 1.255.52l.094.319c.527 1.79 3.065 1.79 3.592 0l.094-.319a.873.873 0 0 1 1.255-.52l.292.16c1.64.893 3.434-.902 2.54-2.541l-.159-.292a.873.873 0 0 1 .52-1.255l.319-.094c1.79-.527 1.79-3.065 0-3.592l-.319-.094a.873.873 0 0 1-.52-1.255l.16-.292c.893-1.64-.902-3.433-2.541-2.54l-.292.159a.873.873 0 0 1-1.255-.52l-.094-.319zm-2.633.283c.246-.835 1.428-.835 1.674 0l.094.319a1.873 1.873 0 0 0 2.693 1.115l.292-.16c.764-.415 1.6.42 1.184 1.185l-.159.292a1.873 1.873 0 0 0 1.116 2.692l.318.094c.835.246.835 1.428 0 1.674l-.319.094a1.873 1.873 0 0 0-1.115 2.693l.16.292c.415.764-.42 1.6-1.185 1.184l-.292-.159a1.873 1.873 0 0 0-2.692 1.116l-.094.318c-.246.835-1.428.835-1.674 0l-.094-.319a1.873 1.873 0 0 0-2.693-1.115l-.292.16c-.764.415-1.6-.42-1.184-1.185l.159-.292A1.873 1.873 0 0 0 1.945 8.93l-.319-.094c-.835-.246-.835-1.428 0-1.674l.319-.094A1.873 1.873 0 0 0 3.38 4.468l-.16-.292c-.415-.764.42-1.6 1.185-1.184l.292.159a1.873 1.873 0 0 0 2.692-1.115l.094-.319z" />
        </svg>
      </button>

      {open && (
        <div
          role="menu"
          style={{
            position: 'absolute',
            top: 'calc(100% + 6px)',
            right: 0,
            width: 280,
            zIndex: 60,
            background: menuBg,
            border: `1px solid ${borderColor}`,
            borderRadius: 8,
            boxShadow: darkMode
              ? '0 12px 28px rgba(0,0,0,0.45)'
              : '0 12px 28px rgba(31,35,40,0.18)',
            padding: 12,
            display: 'flex',
            flexDirection: 'column',
            gap: 12,
          }}
        >
          <div style={{ fontSize: 12, fontWeight: 600, color: textColor }}>
            Settings
          </div>

          {/* Theme */}
          <div>
            <div style={{ fontSize: 10, fontWeight: 600, color: mutedColor, marginBottom: 6, letterSpacing: 0.3 }}>
              APPEARANCE
            </div>
            <div
              style={{
                display: 'flex',
                gap: 2,
                padding: 2,
                borderRadius: 7,
                background: darkMode ? '#0d1117' : '#eaeef2',
                border: `1px solid ${borderColor}`,
              }}
            >
              <button type="button" style={segmentBtn(draftTheme === 'light')} onClick={() => setDraftTheme('light')}>
                Light
              </button>
              <button type="button" style={segmentBtn(draftTheme === 'dark')} onClick={() => setDraftTheme('dark')}>
                Dark
              </button>
            </div>
          </div>

          {/* Engine */}
          <div>
            <div style={{ fontSize: 10, fontWeight: 600, color: mutedColor, marginBottom: 6, letterSpacing: 0.3 }}>
              ENGINE
            </div>
            {engines.length === 0 ? (
              <div style={{ fontSize: 11, color: mutedColor }}>
                No engines on PATH
              </div>
            ) : (
              <div
                style={{
                  display: 'flex',
                  gap: 2,
                  padding: 2,
                  borderRadius: 7,
                  background: darkMode ? '#0d1117' : '#eaeef2',
                  border: `1px solid ${borderColor}`,
                }}
              >
                {engines.map((eng) => (
                  <button
                    key={eng.id}
                    type="button"
                    style={segmentBtn(draftEngine === eng.id)}
                    onClick={() => {
                      setDraftEngine(eng.id);
                      const first = eng.models[0]?.id;
                      if (first) setDraftModel(first);
                      setModelOpen(false);
                    }}
                  >
                    {eng.label}
                  </button>
                ))}
              </div>
            )}
          </div>

          {/* Model */}
          <div style={{ position: 'relative' }}>
            <div style={{ fontSize: 10, fontWeight: 600, color: mutedColor, marginBottom: 6, letterSpacing: 0.3 }}>
              MODEL
            </div>
            <button
              type="button"
              disabled={!models.length}
              onClick={() => setModelOpen((v) => !v)}
              style={{
                width: '100%',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                gap: 8,
                padding: '7px 10px',
                fontSize: 12,
                textAlign: 'left',
                background: darkMode ? '#0d1117' : '#f6f8fa',
                border: `1px solid ${borderColor}`,
                borderRadius: 6,
                cursor: models.length ? 'pointer' : 'not-allowed',
                color: textColor,
                opacity: models.length ? 1 : 0.5,
              }}
            >
              <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                {draftModel || '—'}
                {modelLabel && modelLabel !== draftModel ? (
                  <span style={{ color: mutedColor, marginLeft: 6, fontSize: 11 }}>
                    {modelLabel}
                  </span>
                ) : null}
              </span>
              <svg width="10" height="10" viewBox="0 0 12 12" aria-hidden="true" style={{ flexShrink: 0, transform: modelOpen ? 'rotate(180deg)' : 'none' }}>
                <path d="M2.5 4.5 L6 8 L9.5 4.5" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            </button>
            {modelOpen && models.length > 0 && (
              <div
                style={{
                  position: 'absolute',
                  top: 'calc(100% + 4px)',
                  left: 0,
                  right: 0,
                  zIndex: 70,
                  background: menuBg,
                  border: `1px solid ${borderColor}`,
                  borderRadius: 6,
                  boxShadow: darkMode
                    ? '0 8px 20px rgba(0,0,0,0.4)'
                    : '0 8px 20px rgba(31,35,40,0.14)',
                  padding: 4,
                  maxHeight: 180,
                  overflowY: 'auto',
                }}
              >
                {models.map((m) => {
                  const active = m.id === draftModel;
                  return (
                    <button
                      key={m.id}
                      type="button"
                      onClick={() => {
                        setDraftModel(m.id);
                        setModelOpen(false);
                      }}
                      style={{
                        width: '100%',
                        display: 'block',
                        textAlign: 'left',
                        padding: '7px 8px',
                        border: 'none',
                        borderRadius: 4,
                        cursor: 'pointer',
                        background: active ? menuHover : 'none',
                        color: textColor,
                        fontSize: 12,
                      }}
                      onMouseEnter={(e) => { e.currentTarget.style.background = menuHover; }}
                      onMouseLeave={(e) => {
                        if (!active) e.currentTarget.style.background = 'none';
                      }}
                    >
                      <div style={{ fontWeight: active ? 600 : 500 }}>{m.id}</div>
                      {m.label && m.label !== m.id && (
                        <div style={{ fontSize: 10, color: mutedColor, marginTop: 2 }}>{m.label}</div>
                      )}
                    </button>
                  );
                })}
              </div>
            )}
          </div>

          <div style={{ fontSize: 10, color: mutedColor, lineHeight: 1.4 }}>
            {live
              ? 'Save applies on the next loop — the active run keeps its current engine/model.'
              : 'Save applies on the next loop (resume / extend / start).'}
            {settings?.pendingNextLoop && settings.activeEngine ? (
              <span style={{ display: 'block', marginTop: 4, color: accent }}>
                Active now: {settings.activeEngine}
                {settings.activeModel ? ` · ${settings.activeModel}` : ''}
              </span>
            ) : null}
          </div>

          {flash && (
            <div
              style={{
                fontSize: 11,
                color: flash.ok
                  ? (darkMode ? '#3fb950' : '#1a7f37')
                  : (darkMode ? '#f85149' : '#cf222e'),
                lineHeight: 1.35,
              }}
            >
              {flash.text}
            </div>
          )}

          <button
            type="button"
            disabled={saving || !engines.length}
            onClick={() => void onSave()}
            style={{
              padding: '7px 12px',
              fontSize: 12,
              fontWeight: 600,
              borderRadius: 6,
              border: 'none',
              cursor: saving || !engines.length ? 'not-allowed' : 'pointer',
              opacity: saving || !engines.length ? 0.55 : 1,
              background: darkMode ? '#238636' : '#1a7f37',
              color: '#ffffff',
            }}
          >
            {saving ? 'Saving…' : 'Save'}
          </button>
        </div>
      )}
    </div>
  );
}

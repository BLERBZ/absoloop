import { useCallback, useEffect, useRef, useState } from 'react';

export const VIEWPORT_INSET = 16;
export const MIN_WIDTH = 760;
export const MIN_HEIGHT = 420;
/** Distance at which dock / size-preset magnetism engages. */
export const SNAP_ZONE = 24;

export type DockId =
  | 'top-left'
  | 'top-right'
  | 'bottom-left'
  | 'bottom-right'
  | 'left-center'
  | 'right-center';

const DOCKS: DockId[] = [
  'top-left', 'top-right', 'bottom-left', 'bottom-right',
  'left-center', 'right-center',
];

export type ResizeDir = 'n' | 's' | 'e' | 'w' | 'ne' | 'nw' | 'se' | 'sw';

export interface WindowRect {
  x: number;
  y: number;
  w: number;
  h: number;
}

const STORAGE_KEY = 'zc-compact-window';
/** Inner size of the compact monitor when it owns a real OS window. */
const WINDOWED_SIZE_KEY = 'zc-compact-oswin';

interface StoredWindow {
  dock: DockId | null;
  x: number;
  y: number;
  w: number;
  h: number;
}

function viewport(): { vw: number; vh: number } {
  return { vw: window.innerWidth, vh: window.innerHeight };
}

/** Usable screen area (for OS-window mode). availLeft/Top are de-facto standard. */
function screenArea(): { sx: number; sy: number; sw: number; sh: number } {
  const s = window.screen as Screen & { availLeft?: number; availTop?: number };
  return {
    sx: s.availLeft ?? 0,
    sy: s.availTop ?? 0,
    sw: s.availWidth || window.innerWidth,
    sh: s.availHeight || window.innerHeight,
  };
}

function clampSize(w: number, h: number, vw: number, vh: number): { w: number; h: number } {
  const maxW = vw - VIEWPORT_INSET * 2;
  const maxH = vh - VIEWPORT_INSET * 2;
  return {
    w: Math.round(Math.min(Math.max(w, Math.min(MIN_WIDTH, maxW)), maxW)),
    h: Math.round(Math.min(Math.max(h, Math.min(MIN_HEIGHT, maxH)), maxH)),
  };
}

function positionForDock(dock: DockId, w: number, h: number, vw: number, vh: number): { x: number; y: number } {
  const left = VIEWPORT_INSET;
  const right = vw - w - VIEWPORT_INSET;
  const top = VIEWPORT_INSET;
  const bottom = vh - h - VIEWPORT_INSET;
  const centerY = Math.round((vh - h) / 2);
  switch (dock) {
    case 'top-left': return { x: left, y: top };
    case 'top-right': return { x: right, y: top };
    case 'bottom-left': return { x: left, y: bottom };
    case 'bottom-right': return { x: right, y: bottom };
    case 'left-center': return { x: left, y: centerY };
    case 'right-center': return { x: right, y: centerY };
  }
}

function clampPosition(x: number, y: number, w: number, h: number, vw: number, vh: number): { x: number; y: number } {
  return {
    x: Math.round(Math.min(Math.max(x, 0), Math.max(0, vw - w))),
    y: Math.round(Math.min(Math.max(y, 0), Math.max(0, vh - h))),
  };
}

/** Size presets: compact 50×50, wide 66×50, tall 50×72 (of viewport). */
function sizePresets(vw: number, vh: number): { w: number; h: number }[] {
  return [
    { w: vw * 0.5, h: vh * 0.5 },
    { w: vw * 0.66, h: vh * 0.5 },
    { w: vw * 0.5, h: vh * 0.72 },
  ].map(p => clampSize(p.w, p.h, vw, vh));
}

function loadStored(): StoredWindow | null {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    if (typeof parsed !== 'object' || parsed == null) return null;
    const dock = DOCKS.includes(parsed.dock) ? parsed.dock as DockId : null;
    const num = (v: unknown) => (typeof v === 'number' && Number.isFinite(v) ? v : NaN);
    const w = num(parsed.w);
    const h = num(parsed.h);
    if (Number.isNaN(w) || Number.isNaN(h)) return null;
    return { dock, x: num(parsed.x) || 0, y: num(parsed.y) || 0, w, h };
  } catch {
    return null;
  }
}

function saveStored(rect: WindowRect, dock: DockId | null) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify({ dock, ...rect }));
  } catch {
    /* ignore */
  }
}

function saveWindowedSize(w: number, h: number) {
  try {
    localStorage.setItem(WINDOWED_SIZE_KEY, JSON.stringify({ w: Math.round(w), h: Math.round(h) }));
  } catch {
    /* ignore */
  }
}

/**
 * Preferred inner size for a dedicated compact OS window — last windowed
 * size, falling back to the stored in-page panel size, then defaults.
 */
export function getStoredCompactSize(): { w: number; h: number } {
  try {
    const raw = localStorage.getItem(WINDOWED_SIZE_KEY);
    if (raw) {
      const parsed = JSON.parse(raw);
      if (Number.isFinite(parsed?.w) && Number.isFinite(parsed?.h)) {
        return { w: Math.max(MIN_WIDTH, parsed.w), h: Math.max(MIN_HEIGHT, parsed.h) };
      }
    }
  } catch {
    /* ignore */
  }
  const stored = loadStored();
  if (stored) return { w: Math.max(MIN_WIDTH, stored.w), h: Math.max(MIN_HEIGHT, stored.h) };
  return { w: 960, h: 560 };
}

function initialWindow(): { rect: WindowRect; dock: DockId | null } {
  const { vw, vh } = viewport();
  const stored = loadStored();
  if (stored) {
    const { w, h } = clampSize(stored.w, stored.h, vw, vh);
    if (stored.dock) {
      return { rect: { ...positionForDock(stored.dock, w, h, vw, vh), w, h }, dock: stored.dock };
    }
    return { rect: { ...clampPosition(stored.x, stored.y, w, h, vw, vh), w, h }, dock: null };
  }
  const { w, h } = clampSize(vw * 0.5, vh * 0.5, vw, vh);
  return { rect: { ...positionForDock('top-right', w, h, vw, vh), w, h }, dock: 'top-right' };
}

export interface FloatingWindow {
  rect: WindowRect;
  dock: DockId | null;
  dragging: boolean;
  resizing: boolean;
  /** Ghost frame shown while the drag is inside a snap zone. */
  snapPreview: WindowRect | null;
  startDrag: (e: React.PointerEvent) => void;
  startResize: (dir: ResizeDir) => (e: React.PointerEvent) => void;
  dockTo: (dock: DockId) => void;
  /** Keyboard resize — grows/shrinks from the anchored corner. */
  nudgeResize: (dw: number, dh: number) => void;
}

/**
 * Geometry controller for the compact monitor.
 *
 * - Default (in-page) mode: the panel floats inside the viewport with dock
 *   snapping and magnetic size presets.
 * - `windowed` mode: the panel fills a dedicated OS window (opened via
 *   window.open, so the browser permits scripted move/resize) and the same
 *   drag/resize gestures drive window.moveTo / window.resizeTo instead.
 */
export function useFloatingWindow(active: boolean, windowed = false): FloatingWindow {
  const [{ rect, dock }, setWin] = useState(() => (windowed
    ? { rect: { x: 0, y: 0, w: window.innerWidth, h: window.innerHeight }, dock: null }
    : initialWindow()));
  const [dragging, setDragging] = useState(false);
  const [resizing, setResizing] = useState(false);
  const [snapPreview, setSnapPreview] = useState<WindowRect | null>(null);
  const gesture = useRef<{
    kind: 'drag' | 'resize';
    dir?: ResizeDir;
    pointerId: number;
    startX: number;
    startY: number;
    startRect: WindowRect;
    /** Dock candidate while dragging (committed on release). */
    candidate: DockId | null;
    /** OS-window mode anchors (screen coordinates). */
    winStartX: number;
    winStartY: number;
    chromeW: number;
    chromeH: number;
  } | null>(null);

  // Track geometry after browser/OS window resize so the panel stays correct.
  useEffect(() => {
    if (!active) return;
    const onResize = () => {
      const { vw, vh } = viewport();
      if (windowed) {
        setWin({ rect: { x: 0, y: 0, w: vw, h: vh }, dock: null });
        saveWindowedSize(vw, vh);
        return;
      }
      setWin(prev => {
        const { w, h } = clampSize(prev.rect.w, prev.rect.h, vw, vh);
        const pos = prev.dock
          ? positionForDock(prev.dock, w, h, vw, vh)
          : clampPosition(prev.rect.x, prev.rect.y, w, h, vw, vh);
        const next = { rect: { ...pos, w, h }, dock: prev.dock };
        saveStored(next.rect, next.dock);
        return next;
      });
    };
    window.addEventListener('resize', onResize);
    return () => window.removeEventListener('resize', onResize);
  }, [active, windowed]);

  const endGesture = useCallback(() => {
    const g = gesture.current;
    gesture.current = null;
    setDragging(false);
    setResizing(false);
    setSnapPreview(null);
    document.body.style.removeProperty('cursor');
    document.body.style.removeProperty('user-select');
    if (!g) return;
    if (windowed) {
      saveWindowedSize(window.innerWidth, window.innerHeight);
      return;
    }
    const { vw, vh } = viewport();
    setWin(prev => {
      let next = prev;
      if (g.kind === 'drag') {
        if (g.candidate) {
          const pos = positionForDock(g.candidate, prev.rect.w, prev.rect.h, vw, vh);
          next = { rect: { ...prev.rect, ...pos }, dock: g.candidate };
        } else {
          next = { ...prev, dock: null };
        }
      } else if (prev.dock) {
        // Keep the window anchored to its dock after a resize.
        const pos = positionForDock(prev.dock, prev.rect.w, prev.rect.h, vw, vh);
        next = { rect: { ...prev.rect, ...pos }, dock: prev.dock };
      }
      saveStored(next.rect, next.dock);
      return next;
    });
  }, [windowed]);

  useEffect(() => {
    if (!dragging && !resizing) return;
    const onMove = (e: PointerEvent) => {
      const g = gesture.current;
      if (!g || e.pointerId !== g.pointerId) return;

      if (windowed) {
        // Gestures move/resize the real OS window (screen coordinates).
        const dx = e.screenX - g.startX;
        const dy = e.screenY - g.startY;
        if (g.kind === 'drag') {
          window.moveTo(g.winStartX + dx, g.winStartY + dy);
          return;
        }
        const dir = g.dir!;
        const { sw, sh } = screenArea();
        let w = g.startRect.w;
        let h = g.startRect.h;
        if (dir.includes('e')) w = g.startRect.w + dx;
        if (dir.includes('s')) h = g.startRect.h + dy;
        if (dir.includes('w')) w = g.startRect.w - dx;
        if (dir.includes('n')) h = g.startRect.h - dy;
        w = Math.round(Math.min(Math.max(w, MIN_WIDTH), sw));
        h = Math.round(Math.min(Math.max(h, MIN_HEIGHT), sh));
        window.resizeTo(w + g.chromeW, h + g.chromeH);
        // Keep the opposite edge fixed for w/n handles.
        if (dir.includes('w') || dir.includes('n')) {
          const x = dir.includes('w') ? g.winStartX + (g.startRect.w - w) : g.winStartX;
          const y = dir.includes('n') ? g.winStartY + (g.startRect.h - h) : g.winStartY;
          window.moveTo(x, y);
        }
        return;
      }

      const { vw, vh } = viewport();
      const dx = e.clientX - g.startX;
      const dy = e.clientY - g.startY;

      if (g.kind === 'drag') {
        const { w, h } = g.startRect;
        const pos = clampPosition(g.startRect.x + dx, g.startRect.y + dy, w, h, vw, vh);
        let candidate: DockId | null = null;
        for (const d of DOCKS) {
          const t = positionForDock(d, w, h, vw, vh);
          if (Math.abs(pos.x - t.x) <= SNAP_ZONE && Math.abs(pos.y - t.y) <= SNAP_ZONE) {
            candidate = d;
            setSnapPreview({ ...t, w, h });
            break;
          }
        }
        if (!candidate) setSnapPreview(null);
        g.candidate = candidate;
        setWin(prev => ({ ...prev, rect: { ...pos, w, h } }));
        return;
      }

      // Resize
      const dir = g.dir!;
      const s = g.startRect;
      let x = s.x;
      let y = s.y;
      let w = s.w;
      let h = s.h;
      if (dir.includes('e')) w = s.w + dx;
      if (dir.includes('s')) h = s.h + dy;
      if (dir.includes('w')) { w = s.w - dx; x = s.x + dx; }
      if (dir.includes('n')) { h = s.h - dy; y = s.y + dy; }

      const clamped = clampSize(w, h, vw, vh);
      // Magnetic size presets — snap when both dimensions are close.
      for (const p of sizePresets(vw, vh)) {
        if (Math.abs(clamped.w - p.w) <= SNAP_ZONE && Math.abs(clamped.h - p.h) <= SNAP_ZONE) {
          clamped.w = p.w;
          clamped.h = p.h;
          break;
        }
      }
      // Keep the opposite edge fixed for w/n handles after clamping.
      if (dir.includes('w')) x = s.x + s.w - clamped.w;
      if (dir.includes('n')) y = s.y + s.h - clamped.h;
      const pos = clampPosition(x, y, clamped.w, clamped.h, vw, vh);
      setWin(prev => ({ ...prev, rect: { ...pos, ...clamped } }));
    };
    const onUp = (e: PointerEvent) => {
      const g = gesture.current;
      if (!g || e.pointerId !== g.pointerId) return;
      endGesture();
    };
    window.addEventListener('pointermove', onMove);
    window.addEventListener('pointerup', onUp);
    window.addEventListener('pointercancel', onUp);
    return () => {
      window.removeEventListener('pointermove', onMove);
      window.removeEventListener('pointerup', onUp);
      window.removeEventListener('pointercancel', onUp);
    };
  }, [dragging, resizing, endGesture, windowed]);

  const beginGesture = useCallback((e: React.PointerEvent) => {
    // Keep receiving pointer events even when the pointer leaves the window
    // (essential when the gesture drags the OS window itself).
    try {
      (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
    } catch {
      /* unsupported pointer types — window listeners still cover most cases */
    }
  }, []);

  const startDrag = useCallback((e: React.PointerEvent) => {
    if (e.button !== 0) return;
    // Don't steal pointer interactions from buttons/inputs inside the handle.
    const el = e.target as HTMLElement;
    if (el.closest('button, a, input, select, textarea, [role="menu"]')) return;
    e.preventDefault();
    beginGesture(e);
    gesture.current = {
      kind: 'drag',
      pointerId: e.pointerId,
      startX: windowed ? e.screenX : e.clientX,
      startY: windowed ? e.screenY : e.clientY,
      startRect: windowed
        ? { x: 0, y: 0, w: window.innerWidth, h: window.innerHeight }
        : rect,
      candidate: null,
      winStartX: window.screenX,
      winStartY: window.screenY,
      chromeW: Math.max(0, window.outerWidth - window.innerWidth),
      chromeH: Math.max(0, window.outerHeight - window.innerHeight),
    };
    setDragging(true);
    document.body.style.cursor = 'grabbing';
    document.body.style.userSelect = 'none';
  }, [rect, windowed, beginGesture]);

  const startResize = useCallback((dir: ResizeDir) => (e: React.PointerEvent) => {
    if (e.button !== 0) return;
    e.preventDefault();
    e.stopPropagation();
    beginGesture(e);
    gesture.current = {
      kind: 'resize',
      dir,
      pointerId: e.pointerId,
      startX: windowed ? e.screenX : e.clientX,
      startY: windowed ? e.screenY : e.clientY,
      startRect: windowed
        ? { x: 0, y: 0, w: window.innerWidth, h: window.innerHeight }
        : rect,
      candidate: null,
      winStartX: window.screenX,
      winStartY: window.screenY,
      chromeW: Math.max(0, window.outerWidth - window.innerWidth),
      chromeH: Math.max(0, window.outerHeight - window.innerHeight),
    };
    setResizing(true);
    const cursors: Record<ResizeDir, string> = {
      n: 'ns-resize', s: 'ns-resize', e: 'ew-resize', w: 'ew-resize',
      ne: 'nesw-resize', sw: 'nesw-resize', nw: 'nwse-resize', se: 'nwse-resize',
    };
    document.body.style.cursor = cursors[dir];
    document.body.style.userSelect = 'none';
  }, [rect, windowed, beginGesture]);

  const dockTo = useCallback((target: DockId) => {
    if (windowed) {
      // Move the OS window to the matching screen corner/edge.
      const { sx, sy, sw, sh } = screenArea();
      const pos = positionForDock(
        target,
        window.outerWidth,
        window.outerHeight,
        sw,
        sh,
      );
      window.moveTo(sx + pos.x, sy + pos.y);
      return;
    }
    const { vw, vh } = viewport();
    setWin(prev => {
      const pos = positionForDock(target, prev.rect.w, prev.rect.h, vw, vh);
      const next = { rect: { ...prev.rect, ...pos }, dock: target };
      saveStored(next.rect, next.dock);
      return next;
    });
  }, [windowed]);

  const nudgeResize = useCallback((dw: number, dh: number) => {
    if (windowed) {
      const { sw, sh } = screenArea();
      const chromeW = Math.max(0, window.outerWidth - window.innerWidth);
      const chromeH = Math.max(0, window.outerHeight - window.innerHeight);
      const w = Math.round(Math.min(Math.max(window.innerWidth + dw, MIN_WIDTH), sw));
      const h = Math.round(Math.min(Math.max(window.innerHeight + dh, MIN_HEIGHT), sh));
      window.resizeTo(w + chromeW, h + chromeH);
      saveWindowedSize(w, h);
      return;
    }
    const { vw, vh } = viewport();
    setWin(prev => {
      const size = clampSize(prev.rect.w + dw, prev.rect.h + dh, vw, vh);
      const pos = prev.dock
        ? positionForDock(prev.dock, size.w, size.h, vw, vh)
        : clampPosition(prev.rect.x, prev.rect.y, size.w, size.h, vw, vh);
      const next = { rect: { ...pos, ...size }, dock: prev.dock };
      saveStored(next.rect, next.dock);
      return next;
    });
  }, [windowed]);

  return {
    rect,
    dock,
    dragging,
    resizing,
    snapPreview,
    startDrag,
    startResize,
    dockTo,
    nudgeResize,
  };
}

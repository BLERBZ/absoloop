import type { Task, Metrics } from '../hooks/usePolling';

const phaseNames: Record<number, string> = {
  0: 'Infrastructure',
  1: 'Research',
  2: 'Team Design',
  3: 'Planning',
  4: 'Implementation',
  5: 'QA & Testing',
  6: 'Validation'
};

const phaseColors: Record<string, string> = {
  complete: '#238636',
  active: '#1f6feb',
  pending: '#30363d'
};

export function GanttChart({ tasks, metrics, darkMode }: {
  tasks: Task[];
  metrics?: Metrics;
  darkMode: boolean;
}) {
  const mutedColor = darkMode ? '#7d8590' : '#656d76';
  const barBg = darkMode ? '#21262d' : '#e1e4e8';
  const borderColor = darkMode ? '#30363d' : '#d0d7de';

  // Group tasks by phase
  const phaseMap = new Map<number, Task[]>();
  tasks.forEach(t => {
    const list = phaseMap.get(t.phase) || [];
    list.push(t);
    phaseMap.set(t.phase, list);
  });

  const phases = Array.from(phaseMap.entries()).sort((a, b) => a[0] - b[0]);

  if (phases.length === 0) {
    return null;
  }

  return (
    <div>
      <h3 style={{
        margin: '0 0 14px',
        fontSize: 13,
        fontWeight: 700,
        textTransform: 'uppercase',
        color: mutedColor,
        letterSpacing: 1.5
      }}>
        Phase Timeline
      </h3>
      <div style={{
        background: darkMode ? '#0d1117' : '#f6f8fa',
        borderRadius: 8,
        padding: 14,
        marginBottom: 16
      }}>
        {phases.map(([phase, pTasks], idx) => {
          const done = pTasks.filter(t => t.status === 'done').length;
          const total = pTasks.length;
          const pct = total > 0 ? Math.round((done / total) * 100) : 0;
          const hasActive = pTasks.some(t => t.status === 'in_progress');
          const allDone = pct === 100;
          const status = allDone ? 'complete' : hasActive ? 'active' : 'pending';

          return (
            <div key={phase} style={{
              display: 'flex',
              alignItems: 'center',
              gap: 12,
              padding: '8px 0',
              borderBottom: idx < phases.length - 1 ? `1px solid ${borderColor}` : 'none'
            }}>
              {/* Phase label */}
              <span style={{
                fontSize: 11,
                fontWeight: 600,
                width: 130,
                flexShrink: 0,
                color: allDone ? '#3fb950' : hasActive ? '#58a6ff' : mutedColor,
                display: 'flex',
                alignItems: 'center',
                gap: 6
              }}>
                <span style={{
                  width: 6,
                  height: 6,
                  borderRadius: '50%',
                  background: phaseColors[status],
                  flexShrink: 0
                }} />
                P{phase}: {phaseNames[phase] || `Phase ${phase}`}
              </span>

              {/* Progress bar */}
              <div style={{
                flex: 1,
                height: 14,
                background: barBg,
                borderRadius: 7,
                overflow: 'hidden',
                position: 'relative'
              }}>
                <div style={{
                  width: `${pct}%`,
                  height: '100%',
                  background: allDone ? '#238636' : hasActive ? '#1f6feb' : '#30363d',
                  borderRadius: 7,
                  transition: 'width 0.5s ease'
                }} />
                {hasActive && !allDone && (
                  <div style={{
                    position: 'absolute',
                    right: 0,
                    top: 0,
                    width: `${100 - pct}%`,
                    height: '100%',
                    background: `repeating-linear-gradient(90deg, transparent, transparent 4px, ${darkMode ? '#1f6feb15' : '#1f6feb10'} 4px, ${darkMode ? '#1f6feb15' : '#1f6feb10'} 8px)`
                  }} />
                )}
              </div>

              {/* Count */}
              <span style={{
                fontSize: 11,
                color: allDone ? '#3fb950' : mutedColor,
                width: 50,
                textAlign: 'right',
                fontWeight: allDone ? 600 : 400,
                fontVariantNumeric: 'tabular-nums'
              }}>
                {done}/{total}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

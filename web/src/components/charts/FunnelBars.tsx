export interface FunnelStage {
  stage: string;
  count: number;
}

/**
 * Pipeline stages as horizontal bars (one series: the stage name is the category axis).
 * Value at the bar tip in text ink; bars 4px-rounded at the data end, square at the baseline.
 */
export function FunnelBars({ stages, label }: { stages: FunnelStage[]; label: string }) {
  const max = Math.max(1, ...stages.map((s) => s.count));
  return (
    <figure className="m-0">
      <figcaption className="sr-only">{label}</figcaption>
      <ul className="flex flex-col gap-2.5">
        {stages.map((s) => (
          <li key={s.stage} className="grid grid-cols-[96px_1fr] items-center gap-3 text-sm" title={`${s.stage}: ${s.count}`}>
            <span className="truncate text-muted">{s.stage}</span>
            <span className="flex items-center gap-2">
              <span
                className="h-4 rounded-r-[4px] bg-viz-1"
                style={{ width: `${(s.count / max) * 100}%`, minWidth: s.count > 0 ? 3 : 0 }}
                aria-hidden
              />
              <span className="font-semibold text-fg" style={{ fontVariantNumeric: "tabular-nums" }}>
                {s.count.toLocaleString()}
              </span>
            </span>
          </li>
        ))}
      </ul>
    </figure>
  );
}

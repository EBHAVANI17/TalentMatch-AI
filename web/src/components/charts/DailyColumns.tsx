import { useEffect, useId, useMemo, useRef, useState } from "react";

export interface DayValue {
  date: string; // YYYY-MM-DD
  count: number;
}

const HEIGHT = 180;
const PAD = { top: 12, right: 8, bottom: 24, left: 32 };

function niceMax(value: number) {
  if (value <= 4) return 4;
  const magnitude = 10 ** Math.floor(Math.log10(value));
  const step = [1, 2, 2.5, 5, 10].map((m) => m * magnitude).find((s) => s * 4 >= value) ?? magnitude * 10;
  return step * 4;
}

const shortDate = (iso: string) =>
  new Date(`${iso}T00:00:00`).toLocaleDateString(undefined, { month: "short", day: "numeric" });

/**
 * Single-series daily column chart (dataviz mark spec: thin columns with a 4px rounded
 * top, square baseline, hairline grid, hover/focus tooltip, table view for screen readers).
 */
export function DailyColumns({ data, label }: { data: DayValue[]; label: string }) {
  const [active, setActive] = useState<number | null>(null);
  const [width, setWidth] = useState(640);
  const titleId = useId();
  const containerRef = useRef<HTMLDivElement>(null);

  // Draw at the real pixel width so text and 2px gaps aren't scaled.
  useEffect(() => {
    const el = containerRef.current;
    if (!el || typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(([entry]) => setWidth(Math.max(240, Math.round(entry.contentRect.width))));
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  const max = useMemo(() => niceMax(Math.max(0, ...data.map((d) => d.count))), [data]);
  const ticks = [0, max / 4, max / 2, (3 * max) / 4, max];
  const plotW = width - PAD.left - PAD.right;
  const plotH = HEIGHT - PAD.top - PAD.bottom;
  const band = plotW / Math.max(data.length, 1);
  const barW = Math.max(2, Math.min(24, band - 2)); // 2px surface gap between neighbours
  const y = (v: number) => PAD.top + plotH - (v / max) * plotH;
  const labelEvery = Math.ceil(data.length / 6);
  const hovered = active !== null ? data[active] : null;

  return (
    <figure className="m-0" aria-labelledby={titleId}>
      <figcaption id={titleId} className="sr-only">
        {label}
      </figcaption>
      <div className="relative" ref={containerRef}>
        <svg width="100%" height={HEIGHT} viewBox={`0 0 ${width} ${HEIGHT}`} role="img" aria-hidden className="block">
          {ticks.map((t) => (
            <g key={t}>
              <line x1={PAD.left} x2={width - PAD.right} y1={y(t)} y2={y(t)} stroke={t === 0 ? "var(--tm-viz-axis)" : "var(--tm-viz-grid)"} strokeWidth={1} />
              <text x={PAD.left - 6} y={y(t)} dy="0.32em" textAnchor="end" className="fill-muted text-[10px]" style={{ fontVariantNumeric: "tabular-nums" }}>
                {Number.isInteger(t) ? t.toLocaleString() : t.toFixed(1)}
              </text>
            </g>
          ))}
          {data.map((d, i) => {
            const x = PAD.left + i * band + (band - barW) / 2;
            const h = Math.max(0, y(0) - y(d.count));
            const r = Math.min(4, barW / 2, h);
            return (
              <g key={d.date}>
                {h > 0 && (
                  <path
                    d={`M${x},${y(0)} V${y(0) - h + r} Q${x},${y(0) - h} ${x + r},${y(0) - h} H${x + barW - r} Q${x + barW},${y(0) - h} ${x + barW},${y(0) - h + r} V${y(0)} Z`}
                    fill="var(--tm-viz-1)"
                    opacity={active === null || active === i ? 1 : 0.55}
                  />
                )}
                {i % labelEvery === 0 && (
                  <text x={x + barW / 2} y={HEIGHT - 6} textAnchor="middle" className="fill-muted text-[10px]">
                    {shortDate(d.date)}
                  </text>
                )}
              </g>
            );
          })}
        </svg>
        {/* Hit targets: the full column band, larger than the painted bar */}
        <div className="absolute inset-0 flex" style={{ left: PAD.left, right: PAD.right, top: PAD.top, bottom: PAD.bottom }}>
          {data.map((d, i) => (
            <button
              key={d.date}
              type="button"
              className="h-full flex-1 cursor-default focus:outline-none"
              aria-label={`${shortDate(d.date)}: ${d.count}`}
              onPointerEnter={() => setActive(i)}
              onPointerLeave={() => setActive(null)}
              onFocus={() => setActive(i)}
              onBlur={() => setActive(null)}
            />
          ))}
        </div>
        {hovered && active !== null && (
          <div
            role="status"
            className="pointer-events-none absolute -translate-x-1/2 rounded-md border border-border bg-surface px-2.5 py-1.5 text-xs shadow-card"
            style={{ left: PAD.left + active * band + band / 2, top: Math.max(0, y(hovered.count) - 44) }}
          >
            <span className="block font-semibold text-fg">{hovered.count.toLocaleString()}</span>
            <span className="block text-muted">{shortDate(hovered.date)}</span>
          </div>
        )}
      </div>
      <table className="sr-only">
        <caption>{label}</caption>
        <thead>
          <tr>
            <th scope="col">Date</th>
            <th scope="col">Count</th>
          </tr>
        </thead>
        <tbody>
          {data.map((d) => (
            <tr key={d.date}>
              <td>{d.date}</td>
              <td>{d.count}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </figure>
  );
}

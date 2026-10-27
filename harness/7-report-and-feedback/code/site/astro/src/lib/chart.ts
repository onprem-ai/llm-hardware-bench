// Build-time SVG line charts with repetition-range bands.
//
// Geometry, scales and palette are a direct port of the client-side chart()
// that previously drew these in the browser, so output stays visually
// comparable to earlier reports. Differences, all deliberate:
//   - emitted as markup at build time, so charts need no JavaScript
//   - <title>/<desc> on the chart, and <title> per point, giving native hover
//     text and something for crawlers and screen readers to read
//   - the "unavailable" placeholder is a <figure>-level concern here too, so
//     an absent metric still renders an honest box rather than an empty axis

import { esc, f, type ChartSeries } from './report';

const W = 600;
const H = 315;
const M = { l: 78, r: 16, t: 38, b: 40 };

export type { ChartSeries };

export interface ChartOptions {
  /** Y-axis caption, rendered rotated at the left edge. */
  y?: string;
  /** Log-scale the Y axis (used for TTFT, which spans orders of magnitude). */
  log?: boolean;
  /** Lower clamp for log scales. */
  min?: number;
  /** Start the axis near the data instead of at zero. */
  nozero?: boolean;
  /** Horizontal reference line, e.g. a theoretical ceiling. */
  ref?: number | null;
  refLabel?: string;
  /** Vertical marker for the configured active-sequence ceiling. */
  ceiling?: number | null;
  /** Y tick formatter. */
  tick?: (value: number) => string;
  /** Accessible description; falls back to the caption. */
  desc?: string;
}

const attrs = (map: Record<string, string | number>): string =>
  Object.entries(map)
    .map(([k, v]) => `${k}="${esc(v)}"`)
    .join(' ');

const el = (name: string, map: Record<string, string | number>, text?: string): string =>
  text === undefined
    ? `<${name} ${attrs(map)}/>`
    : `<${name} ${attrs(map)}>${esc(text)}</${name}>`;

function placeholder(caption: string): string {
  return (
    `<svg viewBox="0 0 ${W} ${H}" class="chart" role="img" aria-label="${esc(caption)}: unavailable">` +
    `<title>${esc(caption)}: unavailable</title>` +
    `<desc>This metric was not collected for this campaign.</desc>` +
    el('rect', { x: 0, y: 0, width: W, height: H, fill: '#f5f7f6' }) +
    el('text', { x: W / 2, y: H / 2 - 5, 'text-anchor': 'middle', fill: '#52616a', 'font-size': 15, 'font-weight': 700 }, 'Unavailable') +
    el('text', { x: W / 2, y: H / 2 + 20, 'text-anchor': 'middle', fill: '#65747d', 'font-size': 11 }, 'Metric was not collected for this campaign') +
    `</svg>`
  );
}

export function renderChart(
  series: ChartSeries[],
  axis: { ticks: number[]; max: number },
  options: ChartOptions = {},
): string {
  const caption = options.y ?? 'Measurement';
  const values = series
    .flatMap((s) => s.data.flatMap((d) => [d.v, d.min, d.max]))
    .filter((v): v is number => v !== null && Number.isFinite(v));

  if (!values.length) return placeholder(caption);

  const log = !!options.log;
  let lo = log
    ? Math.log10(Math.max(0.001, options.min ?? Math.min(...values)))
    : options.nozero
      ? Math.min(...values) * 0.96
      : 0;
  let hi = log ? Math.log10(Math.max(...values) * 1.18) : Math.max(...values) * 1.12;
  if (options.ref != null) hi = Math.max(hi, options.ref * 1.08);
  if (lo === hi) hi += 1;

  const x = (c: number) => M.l + ((c - 1) * (W - M.l - M.r)) / Math.max(1, axis.max - 1);
  const y = (v: number) =>
    M.t + ((hi - (log ? Math.log10(Math.max(0.001, v)) : v)) * (H - M.t - M.b)) / (hi - lo);

  const parts: string[] = [];

  // Horizontal gridlines with value labels.
  for (let i = 0; i < 5; i++) {
    const q = lo + ((hi - lo) * i) / 4;
    const v = log ? 10 ** q : q;
    const yy = y(v);
    parts.push(el('line', { x1: M.l, y1: yy, x2: W - M.r, y2: yy, stroke: '#e9eeeb' }));
    parts.push(
      el(
        'text',
        { x: M.l - 7, y: yy + 4, 'text-anchor': 'end', fill: '#45535b', 'font-size': 10, 'font-weight': 700 },
        options.tick ? options.tick(v) : f(v, v < 10 ? 1 : 0),
      ),
    );
  }

  // Theoretical / configured reference line.
  if (options.ref != null) {
    const ry = y(options.ref);
    parts.push(
      el('line', { x1: M.l, y1: ry, x2: W - M.r, y2: ry, stroke: '#aa4050', 'stroke-width': 1.5, 'stroke-dasharray': '6 4' }),
    );
    parts.push(
      el('text', { x: W - M.r, y: ry - 5, 'text-anchor': 'end', fill: '#aa4050', 'font-size': 9 }, options.refLabel ?? String(options.ref)),
    );
  }

  // Active-sequence ceiling marker.
  if (options.ceiling != null && options.ceiling <= axis.max) {
    const cx = x(options.ceiling);
    parts.push(
      el('line', { x1: cx, y1: M.t, x2: cx, y2: H - M.b, stroke: '#7557a5', 'stroke-dasharray': '4 4' }),
    );
    parts.push(
      el(
        'text',
        { x: cx - 3, y: M.t + 12, 'text-anchor': 'end', fill: '#7557a5', 'font-size': 8 },
        `${options.ceiling} ACTIVE-SEQUENCE CEILING`,
      ),
    );
  }

  // X axis.
  for (const c of axis.ticks) {
    parts.push(el('text', { x: x(c), y: H - 14, 'text-anchor': 'middle', fill: '#65747d', 'font-size': 10 }, String(c)));
  }
  parts.push(
    el('text', { x: (M.l + W - M.r) / 2, y: H - 1, 'text-anchor': 'middle', fill: '#65747d', 'font-size': 9 }, 'GLOBAL CONCURRENCY'),
  );
  if (options.y) {
    const mid = (M.t + H - M.b) / 2;
    parts.push(
      el(
        'text',
        { x: 14, y: mid, transform: `rotate(-90 14 ${mid})`, 'text-anchor': 'middle', fill: '#17242c', 'font-size': 11, 'font-weight': 700 },
        options.y,
      ),
    );
  }

  // Legend.
  let offset = 0;
  for (const s of series) {
    parts.push(el('line', { x1: M.l + offset, y1: 15, x2: M.l + offset + 17, y2: 15, stroke: s.color, 'stroke-width': 3 }));
    parts.push(el('text', { x: M.l + offset + 22, y: 19, fill: '#34434b', 'font-size': 10, 'font-weight': 700 }, s.name));
    offset += s.name.length * 7 + 29;
  }

  // Range band, central line, and points.
  for (const s of series) {
    const d = [...s.data].sort((a, b) => a.c - b.c);
    const banded = d.filter((q) => q.min !== null && q.max !== null);
    if (banded.length) {
      const up = banded.map((q, i) => `${i ? 'L' : 'M'}${x(q.c)},${y(q.max as number)}`).join(' ');
      const down = [...banded].reverse().map((q) => `L${x(q.c)},${y(q.min as number)}`).join(' ');
      parts.push(el('path', { d: `${up} ${down}Z`, fill: s.color, opacity: 0.12 }));
    }
    const line = d.filter((q) => q.v !== null);
    parts.push(
      el('path', {
        d: line.map((q, i) => `${i ? 'L' : 'M'}${x(q.c)},${y(q.v as number)}`).join(' '),
        fill: 'none',
        stroke: s.color,
        'stroke-width': 2.5,
      }),
    );
    for (const q of line) {
      const range =
        q.min !== null && q.max !== null ? ` (range ${f(q.min, 2)}–${f(q.max, 2)}, n=${q.n})` : ` (n=${q.n})`;
      parts.push(
        `<circle ${attrs({ cx: x(q.c), cy: y(q.v as number), r: 4, fill: s.color, stroke: '#fff', 'stroke-width': 1.5 })}>` +
          `<title>${esc(`${s.name} at C${q.c}: ${f(q.v, 2)}${range}`)}</title></circle>`,
      );
    }
  }

  const names = series.map((s) => s.name).join(' and ');
  return (
    `<svg viewBox="0 0 ${W} ${H}" class="chart" role="img" aria-label="${esc(caption)}">` +
    `<title>${esc(`${caption} by global concurrency`)}</title>` +
    `<desc>${esc(options.desc ?? `${names} plotted against global concurrency. Shaded bands show the observed repetition range.`)}</desc>` +
    parts.join('') +
    `</svg>`
  );
}

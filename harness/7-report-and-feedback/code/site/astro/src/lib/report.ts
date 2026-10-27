// Typed access to a publication's normalized_data.
//
// Metrics are addressed by their normalized-report-data names ("throughput",
// "joules_per_token"). The renderer's old compact() step renamed these per kind
// ("decode_tps", "gpu_j_per_output_token"); that rename is deliberately not
// reproduced here. Kind-specific wording belongs in labels, not in field names.

export type Kind = 'decode' | 'prefill';

export interface Stat {
  median: number | null;
  minimum: number | null;
  maximum: number | null;
  mean?: number | null;
  standard_deviation?: number | null;
  n: number;
  unit?: string | null;
}

export interface Point {
  concurrency: number;
  [metric: string]: Stat | number | undefined;
}

export interface Series {
  source_id: string;
  points: Point[];
}

export interface NormalizedData {
  schema_version: 1;
  source_campaign: string;
  generated_at?: string | null;
  source_counts: { runs: number; requests: number; errors: number; excluded_runs?: number };
  selection: { policy: string; decode_source_id: string; prefill_source_id: string };
  idle_baseline?: { aggregate_gpu_board_power_w?: number | null; source?: string | null } | null;
  series: Record<Kind, Series>;
  host_fabric?: Record<string, any> | null;
  metric_availability?: Record<string, 'available' | 'unavailable' | 'partial'>;
  exclusions?: { run_id: string; reason: string }[];
}

/** One plotted observation: central value plus the repetition range behind it. */
export interface Datum {
  c: number;
  n: number;
  v: number | null;
  min: number | null;
  max: number | null;
}

export const COLOR = {
  decode: '#086c83',
  prefill: '#d36b32',
  alt: '#aa4050',
  ceiling: '#7557a5',
} as const;

export const KIND_LABEL: Record<Kind, string> = { decode: 'Decode', prefill: 'Prefill' };

const isStat = (value: unknown): value is Stat =>
  typeof value === 'object' && value !== null && 'median' in (value as object);

export function stat(point: Point, metric: string): Stat | null {
  const value = point[metric];
  return isStat(value) ? value : null;
}

/** Central value plus range for one metric across a kind's concurrency sweep. */
export function seriesData(data: NormalizedData, kind: Kind, metric: string): Datum[] {
  const points = data.series[kind]?.points ?? [];
  return points
    .map((point) => {
      const s = stat(point, metric);
      if (!s || s.median === null || !Number.isFinite(s.median)) return null;
      return { c: point.concurrency, n: s.n, v: s.median, min: s.minimum, max: s.maximum };
    })
    .filter((d): d is Datum => d !== null)
    .sort((a, b) => a.c - b.c);
}

/**
 * Coefficient of variation as a percentage. Needs mean and standard_deviation,
 * which single-repetition campaigns do not carry.
 */
export function variationData(data: NormalizedData, kind: Kind, metric: string): Datum[] {
  const points = data.series[kind]?.points ?? [];
  return points
    .map((point) => {
      const s = stat(point, metric);
      if (!s || !s.mean || s.standard_deviation === null || s.standard_deviation === undefined) return null;
      const value = (100 * s.standard_deviation) / s.mean;
      if (!Number.isFinite(value)) return null;
      return { c: point.concurrency, n: s.n, v: value, min: value, max: value };
    })
    .filter((d): d is Datum => d !== null)
    .sort((a, b) => a.c - b.c);
}

/** True when a metric has at least one usable observation in either kind. */
export function hasData(data: NormalizedData, metric: string): boolean {
  return (['decode', 'prefill'] as Kind[]).some((kind) => seriesData(data, kind, metric).length > 0);
}

/** Concurrency axis. Accepts the legacy array shape and the richer object shape. */
export function axisOf(axis: unknown, data: NormalizedData): { ticks: number[]; max: number } {
  const measured = Array.isArray(axis)
    ? (axis as number[])
    : ((axis as any)?.measured_concurrency ??
       data.series.decode.points.map((p) => p.concurrency));
  const ticks = Array.isArray(axis) ? measured : ((axis as any)?.major_ticks ?? measured);
  const max = Array.isArray(axis) ? Math.max(...measured) : ((axis as any)?.maximum ?? Math.max(...measured));
  return { ticks, max };
}

export interface ChartSeries {
  name: string;
  color: string;
  data: Datum[];
}

interface SeriesRequest {
  name?: string;
  color?: string;
  kind: Kind;
  metric: string;
  variation?: boolean;
}

/**
 * Turn catalogue series specs into plottable series.
 *
 * `kindOverride` re-binds every spec to one kind, which is how the decode /
 * prefill toggle renders the same chart twice without duplicating the spec.
 */
export function resolveSeries(
  data: NormalizedData,
  specs: SeriesRequest[],
  kindOverride?: Kind,
): ChartSeries[] {
  return specs.map((spec) => {
    const kind = kindOverride ?? spec.kind;
    const read = spec.variation ? variationData : seriesData;
    return {
      name: spec.name ?? KIND_LABEL[kind],
      color: spec.color ?? COLOR[kind],
      data: read(data, kind, spec.metric),
    };
  });
}

export function f(value: number | null | undefined, digits = 0): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return '—';
  return value.toLocaleString('en-US', { maximumFractionDigits: digits, minimumFractionDigits: digits });
}

/** Escape for interpolation into generated SVG/HTML markup. */
export function esc(value: unknown): string {
  return String(value ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

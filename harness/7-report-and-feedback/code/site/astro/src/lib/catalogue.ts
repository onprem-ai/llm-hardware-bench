// What the report renders, as data.
//
// Each entry names its metric by its normalized-report-data key. Adding a
// publication requires no change here; adding a *metric* is one entry. Section
// ids, eyebrows, headings and chart order match the report template they
// replace, so existing anchors (#throughput, #gpu-path, …) keep working.

import { COLOR, KIND_LABEL, type Kind } from './report';
import type { ChartOptions } from './chart';

export interface SeriesSpec {
  /** Display label. Defaults to the kind's label. */
  name?: string;
  color?: string;
  kind: Kind;
  metric: string;
  /** Plot coefficient of variation instead of the value itself. */
  variation?: boolean;
}

export interface ChartSpec {
  heading: string;
  series: SeriesSpec[];
  options?: ChartOptions;
  unit?: string;
  digits?: number;
  /**
   * Rendered once per kind behind the decode/prefill toggle. Used where the
   * two kinds share an axis but must not be overlaid.
   */
  tabbed?: boolean;
  note?: string;
}

export interface SectionSpec {
  id: string;
  eyebrow: string;
  heading: string;
  /** Single word for the section nav; headings are far too long there. */
  navLabel: string;
  intro?: string;
  charts: ChartSpec[];
}

export interface CatalogueContext {
  gpuCount: number;
  /** Configured active-sequence ceiling, when the publication carries it. */
  ceiling: number | null;
}

/** Both kinds overlaid on one axis — the common case. */
const both = (metric: string): SeriesSpec[] => [
  { kind: 'decode', metric, name: KIND_LABEL.decode, color: COLOR.decode },
  { kind: 'prefill', metric, name: KIND_LABEL.prefill, color: COLOR.prefill },
];

const one = (kind: Kind, metric: string, name: string): SeriesSpec[] => [
  { kind, metric, name, color: COLOR[kind] },
];

const pct = (label: string): ChartOptions => ({ y: label, ref: 100, refLabel: '100% theoretical ceiling' });
const thousands = (v: number) => (v >= 1000 ? `${(v / 1000).toFixed(1)}k` : v.toLocaleString('en-US'));

export function buildCatalogue(ctx: CatalogueContext): SectionSpec[] {
  // A Gen5 x16 link carries about 63 GB/s of payload per GPU endpoint.
  const pcieCeiling = ctx.gpuCount * 63;
  const pcieLabel = `~${pcieCeiling} GB/s: ${ctx.gpuCount} × Gen5 x16`;

  return [
    {
      id: 'throughput',
      eyebrow: '02 · Capacity curves',
      heading: 'Input and output throughput',
      navLabel: 'Throughput',
      charts: [
        {
          heading: 'Decode throughput',
          series: one('decode', 'throughput', 'Decode throughput'),
          options: { y: 'OUTPUT TOKENS / SECOND', tick: thousands },
          unit: 'output tokens/s',
          digits: 0,
        },
        {
          heading: 'Prefill throughput',
          series: one('prefill', 'throughput', 'Prefill throughput'),
          options: { y: 'INPUT TOKENS / SECOND', tick: thousands },
          unit: 'input tokens/s',
          digits: 0,
        },
        {
          heading: 'Decode rate per user',
          series: one('decode', 'per_user_throughput', 'Per-user decode'),
          options: { y: 'OUTPUT TOKENS / SECOND / USER' },
          unit: 'output tokens/s/user',
        },
        {
          heading: 'Prefill rate per user',
          series: one('prefill', 'per_user_throughput', 'Per-user prefill'),
          options: { y: 'INPUT TOKENS / SECOND / USER' },
          unit: 'input tokens/s/user',
        },
        {
          heading: 'Throughput variability',
          series: [
            { kind: 'decode', metric: 'throughput', name: 'Decode variation', color: COLOR.decode, variation: true },
            { kind: 'prefill', metric: 'throughput', name: 'Prefill variation', color: COLOR.prefill, variation: true },
          ],
          options: { y: 'COEFFICIENT OF VARIATION (%)' },
          unit: '%',
          note: 'Requires repeated measurements; a single-repetition campaign has no variance to report.',
        },
      ],
    },
    {
      id: 'latency',
      eyebrow: '03 · Responsiveness',
      heading: 'Latency across concurrency',
      navLabel: 'Latency',
      charts: [
        {
          heading: 'Time to first token',
          tabbed: true,
          series: [
            { kind: 'decode', metric: 'ttft_p50', name: 'p50' },
            { kind: 'decode', metric: 'ttft_p95', name: 'p95', color: COLOR.alt },
          ],
          options: { y: 'TTFT (ms)', log: true, min: 1, tick: (v) => (v >= 1000 ? `${(v / 1000).toFixed(1)}s` : `${Math.round(v)}ms`) },
          unit: 'ms',
          digits: 0,
        },
        {
          heading: 'Inter-token latency',
          tabbed: true,
          series: [
            { kind: 'decode', metric: 'itl_average', name: 'Average' },
            { kind: 'decode', metric: 'itl_p95', name: 'p95', color: COLOR.alt },
          ],
          options: { y: 'INTER-TOKEN LATENCY (ms)' },
          unit: 'ms',
          digits: 1,
        },
      ],
    },
    {
      id: 'energy',
      eyebrow: '04 · Power and efficiency',
      heading: 'GPU board power and token energy',
      navLabel: 'Energy',
      charts: [
        {
          heading: 'Aggregate GPU board power',
          series: both('gpu_board_power'),
          options: { y: 'GPU BOARD POWER (W)' },
          unit: 'W',
          digits: 0,
        },
        {
          heading: 'Energy per useful token',
          series: [
            { kind: 'decode', metric: 'joules_per_token', name: 'Decode', color: COLOR.decode },
            { kind: 'prefill', metric: 'joules_per_token', name: 'Prefill', color: COLOR.prefill },
          ],
          options: { y: 'JOULES / TOKEN' },
          unit: 'J/token',
          digits: 3,
        },
      ],
    },
    {
      id: 'resources',
      eyebrow: '05 · Primary resources',
      heading: 'GPU utilization and temperature, VRAM, CPU, and RAM',
      navLabel: 'Resources',
      charts: [
        { heading: 'GPU utilization', series: both('gpu_utilization'), options: pct('GPU UTILIZATION (%)'), unit: '%', digits: 1 },
        { heading: 'GPU temperature', series: both('gpu_temperature'), options: { y: 'GPU TEMPERATURE (°C)', nozero: true }, unit: '°C', digits: 1 },
        { heading: 'Allocated VRAM', series: both('gpu_vram_used'), options: { y: 'ALLOCATED VRAM (GiB)', nozero: true }, unit: 'GiB', digits: 1 },
        { heading: 'Host CPU busy', series: both('host_cpu_busy'), options: pct('HOST CPU BUSY (%)'), unit: '%', digits: 1 },
        { heading: 'Host RAM used', series: both('host_ram_used'), options: { y: 'HOST RAM USED (GiB)', nozero: true }, unit: 'GiB', digits: 1 },
      ],
    },
    {
      id: 'gpu-path',
      eyebrow: '06 · GPU memory path, clocks, and PCIe endpoints',
      heading: 'GPU execution and host-link traffic',
      navLabel: 'GPU/PCIe',
      charts: [
        { heading: 'Memory-copy utilization', series: both('gpu_memory_copy'), options: pct('MEMORY-COPY UTILIZATION (%)'), unit: '%', digits: 1 },
        { heading: 'SM clock', series: both('gpu_sm_clock'), options: { y: 'SM CLOCK (MHz)', nozero: true }, unit: 'MHz', digits: 0 },
        { heading: 'Memory clock', series: both('gpu_memory_clock'), options: { y: 'MEMORY CLOCK (MHz)', nozero: true }, unit: 'MHz', digits: 0 },
        { heading: 'Aggregate PCIe RX endpoint rate', series: both('pcie_rx'), options: { y: 'AGGREGATE GPU-ENDPOINT RX (GB/s)', ref: pcieCeiling, refLabel: pcieLabel }, unit: 'GB/s' },
        { heading: 'Aggregate PCIe TX endpoint rate', series: both('pcie_tx'), options: { y: 'AGGREGATE GPU-ENDPOINT TX (GB/s)', ref: pcieCeiling, refLabel: pcieLabel }, unit: 'GB/s' },
        { heading: 'PCIe replay-counter change', series: both('pcie_replay_delta'), options: { y: 'REPLAY-COUNTER CHANGE' }, digits: 0 },
      ],
    },
    {
      id: 'serving',
      eyebrow: '07 · Serving behavior',
      heading: 'Scheduler, KV and state caches, and speculative decoding',
      navLabel: 'Serving',
      charts: [
        {
          heading: 'Running requests',
          series: both('running_requests'),
          options: ctx.ceiling
            ? { y: 'RUNNING REQUESTS', ref: ctx.ceiling, refLabel: `${ctx.ceiling} active-sequence ceiling` }
            : { y: 'RUNNING REQUESTS' },
          digits: 0,
        },
        { heading: 'Waiting requests', series: both('waiting_requests'), options: { y: 'WAITING REQUESTS' }, digits: 0 },
        { heading: 'KV-cache utilization', series: both('kv_cache_usage'), options: pct('KV-CACHE USED (%)'), unit: '%', digits: 1 },
        { heading: 'Mamba-state utilization', series: both('mamba_usage'), options: pct('MAMBA-STATE USED (%)'), unit: '%', digits: 1 },
        { heading: 'Speculative-token acceptance', series: both('speculative_acceptance'), options: pct('SPECULATIVE ACCEPTANCE (%)'), unit: '%', digits: 1 },
      ],
    },
    {
      id: 'diagnostics',
      eyebrow: '08 · Detailed diagnostics',
      heading: 'Additional collected metrics',
      navLabel: 'Diagnostics',
      charts: [
        {
          heading: 'CPU user and system',
          series: [
            { kind: 'decode', metric: 'cpu_user', name: 'User', color: COLOR.decode },
            { kind: 'decode', metric: 'cpu_system', name: 'System', color: COLOR.alt },
          ],
          options: { y: 'HOST CPU (%)' },
          unit: '%',
          digits: 1,
        },
        { heading: 'I/O wait', series: both('cpu_iowait'), options: { y: 'CPU I/O WAIT (%)' }, unit: '%', digits: 2 },
        { heading: 'One-minute load average', series: both('host_load1'), options: { y: 'ONE-MINUTE LOAD' }, digits: 1 },
        { heading: 'Inference-process proportional set size', series: both('process_pss'), options: { y: 'INFERENCE PROCESS PSS (GiB)', nozero: true }, unit: 'GiB', digits: 1 },
        { heading: 'Inference-process RSS', series: both('process_rss'), options: { y: 'INFERENCE PROCESS RSS (GiB)', nozero: true }, unit: 'GiB', digits: 1 },
        { heading: 'Inference-process private memory', series: both('process_private'), options: { y: 'PRIVATE MEMORY (GiB)', nozero: true }, unit: 'GiB', digits: 1 },
        { heading: 'Inference-process shared mappings', series: both('process_shared'), options: { y: 'SHARED MAPPINGS (GiB)', nozero: true }, unit: 'GiB', digits: 1 },
        { heading: 'Inference-process swap', series: both('process_swap'), options: { y: 'PROCESS SWAP (GiB)' }, unit: 'GiB', digits: 1 },
        {
          heading: 'HAProxy frontend traffic',
          series: [
            { kind: 'decode', metric: 'haproxy_frontend_ingress', name: 'Frontend ingress', color: COLOR.prefill },
            { kind: 'decode', metric: 'haproxy_frontend_egress', name: 'Frontend egress', color: COLOR.decode },
          ],
          options: { y: 'APPLICATION TRAFFIC (MiB/s)' },
          unit: 'MiB/s',
        },
        {
          heading: 'HAProxy backend traffic',
          series: [
            { kind: 'decode', metric: 'haproxy_backend_ingress', name: 'Backend ingress', color: COLOR.prefill },
            { kind: 'decode', metric: 'haproxy_backend_egress', name: 'Backend egress', color: COLOR.decode },
          ],
          options: { y: 'APPLICATION TRAFFIC (MiB/s)' },
          unit: 'MiB/s',
        },
        {
          heading: 'HAProxy directional bytes per request',
          series: [
            { kind: 'decode', metric: 'haproxy_ingress_per_request', name: 'Ingress/request', color: COLOR.prefill },
            { kind: 'decode', metric: 'haproxy_egress_per_request', name: 'Egress/request', color: COLOR.decode },
          ],
          options: { y: 'DIRECTIONAL KiB / REQUEST' },
          unit: 'KiB/request',
        },
        { heading: 'HAProxy backend queue', series: both('haproxy_queue'), options: { y: 'QUEUED REQUESTS' }, digits: 0 },
        { heading: 'HAProxy backend distribution imbalance', series: both('haproxy_backend_imbalance'), options: { y: 'BACKEND SESSION IMBALANCE (%)' }, unit: '%', digits: 1 },
        { heading: 'Monitored-container CPU', series: both('container_cpu'), options: { y: 'CPU CORES' }, unit: 'cores', digits: 1 },
        { heading: 'Monitored-container memory', series: both('container_memory'), options: { y: 'CONTAINER MEMORY (GiB)' }, unit: 'GiB', digits: 1 },
        { heading: 'Disk write throughput', series: both('disk_write'), options: { y: 'DISK WRITE (MiB/s)' }, unit: 'MiB/s', digits: 1 },
        { heading: 'Container transmit throughput', series: both('container_tx'), options: { y: 'CONTAINER TX (MiB/s)' }, unit: 'MiB/s', digits: 1 },
        { heading: 'Preemption rate', series: both('preemptions'), options: { y: 'PREEMPTIONS / SECOND' }, digits: 2 },
        { heading: 'Server-observed decode-token rate', series: both('server_decode_rate'), options: { y: 'SERVER OUTPUT TOKENS / SECOND' }, unit: 'tokens/s', digits: 0 },
        { heading: 'Server-observed prompt-token rate', series: both('server_prompt_rate'), options: { y: 'SERVER INPUT TOKENS / SECOND' }, unit: 'tokens/s', digits: 0 },
      ],
    },
  ];
}

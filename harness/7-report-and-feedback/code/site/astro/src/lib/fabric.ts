// Host-fabric charts: NCCL grouped bars and the CUDA P2P bandwidth heatmap.
//
// Ported from the Python builders in analysis/render_report.py, which already
// emitted these as server-side SVG. Behaviour is preserved except that the GPU
// count is now a parameter rather than hardcoded to 8.

import { esc } from './report';

const BAR_COLORS = ['#086c83', '#d36b32', '#7557a5'];

export interface BarGroup {
  label: string;
  values: (number | null)[];
}

const unavailable = (reason: string) => `<div class="unavailable">Unavailable — ${esc(reason)}</div>`;

export function groupedBarSvg(
  groups: BarGroup[],
  series: string[],
  yLabel: string,
  theoreticalMax?: number | null,
  theoreticalLabel?: string,
): string {
  const width = 700;
  const height = 340;
  const left = 72;
  const right = 18;
  const top = 48;
  const bottom = 58;

  const values = groups.flatMap((g) => g.values).filter((v): v is number => v !== null && Number.isFinite(v));
  if (!values.length) return unavailable('no fabric measurements');

  const plotW = width - left - right;
  const plotH = height - top - bottom;
  let maximum = Math.max(...values) * 1.15 || 1;
  if (theoreticalMax != null) maximum = Math.max(maximum, theoreticalMax * 1.08);

  const parts: string[] = [
    `<svg class="fabric-svg" viewBox="0 0 ${width} ${height}" role="img" aria-label="${esc(yLabel)}">`,
    `<title>${esc(yLabel)}</title>`,
  ];

  for (let tick = 0; tick < 5; tick++) {
    const value = (maximum * tick) / 4;
    const y = top + plotH - (value / maximum) * plotH;
    parts.push(
      `<line x1="${left}" y1="${y.toFixed(1)}" x2="${width - right}" y2="${y.toFixed(1)}" stroke="#e9eeeb"/>` +
        `<text x="${left - 8}" y="${(y + 4).toFixed(1)}" text-anchor="end" font-size="10" font-weight="700" fill="#45535b">${value.toFixed(0)}</text>`,
    );
  }

  const groupWidth = plotW / groups.length;
  const barWidth = Math.min(34, groupWidth / (series.length + 1));

  groups.forEach((group, groupIndex) => {
    const center = left + groupWidth * (groupIndex + 0.5);
    group.values.forEach((value, index) => {
      if (value === null || !Number.isFinite(value)) return;
      const x = center + (index - (series.length - 1) / 2) * barWidth - barWidth * 0.38;
      const y = top + plotH - (value / maximum) * plotH;
      const barHeight = top + plotH - y;
      parts.push(
        `<rect x="${x.toFixed(1)}" y="${y.toFixed(1)}" width="${(barWidth * 0.76).toFixed(1)}" height="${barHeight.toFixed(1)}" fill="${BAR_COLORS[index % BAR_COLORS.length]}">` +
          `<title>${esc(`${group.label} · ${series[index]}: ${value.toFixed(2)}`)}</title></rect>` +
          `<text x="${(x + barWidth * 0.38).toFixed(1)}" y="${(y - 5).toFixed(1)}" text-anchor="middle" font-size="9" font-weight="700">${value.toFixed(1)}</text>`,
      );
    });
    parts.push(
      `<text x="${center.toFixed(1)}" y="${height - bottom + 22}" text-anchor="middle" font-size="10">${esc(group.label)}</text>`,
    );
  });

  if (theoreticalMax != null) {
    const y = top + plotH - (theoreticalMax / maximum) * plotH;
    parts.push(
      `<line x1="${left}" y1="${y.toFixed(1)}" x2="${width - right}" y2="${y.toFixed(1)}" stroke="#aa4050" stroke-width="1.5" stroke-dasharray="6 4"/>` +
        `<text x="${width - right}" y="${(y - 5).toFixed(1)}" text-anchor="end" font-size="9" fill="#aa4050">${esc(theoreticalLabel ?? theoreticalMax)}</text>`,
    );
  }

  series.forEach((name, index) => {
    const x = left + index * 150;
    parts.push(
      `<rect x="${x}" y="15" width="12" height="12" fill="${BAR_COLORS[index % BAR_COLORS.length]}"/>` +
        `<text x="${x + 18}" y="25" font-size="10" font-weight="700">${esc(name)}</text>`,
    );
  });

  const mid = top + plotH / 2;
  parts.push(
    `<text x="14" y="${mid.toFixed(1)}" transform="rotate(-90 14 ${mid.toFixed(1)})" text-anchor="middle" font-size="11" font-weight="700">${esc(yLabel)}</text></svg>`,
  );
  return parts.join('');
}

export interface P2PRow {
  direction: string;
  source_gpu: number;
  destination_gpu: number;
  value: number;
}

export function p2pHeatmapSvg(rows: P2PRow[], direction: 'unidirectional' | 'bidirectional', gpuCount = 8): string {
  const selected = (rows ?? []).filter((row) => row.direction === direction);
  const lookup = new Map(selected.map((row) => [`${row.source_gpu},${row.destination_gpu}`, row.value]));
  const off = selected.filter((row) => row.source_gpu !== row.destination_gpu).map((row) => row.value);
  if (!off.length) return unavailable('no P2P matrix');

  const low = Math.min(...off);
  const high = Math.max(...off);
  const cell = 43;
  const left = 45;
  const top = 38;
  const width = left + gpuCount * cell + 12;
  const height = top + gpuCount * cell + 42;

  const parts: string[] = [
    `<svg class="fabric-svg" viewBox="0 0 ${width} ${height}" role="img" aria-label="CUDA P2P ${direction} bandwidth matrix">`,
    `<title>${esc(`CUDA P2P ${direction} bandwidth between GPU pairs`)}</title>`,
    `<desc>${esc(`Off-diagonal values range ${low.toFixed(2)} to ${high.toFixed(2)} GB/s.`)}</desc>`,
  ];

  for (let index = 0; index < gpuCount; index++) {
    parts.push(
      `<text x="${left + index * cell + cell / 2}" y="24" text-anchor="middle" font-size="10" font-weight="700">GPU ${index}</text>` +
        `<text x="${left - 6}" y="${top + index * cell + cell / 2 + 4}" text-anchor="end" font-size="10" font-weight="700">GPU ${index}</text>`,
    );
  }

  for (let source = 0; source < gpuCount; source++) {
    for (let destination = 0; destination < gpuCount; destination++) {
      const value = lookup.get(`${source},${destination}`);
      const diagonal = source === destination;
      let color: string;
      let text: string;
      if (diagonal) {
        color = '#d8dfdc';
        text = 'self';
      } else if (value === undefined) {
        color = '#f5f7f6';
        text = '-';
      } else {
        const ratio = high > low ? (value - low) / (high - low) : 0.5;
        color = `rgb(${Math.trunc(225 - 150 * ratio)},${Math.trunc(240 - 130 * ratio)},${Math.trunc(240 - 105 * ratio)})`;
        text = value.toFixed(1);
      }
      const x = left + destination * cell;
      const y = top + source * cell;
      const label = diagonal
        ? `GPU ${source} to itself`
        : `GPU ${source} to GPU ${destination}: ${value === undefined ? 'unavailable' : `${value.toFixed(2)} GB/s`}`;
      parts.push(
        `<rect x="${x}" y="${y}" width="${cell - 1}" height="${cell - 1}" fill="${color}"><title>${esc(label)}</title></rect>` +
          `<text x="${(x + (cell - 1) / 2).toFixed(1)}" y="${(y + cell / 2 + 4).toFixed(1)}" text-anchor="middle" font-size="9">${esc(text)}</text>`,
      );
    }
  }

  const theoretical = direction === 'unidirectional' ? 63 : 126;
  parts.push(
    `<text x="${left + (gpuCount / 2) * cell}" y="${height - 18}" text-anchor="middle" font-size="10">Destination GPU — off-diagonal range ${low.toFixed(2)}-${high.toFixed(2)} GB/s</text>` +
      `<text x="${left + (gpuCount / 2) * cell}" y="${height - 5}" text-anchor="middle" font-size="9" fill="#aa4050">Theoretical Gen5 x16 payload ceiling: about ${theoretical} GB/s per pair</text></svg>`,
  );
  return parts.join('');
}

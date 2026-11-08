// Small SVG charts for the Test Inspector and the Research Brief. They draw only what a ledger row holds.
// Series colours come from CSS classes (.s-<name>), so the same chart reads on the dark inspector
// and on the light brief.
//
// kinds: "stack" (stacked counts per row), "bars" (signed values), "forest" (rate ratios with 95% CIs on a
// log axis) and "grouped" (observed vs predicted risk on the vaulted holdout).

const SERIES_LABEL = {
  organic: "Organic", affiliate: "Affiliate code or sponsored", original: "Original story", repost: "Repost",
  human: "Human", rodent: "Rodent", "in vitro": "In vitro",
  observed: "Observed", scroll: "Scroll's prediction", baseline: "Gatekeeper's baseline (no drug effect)",
};

function esc(s) {
  return String(s == null ? "" : s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
}

function fmt(v, d = 3) {
  if (v == null || Number.isNaN(v)) return "—";
  if (typeof v !== "number") return esc(v);
  const a = Math.abs(v);
  if (a !== 0 && (a < 1e-3 || a >= 1e5)) return v.toExponential(2);
  return String(Number(v.toFixed(d)));
}

const slug = (k) => String(k).replace(/\s+/g, "-");

function fig(chart, svg, legendKeys = []) {
  const legend = legendKeys.length
    ? `<div class="legend">${legendKeys.map((k) => `<span><i class="sw s-${slug(k)}"></i>${esc(SERIES_LABEL[k] || k)}</span>`).join("")}</div>` : "";
  return `<figure class="fig">${chart.title ? `<figcaption>${esc(chart.title)}</figcaption>` : ""}${svg}${legend}</figure>`;
}

function stackChart(chart) {
  const rows = chart.rows || [];
  const max = Math.max(1, ...rows.map((r) => r.parts.reduce((t, p) => t + p.value, 0)));
  const W = 420, row = 24, L = 80, R = 46, H = rows.length * row + 8;
  const sx = (v) => v / max * (W - L - R);
  let svg = `<svg class="chart" viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(chart.title || "counts")}">`;
  const keys = [];
  rows.forEach((r, i) => {
    const y = 4 + i * row;
    let x = L, total = 0;
    svg += `<text class="tick" x="${L - 6}" y="${y + 15}" text-anchor="end">${esc(r.label)}</text>`;
    for (const p of r.parts) {
      if (!keys.includes(p.name)) keys.push(p.name);
      const w = sx(p.value);
      if (w > 0) svg += `<rect class="s-${slug(p.name)}" x="${x.toFixed(1)}" y="${y + 3}" width="${w.toFixed(1)}" height="${row - 8}"><title>${esc(p.name)}: ${p.value}</title></rect>`;
      x += w; total += p.value;
    }
    svg += `<text class="tick" x="${(x + 4).toFixed(1)}" y="${y + 15}">${total}</text>`;
  });
  return fig(chart, svg + "</svg>", keys);
}

function barChart(chart) {
  const bars = chart.bars || [];
  const lo = Math.min(0, ...bars.map((b) => b.value)), hi = Math.max(0, ...bars.map((b) => b.value));
  const span = (hi - lo) || 1;
  const W = 420, row = 22, L = 170, R = 44, H = bars.length * row + 8;
  const sx = (v) => L + (v - lo) / span * (W - L - R);
  let svg = `<svg class="chart" viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(chart.title || "bars")}">`;
  bars.forEach((b, i) => {
    const y = 4 + i * row, x0 = sx(0), x1 = sx(b.value);
    svg += `<text class="tick" x="${L - 6}" y="${y + 14}" text-anchor="end">${esc(b.label)}</text>`
         + `<rect class="${b.value < 0 ? "bar-neg" : "bar"}" x="${Math.min(x0, x1).toFixed(1)}" y="${y + 3}" width="${Math.max(1, Math.abs(x1 - x0)).toFixed(1)}" height="${row - 8}"/>`
         + `<text class="tick" x="${(Math.max(x0, x1) + 4).toFixed(1)}" y="${y + 14}">${fmt(b.value, 2)}</text>`;
  });
  if (lo < 0) svg += `<line class="ref" x1="${sx(0)}" x2="${sx(0)}" y1="2" y2="${H - 2}"/>`;
  return fig(chart, svg + "</svg>");
}

function forestChart(chart) {
  const rows = chart.rows || [];
  const vals = rows.flatMap((r) => [r.est, r.lo, r.hi]).filter((v) => v != null && v > 0);
  let a = Math.log(Math.min(0.5, ...vals) * 0.9), b = Math.log(Math.max(2, ...vals) * 1.1);
  const W = 420, row = 24, L = 170, R = 16, T = 4, B = 34, H = rows.length * row + T + B;
  const sx = (v) => L + (Math.log(v) - a) / (b - a) * (W - L - R);
  let svg = `<svg class="chart" viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(chart.title || "rate ratios")}">`;
  for (const t of [0.25, 0.5, 1, 2, 4]) {
    if (Math.log(t) < a || Math.log(t) > b) continue;
    svg += `<line class="${t === (chart.ref || 1) ? "ref" : "grid"}" x1="${sx(t).toFixed(1)}" x2="${sx(t).toFixed(1)}" y1="${T}" y2="${H - B}"/>`
         + `<text class="tick" x="${sx(t).toFixed(1)}" y="${H - 20}" text-anchor="middle">${t}</text>`;
  }
  rows.forEach((r, i) => {
    const y = T + i * row + row / 2;
    svg += `<text class="tick" x="${L - 6}" y="${y + 4}" text-anchor="end">${esc(r.label)}</text>`;
    if (r.lo != null && r.hi != null) svg += `<line class="ci" x1="${sx(r.lo).toFixed(1)}" x2="${sx(r.hi).toFixed(1)}" y1="${y}" y2="${y}"/>`;
    svg += `<rect class="est" x="${(sx(r.est) - 4).toFixed(1)}" y="${y - 4}" width="8" height="8"><title>${fmt(r.est, 2)}${r.lo != null ? ` (${fmt(r.lo, 2)} to ${fmt(r.hi, 2)})` : ""}</title></rect>`
         + `<text class="tick val" x="${(sx(r.est)).toFixed(1)}" y="${y - 7}" text-anchor="middle">${fmt(r.est, 2)}</text>`;
  });
  svg += `<text class="tick" x="${L}" y="${H - 6}" text-anchor="start">← fewer events</text><text class="tick" x="${W - R}" y="${H - 6}" text-anchor="end">more events →</text>`;
  return fig(chart, svg + "</svg>");
}

function groupedChart(chart) {
  const groups = chart.groups || [];
  const keys = ["observed", "scroll", "baseline"];
  const max = Math.max(1e-6, ...groups.flatMap((g) => keys.map((k) => g.values[k] || 0))) * 1.15;
  const W = 420, H = 170, L = 40, R = 8, T = 10, B = 24;
  const gw = (W - L - R) / Math.max(1, groups.length), bw = Math.min(34, gw / 4);
  const sy = (v) => T + (1 - v / max) * (H - T - B);
  let svg = `<svg class="chart" viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(chart.title || "risk")}">`;
  for (let k = 0; k <= 4; k++) {
    const v = max * k / 4;
    svg += `<line class="grid" x1="${L}" x2="${W - R}" y1="${sy(v).toFixed(1)}" y2="${sy(v).toFixed(1)}"/>`
         + `<text class="tick" x="${L - 4}" y="${(sy(v) + 3).toFixed(1)}" text-anchor="end">${(v * 100).toFixed(v < 0.05 ? 1 : 0)}%</text>`;
  }
  groups.forEach((g, i) => {
    const cx = L + gw * i + gw / 2;
    keys.forEach((k, j) => {
      const v = g.values[k] || 0, x = cx + (j - 1.5) * bw + 2;
      svg += `<rect class="s-${k}" x="${x.toFixed(1)}" y="${sy(v).toFixed(1)}" width="${(bw - 4).toFixed(1)}" height="${(sy(0) - sy(v)).toFixed(1)}"><title>${esc(SERIES_LABEL[k])}: ${(v * 100).toFixed(2)}%</title></rect>`;
    });
    svg += `<text class="tick" x="${cx.toFixed(1)}" y="${H - 6}" text-anchor="middle">${esc(g.label)}</text>`;
  });
  return fig(chart, svg + "</svg>", keys);
}

function chartHTML(chart) {
  if (!chart) return "";
  if (chart.kind === "stack") return stackChart(chart);
  if (chart.kind === "bars") return barChart(chart);
  if (chart.kind === "forest") return forestChart(chart);
  if (chart.kind === "grouped") return groupedChart(chart);
  return "";
}

// HP of each scroll at the end of each level (finale.ranking[].hp_by_level).
function hpChart(rows) {
  const W = 420, H = 180, L = 30, R = 150, T = 10, B = 24;
  const sx = (l) => L + l / 4 * (W - L - R), sy = (h) => T + (1 - h / 100) * (H - T - B);
  let svg = `<svg class="chart" viewBox="0 0 ${W} ${H}" role="img" aria-label="HP after each level">`;
  for (const h of [0, 50, 100]) svg += `<line class="grid" x1="${L}" x2="${W - R}" y1="${sy(h)}" y2="${sy(h)}"/><text class="tick" x="${L - 4}" y="${sy(h) + 3}" text-anchor="end">${h}</text>`;
  ["Start", "I", "II", "III", "IV"].forEach((t, i) => { svg += `<text class="tick" x="${sx(i)}" y="${H - 6}" text-anchor="middle">${t}</text>`; });
  const used = [];
  for (const r of rows) {
    const pts = [[0, 100], ...[1, 2, 3, 4].map((l) => [l, r.hp_by_level[l] ?? r.hp_by_level[String(l)]])].filter((p) => p[1] != null);
    svg += `<path class="line a-${r.archetype}" d="${pts.map((p, i) => `${i ? "L" : "M"}${sx(p[0])},${sy(p[1])}`).join("")}"/>`;
    const lastPt = pts[pts.length - 1];
    let ly = sy(lastPt[1]) + 4;
    while (used.some((u) => Math.abs(u - ly) < 10)) ly -= 10;  // keep labels of equal HP apart
    used.push(ly);
    svg += `<text class="tick a-${r.archetype}-t" x="${sx(lastPt[0]) + 6}" y="${ly}">${esc(r.name.replace(/^The /, ""))} ${lastPt[1]}</text>`;
  }
  return svg + "</svg>";
}

if (typeof module !== "undefined") module.exports = { esc, fmt, chartHTML, hpChart, stackChart, barChart, forestChart, groupedChart };

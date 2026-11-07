// Small SVG charts for the Test Inspector and the Decision Brief. They draw only what a ledger row holds.
// Series colours come from CSS classes (.s-<name>), so the same chart reads on the dark inspector
// and on the light brief.

const SERIES_LABEL = {
  admissions: "Admissions (actual)", signal: "Signal's forecast", news: "News volume (own scale)",
  confounder: "Confounder (rescaled)", agent: "This agent, real-time", baseline: "AR(4) baseline",
  hindsight: "Forecast on finalized data", vintage: "Forecast on data as it stood",
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

function pathOf(xs, ys, sx, sy) {
  let d = "";
  xs.forEach((x, i) => {
    if (ys[i] == null) return;
    d += `${d ? "L" : "M"}${sx(x).toFixed(1)},${sy(ys[i]).toFixed(1)}`;
  });
  return d;
}

// kind "lines" or "vintage". opts.mode = "vintage" | "hindsight" picks which vintage line is shown.
function lineChart(chart, opts = {}) {
  const W = 420, H = 170, L = 34, R = 8, T = 10, B = 22;
  const days = chart.day || [];
  if (!days.length) return "";
  let keys = Object.keys(chart).filter((k) => Array.isArray(chart[k]) && !["day", "surge"].includes(k));
  if (chart.kind === "vintage" && opts.mode) keys = keys.filter((k) => k === "admissions" || k === opts.mode);
  const own = keys.filter((k) => k === "news");  // its own scale: it is not in admissions units
  const shared = keys.filter((k) => !own.includes(k));
  const vals = shared.flatMap((k) => chart[k]).filter((v) => v != null);
  const lo = Math.min(0, ...vals), hi = Math.max(...vals) * 1.05 || 1;
  const x0 = days[0], x1 = days[days.length - 1] || x0 + 1;
  const sx = (x) => L + (x - x0) / Math.max(1, x1 - x0) * (W - L - R);
  const sy = (y) => T + (1 - (y - lo) / (hi - lo)) * (H - T - B);
  let svg = `<svg class="chart" viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(chart.title || "chart")}">`;
  if (chart.surge) {  // shade surge-onset days
    const step = (W - L - R) / Math.max(1, days.length - 1);
    chart.surge.forEach((s, i) => { if (s) svg += `<rect class="surge" x="${(sx(days[i]) - step / 2).toFixed(1)}" y="${T}" width="${step.toFixed(1)}" height="${H - T - B}"/>`; });
  }
  for (let k = 0; k <= 4; k++) {
    const v = lo + (hi - lo) * k / 4;
    svg += `<line class="grid" x1="${L}" x2="${W - R}" y1="${sy(v).toFixed(1)}" y2="${sy(v).toFixed(1)}"/>`
         + `<text class="tick" x="${L - 4}" y="${(sy(v) + 3).toFixed(1)}" text-anchor="end">${Math.round(v)}</text>`;
  }
  svg += `<text class="tick" x="${L}" y="${H - 6}">day ${x0}</text><text class="tick" x="${W - R}" y="${H - 6}" text-anchor="end">day ${x1}</text>`;
  for (const k of own) {
    const v = chart[k].filter((x) => x != null), a = Math.min(...v), b = Math.max(...v) || 1;
    const syo = (y) => T + (1 - (y - a) / ((b - a) || 1)) * (H - T - B);
    svg += `<path class="line s-${k}" d="${pathOf(days, chart[k], sx, syo)}"/>`;
  }
  for (const k of shared) svg += `<path class="line s-${k}" d="${pathOf(days, chart[k], sx, sy)}"/>`;
  svg += "</svg>";
  const legend = keys.map((k) => `<span><i class="sw s-${k}"></i>${esc(SERIES_LABEL[k] || k)}</span>`).join("")
    + (chart.surge ? `<span><i class="sw surge"></i>Surge-onset days</span>` : "");
  return `<figure class="fig">${chart.title ? `<figcaption>${esc(chart.title)}</figcaption>` : ""}${svg}<div class="legend">${legend}</div></figure>`;
}

function barChart(chart) {
  const bars = chart.bars || [];
  const max = Math.max(chart.home || 0, ...bars.map((b) => b.value)) * 1.1 || 1;
  const W = 420, row = 22, L = 130, H = (bars.length + 1) * row + 8;
  const sx = (v) => L + v / max * (W - L - 40);
  let svg = `<svg class="chart" viewBox="0 0 ${W} ${H}" role="img" aria-label="Error by region">`;
  const all = [{ label: "Home region", value: chart.home, home: true }, ...bars];
  all.forEach((b, i) => {
    const y = 4 + i * row;
    svg += `<text class="tick" x="${L - 6}" y="${y + 14}" text-anchor="end">${esc(b.label)}${b.rural ? " (rural)" : ""}</text>`
         + `<rect class="${b.home ? "bar-home" : b.rural ? "bar-rural" : "bar"}" x="${L}" y="${y + 3}" width="${(sx(b.value) - L).toFixed(1)}" height="${row - 8}"/>`
         + `<text class="tick" x="${(sx(b.value) + 4).toFixed(1)}" y="${y + 14}">${fmt(b.value)}</text>`;
  });
  svg += "</svg>";
  return `<figure class="fig"><figcaption>${esc(chart.title || "Normalized error (RMSE / mean) in each region")}</figcaption>${svg}</figure>`;
}

function chartHTML(chart, opts = {}) {
  if (!chart) return "";
  if (chart.kind === "bars") return barChart(chart);
  return lineChart(chart, opts);
}

// HP of each agent at the end of each level (finale.ranking[].hp_by_level).
function hpChart(rows) {
  const W = 420, H = 180, L = 30, R = 70, T = 10, B = 24;
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
    svg += `<text class="tick a-${r.archetype}-t" x="${sx(lastPt[0]) + 6}" y="${ly}">${esc(r.name)} ${lastPt[1]}</text>`;
  }
  return svg + "</svg>";
}

if (typeof module !== "undefined") module.exports = { esc, fmt, chartHTML, hpChart, lineChart, barChart };

// Mystery Bosses: one original pixel-art enemy per research weakness, drawn in code in the same style as the
// dungeon bosses (feet at x, y; 1 unit = 1 pixel before the stage's scale). Each registers into BOSSES, so the
// battle stage draws it with the shared outline. They appear only when the Research Director summons them.

function drawSeasonalWraith(ctx, x, y, f) {  // a cloak that turns through four seasons
  const seasons = [["#9fd8ff", "#e8f6ff"], ["#7fd67a", "#d8ffb0"], ["#ffb347", "#ffe08a"], ["#c0603a", "#ff9a6a"]];
  const [c1, c2] = seasons[Math.floor(f / 50) % 4], hover = Math.round(Math.sin(f / 12) * 2), by = y - 4 + hover;
  for (let i = 0; i < 30; i++) {
    const w = 4 + Math.round(i * 0.5), wob = Math.round(Math.sin(f / 7 + i / 3));
    rect(ctx, x - w + wob, by - 34 + i, w * 2, 1, i % 6 === 0 ? c2 : "#3b2559");
  }
  for (let k = 0; k < 5; k++) rect(ctx, x - 14 + k * 7 + Math.round(Math.sin(f / 5 + k)), by - 4 + (k % 2) * 2, 3, 5, "#3b2559");
  disc(ctx, x, by - 38, 7, "#2a1a44"); disc(ctx, x, by - 37, 5, "#05040c");
  rect(ctx, x - 3, by - 38, 2, 2, c2); rect(ctx, x + 2, by - 38, 2, 2, c2);
  for (let k = 0; k < 6; k++) {  // leaves and snowflakes drifting round it
    const a = f / 30 + k, px = x + Math.round(Math.cos(a) * 20), py = by - 24 + Math.round(Math.sin(a * 1.3) * 12);
    rect(ctx, px, py, 2, 2, k % 2 ? c1 : c2);
  }
  return 48;
}

function drawChronolockAssassin(ctx, x, y, f) {  // a hooded blade-runner wearing a stolen clock
  const cloak = "#1a1430", edge = "#4a3a78", steel = "#c8d0e0", gold = "#e8b847";
  const lean = Math.round(Math.sin(f / 10) * 1);
  rect(ctx, x - 6, y - 10, 4, 10, cloak); rect(ctx, x + 2, y - 10, 4, 10, cloak);
  for (let i = 0; i < 24; i++) { const w = 6 + Math.round(i * 0.25); rect(ctx, x - w + lean, y - 34 + i, w * 2, 1, i % 5 === 0 ? edge : cloak); }
  disc(ctx, x + lean, y - 38, 6, cloak); disc(ctx, x + lean, y - 37, 4, "#05040c");
  rect(ctx, x - 2 + lean, y - 38, 1, 1, "#ff4a5a"); rect(ctx, x + 2 + lean, y - 38, 1, 1, "#ff4a5a");
  disc(ctx, x + lean, y - 24, 5, gold); disc(ctx, x + lean, y - 24, 4, "#f3e9d2");  // the clock, running backwards
  const a = -f / 12;
  rect(ctx, x + lean + Math.round(Math.cos(a) * 3), y - 24 + Math.round(Math.sin(a) * 3), 1, 1, "#15122b");
  rect(ctx, x + lean, y - 24, 1, 1, "#15122b");
  for (const s of [-1, 1]) {  // twin daggers
    const bx = x + s * 13, by = y - 26 + (s > 0 ? Math.round(Math.sin(f / 6) * 2) : 0);
    rect(ctx, bx - 1, by, 2, 3, "#7a5230"); rect(ctx, bx - (s < 0 ? 1 : 0), by - 9, 1, 9, steel); rect(ctx, bx - 2, by + 1, 4, 1, gold);
  }
  for (let k = 0; k < 3; k++) rect(ctx, x - 20 - k * 4, y - 20 + k * 3, 3, 1, (f + k * 5) % 20 < 10 ? "#7fe0ff" : edge);  // afterimages
  return 46;
}

function drawRegionalHydra(ctx, x, y, f) {  // five heads, one per EHR site; the rural ones glow cyan
  const body = "#2f6a4a", belly = "#5fae6a", dark = "#1a3a2a";
  ellipse(ctx, x, y - 10, 16, 8, dark); ellipse(ctx, x, y - 10, 15, 7, body); ellipse(ctx, x, y - 8, 9, 4, belly);
  rect(ctx, x - 12, y - 4, 4, 4, dark); rect(ctx, x + 8, y - 4, 4, 4, dark);
  const heads = [[-18, -34], [-9, -42], [0, -46], [9, -42], [18, -34]];
  heads.forEach(([dx, dy], k) => {
    const sway = Math.round(Math.sin(f / 9 + k * 1.3) * 2), hx = x + dx + sway, hy = y + dy;
    for (let t = 0; t <= 8; t++) rect(ctx, Math.round(x + dx * t / 8 * 0.6 + sway * t / 8) - 1, Math.round(y - 14 + (dy + 14) * t / 8), 3, 2, body);
    disc(ctx, hx, hy, 4, k >= 3 ? "#2f8aa0" : body);
    rect(ctx, hx - 2, hy - 1, 1, 1, k >= 3 ? "#7fe0ff" : "#ffe066"); rect(ctx, hx + 1, hy - 1, 1, 1, k >= 3 ? "#7fe0ff" : "#ffe066");
    rect(ctx, hx - 1, hy + 2, 3, 1, dark);
  });
  return 52;
}

function drawProbabilityPhantom(ctx, x, y, f) {  // a ghost of loaded dice, flickering in and out
  const fade = 0.55 + 0.35 * Math.sin(f / 8), by = y - 6 + Math.round(Math.sin(f / 14) * 3);
  ctx.save(); ctx.globalAlpha = fade;
  for (let i = 0; i < 26; i++) { const w = 9 - Math.abs(i - 10) * 0.25; rect(ctx, x - w, by - 34 + i, w * 2, 1, i % 7 === 0 ? "#b0a0ff" : "#6a5acd"); }
  for (let k = 0; k < 4; k++) rect(ctx, x - 9 + k * 5, by - 8 + (k % 2), 3, 4 + ((f / 6 + k) % 2 | 0), "#6a5acd");
  ctx.restore();
  rect(ctx, x - 4, by - 28, 2, 3, "#05040c"); rect(ctx, x + 2, by - 28, 2, 3, "#05040c"); rect(ctx, x - 2, by - 22, 4, 2, "#05040c");
  for (let k = 0; k < 3; k++) {  // orbiting dice showing random faces
    const a = f / 20 + k * 2.1, dx = x + Math.round(Math.cos(a) * 18), dy = by - 20 + Math.round(Math.sin(a) * 8);
    rect(ctx, dx - 3, dy - 3, 7, 7, "#f3e9d2"); rect(ctx, dx - 3, dy - 3, 7, 1, "#ffffff");
    const face = (Math.floor(f / 15) + k * 3) % 6 + 1;
    const pips = { 1: [[0, 0]], 2: [[-2, -2], [2, 2]], 3: [[-2, -2], [0, 0], [2, 2]], 4: [[-2, -2], [2, -2], [-2, 2], [2, 2]],
                   5: [[-2, -2], [2, -2], [0, 0], [-2, 2], [2, 2]], 6: [[-2, -2], [2, -2], [-2, 0], [2, 0], [-2, 2], [2, 2]] }[face];
    for (const [px, py] of pips) rect(ctx, dx + px, dy + py, 1, 1, "#c0294a");
  }
  return 44;
}

function drawReplicationRevenant(ctx, x, y, f) {  // a skeletal knight in a mirror-plated cuirass, with an echo behind it
  const bone = "#e8e0c8", shade = "#a89c80", plate = "#7fa8c8", dark = "#2a3448";
  for (const [off, alpha] of [[10, 0.3], [0, 1]]) {
    ctx.save(); ctx.globalAlpha = alpha;
    const ox = x + off + (off ? Math.round(Math.sin(f / 10) * 2) : 0);
    rect(ctx, ox - 6, y - 12, 3, 12, bone); rect(ctx, ox + 3, y - 12, 3, 12, bone);
    rect(ctx, ox - 9, y - 32, 18, 20, dark); rect(ctx, ox - 8, y - 31, 16, 18, plate);
    rect(ctx, ox - 8, y - 31, 16, 2, "#c8e0f0"); rect(ctx, ox - 1, y - 29, 2, 14, "#c8e0f0");
    disc(ctx, ox, y - 38, 6, bone); rect(ctx, ox - 3, y - 39, 2, 2, "#05040c"); rect(ctx, ox + 1, y - 39, 2, 2, "#05040c");
    rect(ctx, ox - 2, y - 35, 5, 1, shade);
    rect(ctx, ox + 10, y - 40, 2, 30, "#7a5230"); rect(ctx, ox + 8, y - 44, 6, 4, plate);
    ctx.restore();
  }
  for (let k = 0; k < 4; k++) rect(ctx, x - 14 + k * 9, y - 46 - (k % 2) * 2, 2, 2, (f + k * 6) % 24 < 12 ? "#7fe0ff" : "#3b2559");
  return 50;
}

function drawRedundancyGolem(ctx, x, y, f) {  // built from copies of the same block
  const stone = "#8a8698", lit = "#b8b4c8", dark = "#4a4658", breathe = Math.round(Math.sin(f / 16));
  for (let r = 0; r < 4; r++) for (let c = 0; c < 3; c++) {
    const bx = x - 15 + c * 10, by = y - 12 - r * 9 + breathe * (r > 1 ? 1 : 0);
    rect(ctx, bx, by, 10, 9, dark); rect(ctx, bx + 1, by + 1, 8, 7, stone); rect(ctx, bx + 1, by + 1, 8, 1, lit);
    rect(ctx, bx + 4, by + 4, 2, 2, "#e8b847");  // the same rune, copied on every block
  }
  rect(ctx, x - 6, y - 50 + breathe, 12, 10, dark); rect(ctx, x - 5, y - 49 + breathe, 10, 8, stone);
  rect(ctx, x - 3, y - 46 + breathe, 2, 2, f % 40 < 3 ? dark : "#7fe0ff"); rect(ctx, x + 1, y - 46 + breathe, 2, 2, f % 40 < 3 ? dark : "#7fe0ff");
  rect(ctx, x - 24, y - 36 + breathe, 8, 18, dark); rect(ctx, x - 23, y - 35 + breathe, 6, 16, stone);
  rect(ctx, x + 16, y - 36 + breathe, 8, 18, dark); rect(ctx, x + 17, y - 35 + breathe, 6, 16, stone);
  return 52;
}

function drawConfounderShapeshifter(ctx, x, y, f) {  // a mask-swapping trickster in a coat of borrowed faces
  const phase = Math.floor(f / 40) % 3, coat = ["#c0294a", "#2f9a5a", "#c08a1a"][phase];
  for (let i = 0; i < 26; i++) { const w = 5 + Math.round(i * 0.4); rect(ctx, x - w, y - 30 + i, w * 2, 1, i % 4 === 0 ? "#15122b" : coat); }
  rect(ctx, x - 5, y - 4, 3, 4, "#15122b"); rect(ctx, x + 2, y - 4, 3, 4, "#15122b");
  disc(ctx, x, y - 36, 7, "#15122b");
  const mask = ["#f3e9d2", "#e8b847", "#7fe0ff"][phase];
  ellipse(ctx, x, y - 36, 6, 5, mask);
  rect(ctx, x - 3, y - 37, 2, 1, "#15122b"); rect(ctx, x + 2, y - 37, 2, 1, "#15122b");
  rect(ctx, x - 2, y - 33, 5, 1, phase === 1 ? "#15122b" : "#c0294a");
  for (let k = 0; k < 3; k++) {  // spare masks orbiting
    const a = f / 18 + k * 2.1, mx = x + Math.round(Math.cos(a) * 17), my = y - 26 + Math.round(Math.sin(a) * 9);
    ellipse(ctx, mx, my, 3, 2, ["#f3e9d2", "#e8b847", "#7fe0ff"][(phase + k + 1) % 3]); rect(ctx, mx - 1, my - 1, 1, 1, "#15122b");
  }
  return 46;
}

function drawSchemaGolem(ctx, x, y, f) {  // a ledger-page golem that checks the columns of new data
  const page = "#f3e9d2", ink = "#3a3050", edge = "#8a7a5a";
  rect(ctx, x - 12, y - 36, 24, 30, edge); rect(ctx, x - 11, y - 35, 22, 28, page);
  for (let r = 0; r < 6; r++) rect(ctx, x - 9, y - 32 + r * 4, 18, 1, (r + Math.floor(f / 8)) % 6 === 0 ? "#2f9a5a" : ink);
  for (let c = 0; c < 2; c++) rect(ctx, x - 3 + c * 6, y - 34, 1, 26, ink);
  rect(ctx, x - 8, y - 6, 5, 6, edge); rect(ctx, x + 3, y - 6, 5, 6, edge);
  rect(ctx, x - 18, y - 30, 6, 4, edge); rect(ctx, x + 12, y - 30, 6, 4, edge);
  rect(ctx, x - 5, y - 42, 10, 6, edge); rect(ctx, x - 3, y - 40, 2, 2, "#7fe0ff"); rect(ctx, x + 1, y - 40, 2, 2, "#7fe0ff");
  return 44;
}

Object.assign(BOSSES, {
  m_seasonal: drawSeasonalWraith, m_chronolock: drawChronolockAssassin, m_regional: drawRegionalHydra,
  m_chance: drawProbabilityPhantom, m_replication: drawReplicationRevenant, m_redundancy: drawRedundancyGolem,
  m_confounder: drawConfounderShapeshifter, m_golem: drawSchemaGolem,
});

// The Secret Research Level: the dungeon floods with teal light while it lasts.
function drawSecretFx(ctx, f) {
  ctx.save();
  ctx.globalAlpha = 0.22; ctx.fillStyle = "#1fbfbf"; ctx.fillRect(0, 0, 320, 180);
  ctx.globalAlpha = 0.5;
  for (let k = 0; k < 14; k++) {
    const bx = (k * 37 + f * 0.4) % 330 - 5, by = 170 - ((f * 0.6 + k * 29) % 160);
    rect(ctx, bx, by, 2, 2, "#bff6ff");
  }
  ctx.restore();
}

// The four evidence levels, the world map, the title and the overworld, drawn in code.
// Static tiles are baked once per level; lights, pages, runes and portals animate per frame.
// World is 360x180 game pixels (16x16 tiles); the camera shows 320 of it.

const WORLD_W = 360, VIEW_W = 320, VIEW_H = 180, FLOOR_Y = 112;

function rng(seed) { let s = seed; return () => (s = (s * 16807) % 2147483647) / 2147483647; }

const LEVEL_PAL = {
  1: { name: "rumour", wall: "#2a2433", wallLit: "#3d3548", mortar: "#16121e", floor: "#3a3242", floorLit: "#4a4152",
       crack: "#1a1520", light: "#ffb347", glow: "rgba(255,170,70,", accent: "#8a5a2b" },
  2: { name: "archives", wall: "#2a1a24", wallLit: "#3f2833", mortar: "#140c12", floor: "#3a2a22", floorLit: "#4d3a2c",
       crack: "#20140f", light: "#ffd27a", glow: "rgba(255,210,120,", accent: "#6b3f1f" },
  3: { name: "temple", wall: "#23224a", wallLit: "#34336a", mortar: "#100f26", floor: "#2c2a52", floorLit: "#3c3a6a",
       crack: "#15143a", light: "#7fe0ff", glow: "rgba(130,200,255,", accent: "#9a7aff" },
  4: { name: "citadel", wall: "#1a1030", wallLit: "#2a1a48", mortar: "#0a0618", floor: "#2a2040", floorLit: "#3e3060",
       crack: "#120c22", light: "#d08aff", glow: "rgba(200,140,255,", accent: "#e8b847" },
};

const _baked = {};

function bakeLevel(level) {
  if (_baked[level]) return _baked[level];
  const c = document.createElement("canvas");
  c.width = WORLD_W; c.height = VIEW_H;
  const ctx = c.getContext("2d");
  const P = LEVEL_PAL[level], r = rng(level * 97);
  if (level === 4) cosmos(ctx, r); else bricks(ctx, P, r, level);
  floorTiles(ctx, P, r, level);
  if (level === 1) rumourProps(ctx, P, r);
  if (level === 2) archiveProps(ctx, P, r);
  if (level === 3) templeProps(ctx, P, r);
  if (level === 4) citadelProps(ctx, P, r);
  _baked[level] = c;
  return c;
}

function bricks(ctx, P, r, level) {
  rect(ctx, 0, 0, WORLD_W, FLOOR_Y, P.mortar);
  for (let row = 0; row * 8 < FLOOR_Y; row++) {
    const off = row % 2 ? 8 : 0;
    for (let x = -off; x < WORLD_W; x += 16) {
      const shade = r() < 0.15 ? P.wallLit : P.wall;
      rect(ctx, x + 1, row * 8 + 1, 15, 7, shade);
      rect(ctx, x + 1, row * 8 + 1, 15, 1, P.wallLit);
      if (r() < 0.08) rect(ctx, x + 4 + Math.floor(r() * 8), row * 8 + 3, 3, 1, P.crack);
    }
  }
  // darken toward the ceiling
  for (let y = 0; y < 24; y += 2) for (let x = (y / 2) % 2; x < WORLD_W; x += 2) rect(ctx, x, y, 1, 1, P.mortar);
}

function floorTiles(ctx, P, r, level) {
  rect(ctx, 0, FLOOR_Y, WORLD_W, VIEW_H - FLOOR_Y, P.floor);
  rect(ctx, 0, FLOOR_Y, WORLD_W, 2, P.crack);
  for (let ty = FLOOR_Y + 2; ty < VIEW_H; ty += 16) for (let tx = 0; tx < WORLD_W; tx += 16) {
    rect(ctx, tx, ty, 16, 1, P.crack); rect(ctx, tx, ty, 1, 16, P.crack);
    rect(ctx, tx + 1, ty + 1, 15, 1, P.floorLit);
    if (level === 1 && r() < 0.3) { // cracked stone
      let cx = tx + 3 + Math.floor(r() * 10), cy = ty + 3;
      for (let i = 0; i < 6; i++) { rect(ctx, cx, cy, 1, 1, P.crack); cx += Math.floor(r() * 3) - 1; cy += 1; }
    }
    if (level === 3 && (tx / 16 + (ty - FLOOR_Y) / 16) % 2 === 0) rect(ctx, tx + 1, ty + 2, 15, 14, "#302e5c");
  }
}

function crate(ctx, x, y) {
  rect(ctx, x, y - 12, 14, 12, "#5a3a1f"); rect(ctx, x + 1, y - 11, 12, 10, "#8a5a2b");
  rect(ctx, x + 1, y - 7, 12, 1, "#5a3a1f"); rect(ctx, x + 6, y - 11, 1, 10, "#5a3a1f");
  rect(ctx, x + 1, y - 11, 12, 1, "#a8703f");
}

function cobweb(ctx, x, y, flip) {
  const s = flip ? -1 : 1;
  for (let i = 0; i < 14; i++) { rect(ctx, x + s * i, y, 1, 1, "#8a8698"); rect(ctx, x, y + i, 1, 1, "#8a8698"); }
  for (let i = 0; i < 11; i++) rect(ctx, x + s * i, y + 10 - i, 1, 1, "#6a6678");
  for (let i = 0; i < 6; i++) rect(ctx, x + s * i, y + 5 - i, 1, 1, "#6a6678");
  for (let i = 0; i < 9; i++) rect(ctx, x + s * i, y + i, 1, 1, "#5a5668");
}

function arch(ctx, x, w, h, c) {
  rect(ctx, x, FLOOR_Y - h, w, h, c);
  for (let i = 0; i < w / 2; i++) { const d = Math.round(Math.sqrt(Math.max(0, (w / 2) ** 2 - (i - w / 2) ** 2)) / 2);
    rect(ctx, x + i, FLOOR_Y - h - d, 1, d, c); rect(ctx, x + w - 1 - i, FLOOR_Y - h - d, 1, d, c); }
}

function rumourProps(ctx, P, r) {
  arch(ctx, 70, 24, 34, "#0a080e");   // corridors off the room
  arch(ctx, 262, 22, 30, "#0a080e");
  cobweb(ctx, 0, 0, false); cobweb(ctx, WORLD_W - 1, 0, true); cobweb(ctx, 180, 0, false);
  crate(ctx, 8, FLOOR_Y + 6); crate(ctx, 20, FLOOR_Y + 4); crate(ctx, 336, FLOOR_Y + 6);
  for (let i = 0; i < 14; i++) { // scattered notes: the rumours
    const x = Math.floor(r() * WORLD_W), y = FLOOR_Y + 8 + Math.floor(r() * 56);
    rect(ctx, x, y, 4, 3, "#d8cfb0"); rect(ctx, x + 1, y + 1, 2, 1, "#8a8070");
  }
  for (const x of [40, 140, 230, 320]) { rect(ctx, x, 40, 2, 9, "#3a2a1a"); rect(ctx, x - 1, 39, 4, 1, "#5a3a1f"); }
}

function bookshelf(ctx, x, w, top, r) {
  rect(ctx, x, top, w, FLOOR_Y - top, "#2a1810");
  for (let sy = top + 3; sy < FLOOR_Y - 6; sy += 13) {
    rect(ctx, x + 1, sy + 10, w - 2, 2, "#5a3a1f");
    for (let bx = x + 2; bx < x + w - 3;) {
      const bw = 2 + Math.floor(r() * 2), bh = 6 + Math.floor(r() * 4);
      const col = ["#8a2a3a", "#2a5a8a", "#3f7a3a", "#a0632b", "#6b3fa0", "#c9a46a"][Math.floor(r() * 6)];
      rect(ctx, bx, sy + 10 - bh, bw, bh, col); rect(ctx, bx, sy + 10 - bh, bw, 1, "#f3e9d2");
      bx += bw + (r() < 0.15 ? 2 : 0);
    }
  }
  rect(ctx, x, top, w, 2, "#5a3a1f");
}

function archiveProps(ctx, P, r) {
  for (const [x, w] of [[0, 46], [52, 40], [112, 46], [196, 40], [250, 46], [312, 48]]) bookshelf(ctx, x, w, 8, r);
  for (const x of [100, 180, 300]) { // candlelit study tables
    rect(ctx, x, FLOOR_Y + 10, 34, 4, "#5a3a1f"); rect(ctx, x + 2, FLOOR_Y + 14, 2, 10, "#3a2410"); rect(ctx, x + 30, FLOOR_Y + 14, 2, 10, "#3a2410");
    rect(ctx, x + 6, FLOOR_Y + 8, 8, 2, "#e8d6a0"); rect(ctx, x + 24, FLOOR_Y + 5, 2, 5, "#f3e9d2");
  }
}

function pillar(ctx, x, w) {
  rect(ctx, x - 2, 14, w + 4, 6, "#4a4880"); rect(ctx, x - 2, FLOOR_Y - 6, w + 4, 6, "#4a4880");
  rect(ctx, x, 20, w, FLOOR_Y - 26, "#5c5a96");
  for (let i = 2; i < w; i += 4) rect(ctx, x + i, 20, 1, FLOOR_Y - 26, "#3c3a70");
  rect(ctx, x, 20, 1, FLOOR_Y - 26, "#8a88c8");
}

function templeProps(ctx, P, r) {
  // observatory window with stars
  disc(ctx, 180, 40, 28, "#0a0a20");
  for (let i = 0; i < 40; i++) { const a = r() * 6.28, d = r() * 26; rect(ctx, 180 + Math.cos(a) * d, 40 + Math.sin(a) * d, 1, 1, r() < 0.3 ? "#ffe08a" : "#c0c8ff"); }
  for (let i = -28; i <= 28; i++) rect(ctx, 180 + i, 40, 1, 1, i % 4 ? "#2a2860" : "#4a4880");
  for (const x of [20, 90, 250, 320]) pillar(ctx, x, 14);
}

function cosmos(ctx, r) {
  const bands = ["#05030f", "#0b0620", "#140a32", "#1e0e44", "#2a1250"];
  bands.forEach((c, i) => rect(ctx, 0, i * 24, WORLD_W, 25, c));
  for (let i = 0; i < 160; i++) rect(ctx, Math.floor(r() * WORLD_W), Math.floor(r() * FLOOR_Y), 1, 1, r() < 0.2 ? "#ffe08a" : "#c8c0ff");
  // nebula smears
  for (let i = 0; i < 260; i++) { const x = 60 + r() * 240, y = 20 + Math.sin(x / 30) * 14 + r() * 18;
    rect(ctx, x, y, 2, 1, r() < 0.5 ? "#4a1a6a" : "#2a2a7a"); }
  // the citadel silhouette
  const sil = "#0a0618";
  rect(ctx, 120, 30, 120, FLOOR_Y - 30, sil);
  for (const [x, w, h] of [[110, 16, 70], [140, 12, 92], [172, 16, 104], [204, 12, 90], [236, 16, 72]]) {
    rect(ctx, x, FLOOR_Y - h, w, h, sil); rect(ctx, x + w / 2 - 1, FLOOR_Y - h - 8, 2, 8, sil);
    for (let wy = FLOOR_Y - h + 6; wy < FLOOR_Y - 10; wy += 10) rect(ctx, x + w / 2 - 1, wy, 2, 3, "#e8b847");
  }
}

function citadelProps(ctx, P, r) {
  // glowing government archive doors
  rect(ctx, 168, FLOOR_Y - 26, 24, 26, "#3a2a10"); rect(ctx, 170, FLOOR_Y - 24, 20, 24, "#e8b847");
  rect(ctx, 179, FLOOR_Y - 24, 2, 24, "#a0632b");
}

// Animated layer drawn over the baked level. f = frame counter.
function drawLevelFx(ctx, level, f) {
  const P = LEVEL_PAL[level];
  if (level === 1) {
    for (const x of [40, 140, 230, 320]) torchFx(ctx, x, 39, f, P);
  } else if (level === 2) {
    for (const x of [107, 187, 307]) candle(ctx, x + 18, FLOOR_Y + 5, f);
    for (let i = 0; i < 6; i++) { // floating manuscripts
      const x = 30 + i * 56 + Math.round(Math.sin(f / 30 + i) * 6), y = 40 + Math.round(Math.sin(f / 20 + i * 2) * 5);
      rect(ctx, x, y, 7, 9, "#e8d6a0"); rect(ctx, x + 1, y + 2, 5, 1, "#8a8070"); rect(ctx, x + 1, y + 4, 4, 1, "#8a8070");
      rect(ctx, x + 1, y + 6, 5, 1, "#8a8070");
    }
    const bx = (f * 0.6) % (WORLD_W + 40) - 20, by = 26 + Math.round(Math.sin(f / 9) * 4); // an enchanted book flapping
    const open = f % 16 < 8;
    rect(ctx, bx, by, 5, open ? 4 : 2, "#6b3fa0"); rect(ctx, bx + 5, by, 5, open ? 4 : 2, "#6b3fa0"); rect(ctx, bx + 4, by, 2, 4, "#e8b847");
  } else if (level === 3) {
    for (let i = 0; i < 8; i++) { // pulsing floor runes
      const on = (Math.floor(f / 12) + i) % 4 === 0, x = 18 + i * 44, y = FLOOR_Y + 30 + (i % 2) * 18;
      const c = on ? "#b8f0ff" : "#4a6aa8";
      rect(ctx, x, y, 7, 1, c); rect(ctx, x + 3, y - 3, 1, 7, c); rect(ctx, x + 1, y - 2, 1, 1, c); rect(ctx, x + 5, y + 2, 1, 1, c);
    }
    for (let i = 0; i < 4; i++) { // floating statistical charts
      const x = 50 + i * 80, y = 60 + Math.round(Math.sin(f / 25 + i) * 4);
      rect(ctx, x, y, 16, 12, "rgba(40,40,100,0.7)");
      for (let b = 0; b < 4; b++) { const h = 2 + ((b * 3 + i + Math.floor(f / 30)) % 8);
        rect(ctx, x + 2 + b * 3, y + 11 - h, 2, h, b % 2 ? "#7fe0ff" : "#9a7aff"); }
    }
    glow(ctx, 180, 40, 34, P, 0.08 + 0.03 * Math.sin(f / 15));
  } else if (level === 4) {
    portal(ctx, 60, 70, f, "#d08aff"); portal(ctx, 300, 66, f + 20, "#7fe0ff");
    for (let i = 0; i < 3; i++) { // floating platforms
      const x = 20 + i * 120, y = 30 + i * 6 + Math.round(Math.sin(f / 20 + i) * 3);
      rect(ctx, x, y, 28, 4, "#4a3a6a"); rect(ctx, x, y, 28, 1, "#8a7ab0");
      for (let k = 0; k < 4; k++) rect(ctx, x + 4 + k * 6, y + 4, 3, 2 + k % 2, "#2a1a48");
    }
    for (const [x, h] of [[110, 22], [250, 28]]) crystal(ctx, x, FLOOR_Y, h, f);
    for (let s = 0; s < 6; s++) { // a moving staircase
      const step = (s + Math.floor(f / 10)) % 6;
      rect(ctx, 320 - step * 6, FLOOR_Y - 8 - step * 6, 10, 3, "#5a4a80");
    }
    glow(ctx, 180, FLOOR_Y - 12, 30, P, 0.07 + 0.03 * Math.sin(f / 12));
  }
}

function torchFx(ctx, x, y, f, P) {
  const fl = Math.floor(f / 6) % 3;
  rect(ctx, x - 1, y - 3 + (fl === 1 ? 1 : 0), 4, 3, "#e8692e");
  rect(ctx, x, y - 5 + (fl === 2 ? 1 : 0), 2, 4, "#f7c548");
  rect(ctx, x + (fl ? 1 : 0), y - 6, 1, 2, "#fff2b0");
  glow(ctx, x + 1, y - 2, 26 + fl, P, 0.12);
}

function candle(ctx, x, y, f) {
  rect(ctx, x, y - 1, 1, 2, Math.floor(f / 5) % 2 ? "#fff2b0" : "#f7c548");
  ctx.fillStyle = "rgba(255,210,120,0.10)"; ctx.fillRect(x - 6, y - 6, 13, 13);
}

// Dithered light pool: rings of transparent warm colour, stepped for the pixel look.
function glow(ctx, x, y, radius, P, strength) {
  for (let k = 3; k >= 1; k--) {
    ctx.fillStyle = `${P.glow}${(strength / k).toFixed(3)})`;
    const rr = Math.round(radius * k / 3);
    for (let dy = -rr; dy <= rr; dy += 2) { const w = Math.round(Math.sqrt(rr * rr - dy * dy));
      ctx.fillRect(Math.round(x - w), Math.round(y + dy), w * 2, 2); }
  }
}

function portal(ctx, x, y, f, color) {
  ellipse(ctx, x, y, 12, 18, "#15122b");
  for (let k = 0; k < 3; k++) ellipse(ctx, x, y, 10 - k * 3, 16 - k * 5, k % 2 ? "#2a1a48" : color);
  for (let i = 0; i < 10; i++) { const a = f / 10 + i * 0.63; rect(ctx, x + Math.round(Math.cos(a) * 9), y + Math.round(Math.sin(a) * 15), 1, 1, "#ffffff"); }
}

function crystal(ctx, x, base, h, f) {
  const shine = (f % 80) < 10;
  for (let i = 0; i < h; i++) { const w = Math.round(Math.min(i, h - i) * 0.5) + 1;
    rect(ctx, x - w, base - i, w * 2, 1, i % 5 === 0 ? "#b8f0ff" : "#4ab0ff"); }
  if (shine) rect(ctx, x - 1, base - h + 4, 2, h - 8, "#ffffff");
  glow(ctx, x, base - h / 2, h * 0.8, LEVEL_PAL[3], 0.06);
}

// ---------- title, world map, overworld ----------

function drawTitleScene(ctx, f) {
  rect(ctx, 0, 0, VIEW_W, VIEW_H, "#0d0b1e");
  const r = rng(11);
  for (let i = 0; i < 70; i++) rect(ctx, Math.floor(r() * VIEW_W), Math.floor(r() * 80), 1, 1, r() < 0.3 ? "#ffe08a" : "#8a86b0");
  // mountain + dungeon gate
  for (let x = 0; x < VIEW_W; x++) { const h = 50 + Math.round(Math.sin(x / 23) * 8 + Math.sin(x / 7) * 3);
    rect(ctx, x, VIEW_H - h - 40, 1, h + 40, "#1a1530"); }
  rect(ctx, 0, 150, VIEW_W, 30, "#15122b");
  rect(ctx, 120, 72, 80, 80, "#2a2433");
  for (let row = 0; row < 10; row++) for (let x = 120 + (row % 2) * 4; x < 200; x += 8) rect(ctx, x, 72 + row * 8, 7, 7, row % 3 ? "#3d3548" : "#34303f");
  for (let y = 100; y < 150; y++) rect(ctx, 140, y, 40, 1, "#05040a");
  ellipse(ctx, 160, 100, 20, 14, "#05040a");
  const P = LEVEL_PAL[1];
  torchFx(ctx, 128, 104, f, P); torchFx(ctx, 190, 104, f + 3, P);
  // eyes in the dark
  if (f % 120 < 100) { rect(ctx, 152, 112, 1, 1, "#ff4a5a"); rect(ctx, 156, 112, 1, 1, "#ff4a5a"); }
  if ((f + 40) % 150 < 110) { rect(ctx, 165, 122, 1, 1, "#7fe0ff"); rect(ctx, 168, 122, 1, 1, "#7fe0ff"); }
}

const MAP_NODES = [
  { level: 1, x: 52, y: 128 }, { level: 2, x: 120, y: 84 }, { level: 3, x: 200, y: 118 }, { level: 4, x: 268, y: 58 },
];

function drawWorldMap(ctx, f, current, marker) {
  rect(ctx, 0, 0, VIEW_W, VIEW_H, "#0d0b1e");
  // parchment-dark map with a gold border
  rect(ctx, 8, 8, VIEW_W - 16, VIEW_H - 16, "#2a2238"); rect(ctx, 10, 10, VIEW_W - 20, VIEW_H - 20, "#3a3048");
  rect(ctx, 8, 8, VIEW_W - 16, 1, "#e8b847"); rect(ctx, 8, VIEW_H - 9, VIEW_W - 16, 1, "#e8b847");
  rect(ctx, 8, 8, 1, VIEW_H - 16, "#e8b847"); rect(ctx, VIEW_W - 9, 8, 1, VIEW_H - 16, "#e8b847");
  const r = rng(5);
  for (let i = 0; i < 90; i++) { const x = 14 + r() * 290, y = 14 + r() * 150;
    rect(ctx, x, y, 3, 1, "#463c58"); }
  // mountains and trees as map glyphs
  for (let i = 0; i < 12; i++) { const x = 20 + r() * 280, y = 20 + r() * 140;
    for (let k = 0; k < 4; k++) rect(ctx, x - k, y + k, k * 2 + 1, 1, "#524866"); }
  // dotted path
  for (let i = 0; i < MAP_NODES.length - 1; i++) {
    const a = MAP_NODES[i], b = MAP_NODES[i + 1];
    for (let t = 0; t <= 1; t += 0.04) {
      const x = a.x + (b.x - a.x) * t, y = a.y + (b.y - a.y) * t + Math.sin(t * Math.PI) * -10;
      rect(ctx, x, y, 2, 2, b.level <= current ? "#e8b847" : "#6a5a80");
    }
  }
  const icons = [mapDungeon, mapLibrary, mapTemple, mapCitadel];
  MAP_NODES.forEach((n, i) => {
    const lit = n.level <= current;
    if (n.level === current) glow(ctx, n.x, n.y - 8, 22, LEVEL_PAL[n.level], 0.18 + 0.06 * Math.sin(f / 8));
    icons[i](ctx, n.x, n.y, lit, f);
  });
  // end: the overworld, beyond the citadel
  rect(ctx, 296, 22, 14, 10, current > 4 ? "#5fd67a" : "#4a405a");
  if (marker) {
    const bob = Math.round(Math.sin(f / 6));
    rect(ctx, marker.x - 3, marker.y - 22 + bob, 7, 7, "#e8b847"); rect(ctx, marker.x - 2, marker.y - 21 + bob, 5, 5, "#c0294a");
    rect(ctx, marker.x, marker.y - 15 + bob, 1, 6, "#e8b847");
  }
}

function mapDungeon(ctx, x, y, lit) {
  const c = lit ? "#8a8698" : "#4a4458";
  rect(ctx, x - 10, y - 12, 20, 12, c);
  ellipse(ctx, x, y - 4, 4, 4, "#05040a"); rect(ctx, x - 4, y - 4, 9, 4, "#05040a");
  if (lit) { rect(ctx, x - 9, y - 16, 2, 3, "#ffb347"); rect(ctx, x + 8, y - 16, 2, 3, "#ffb347"); }
}
function mapLibrary(ctx, x, y, lit) {
  const c = lit ? "#a0632b" : "#4a4458";
  rect(ctx, x - 12, y - 16, 24, 16, c); for (let k = 0; k < 5; k++) rect(ctx, x - 10 + k * 5, y - 14, 3, 12, lit ? ["#8a2a3a", "#2a5a8a", "#3f7a3a", "#6b3fa0", "#c9a46a"][k] : "#3a3448");
  for (let k = 0; k < 6; k++) rect(ctx, x - 12 + k * 2, y - 22 + k, 24 - k * 4, 1, c);
}
function mapTemple(ctx, x, y, lit) {
  const c = lit ? "#7a78c0" : "#4a4458";
  rect(ctx, x - 14, y - 4, 28, 4, c); for (let k = 0; k < 4; k++) rect(ctx, x - 12 + k * 7, y - 18, 3, 14, c);
  for (let k = 0; k < 7; k++) rect(ctx, x - 15 + k * 2, y - 24 + k, 30 - k * 4, 1, c);
  if (lit) rect(ctx, x - 1, y - 22, 2, 2, "#7fe0ff");
}
function mapCitadel(ctx, x, y, lit, f) {
  const c = lit ? "#6b3fa0" : "#4a4458";
  rect(ctx, x - 12, y - 18, 24, 18, c); for (const dx of [-12, -2, 8]) rect(ctx, x + dx, y - 30 + (dx === -2 ? -6 : 0), 4, 14 + (dx === -2 ? 6 : 0), c);
  if (lit) { rect(ctx, x - 1, y - 36, 2, 2, (f % 20) < 10 ? "#ffe08a" : "#d08aff"); rect(ctx, x - 2, y - 10, 4, 10, "#e8b847"); }
}

function drawOverworld(ctx, f) {
  const sky = ["#3a6aa8", "#5a8ac8", "#7aaad8", "#a8c8e0", "#e8d6a0"];
  sky.forEach((c, i) => rect(ctx, 0, i * 23, VIEW_W, 24, c));
  disc(ctx, 260, 36, 12, "#ffe08a"); disc(ctx, 260, 36, 9, "#fff2b0");
  for (let i = 0; i < 3; i++) { const x = ((f * 0.2 + i * 120) % 380) - 40; ellipse(ctx, x, 24 + i * 12, 14, 3, "#f3f3ff"); }
  for (let x = 0; x < VIEW_W; x++) { const h = 14 + Math.round(Math.sin(x / 30) * 6 + Math.sin(x / 11) * 2);
    rect(ctx, x, FLOOR_Y - h, 1, h, "#4a7a4a"); rect(ctx, x, FLOOR_Y - h, 1, 1, "#6a9a5a"); }
  rect(ctx, 0, FLOOR_Y, VIEW_W, VIEW_H - FLOOR_Y, "#5a9a4a");
  const r = rng(3);
  for (let i = 0; i < 120; i++) rect(ctx, r() * VIEW_W, FLOOR_Y + r() * 68, 1, 2, r() < 0.5 ? "#4a8a3a" : "#7aba5a");
  for (let i = 0; i < 14; i++) { const x = r() * VIEW_W, y = FLOOR_Y + 6 + r() * 60;
    rect(ctx, x, y, 2, 2, ["#ff6b8a", "#ffe066", "#f3f3ff"][i % 3]); }
  portal(ctx, 30, FLOOR_Y - 8, f, "#d08aff");
}

if (typeof module !== "undefined") module.exports = { MAP_NODES, LEVEL_PAL, WORLD_W, VIEW_W, VIEW_H, FLOOR_Y };

// Original pixel-art sprites for the Hypothesis Gauntlet. 1 sprite pixel = 1 game pixel;
// the 320x180 game canvas is scaled up with nearest-neighbour (image-rendering: pixelated).
//
// Small sprites are character maps: each letter is a palette colour, "." is transparent.
// Symmetric ones are written as their left half and mirrored. Bosses are drawn in code.

const COLORS = {
  navy: "#0d0b1e", ink: "#15122b", charcoal: "#1f1d2b", purple: "#3b2559", violet: "#6b3fa0",
  gold: "#e8b847", goldLit: "#ffe08a", bone: "#f3e9d2", blood: "#c0294a", heal: "#5fd67a",
  cyan: "#7fe0ff", torch: "#ffb347",
};

function mirror(half) { return half.map((r) => r + [...r].reverse().join("")); }

// ---------- heroes: a head shape on a shared robed body, recoloured per class ----------

const HEADS = {
  pointy: [
    "........HH......",
    ".......HHH......",
    "......HHHH......",
    ".....HHHHHA.....",
    "....HHHHHHH.....",
    "...TTTTTTTTT....",
    ".....OSSSSO..W..",
    ".....SESSES..W..",
    ".....SSSSSS..W..",
  ],
  hood: [
    "................",
    "......HHHH......",
    ".....HHHHHH.....",
    "....HHHHHHHH....",
    "....HTTTTTTH....",
    "....HOSSSSOH.W..",
    "....HSESSESH.W..",
    "....HSSSSSSH.W..",
    ".....HSSSSH..W..",
  ],
  cap: [
    "................",
    "..........A.....",
    ".........AA.....",
    ".....HHHHA......",
    "....HHHHHHH.....",
    "...HHHHHHHHHH...",
    ".....OSSSSO..W..",
    ".....SESSES..W..",
    ".....SSSSSS..W..",
  ],
  circlet: [
    "................",
    "................",
    ".....OOOOOO.....",
    "....OHHHHHHO....",
    "....OTATTATO....",
    ".....OSSSSO..W..",
    ".....SESSES..W..",
    ".....SSSSSS..W..",
    "......SSSS...W..",
  ],
};

const BODY = [
  "....RRRRRRRRAWA.",
  "...RRRTRRTRRSW..",
  "...SRRTRRTRR.W..",
  "....RRTRRTRR.W..",
  "....RRRRRRRR.W..",
  "...RRRRRRRRRRW..",
  "....BB....BB....",
];

const CLASSES = {
  Alchemist:    { head: "pointy",  H: "#6b3fa0", T: "#e8b847", R: "#4a2c7a", A: "#7fe0c0", W: "#8a5a2b" },
  Herbalist:    { head: "hood",    H: "#3f7a3a", T: "#a7d36b", R: "#2f5a2c", A: "#e8b847", W: "#7a5230" },
  Seer:         { head: "hood",    H: "#2b3f8a", T: "#9ad7ff", R: "#1f2d66", A: "#b8f0ff", W: "#c0c8ff" },
  Chronomancer: { head: "pointy",  H: "#a0632b", T: "#ffd27a", R: "#6b3f1f", A: "#ffe9a8", W: "#e8b847" },
  Ranger:       { head: "cap",     H: "#4d6b2f", T: "#c9a46a", R: "#3a4f25", A: "#e05a3a", W: "#8a5a2b" },
  Cleric:       { head: "circlet", H: "#e8e0c8", T: "#e8b847", R: "#d8d0c0", A: "#ff6b8a", W: "#e8b847" },
  Bard:         { head: "cap",     H: "#a8324a", T: "#f2c14e", R: "#7a2238", A: "#f2f2f2", W: "#c98f55" },
  Astrologer:   { head: "pointy",  H: "#1c2a5e", T: "#c0c8ff", R: "#141f47", A: "#f7e27a", W: "#9aa6d8" },
  Wanderer:     { head: "hood",    H: "#5a5668", T: "#9a96a8", R: "#3e3b4a", A: "#e8b847", W: "#7a5230" },
  // the three research roles
  Researcher:   { head: "hood",    H: "#1f6f78", T: "#e8b847", R: "#17525a", A: "#ffe08a", W: "#e8b847" },
  Skeptic:      { head: "hood",    H: "#5c1a2e", T: "#c0294a", R: "#3d1220", A: "#ff9aa8", W: "#9a96a8" },
  Judge:        { head: "circlet", H: "#3b2559", T: "#e8b847", R: "#2a1a44", A: "#7fe0ff", W: "#e8b847" },
};
const SKIN = ["#f1c9a5", "#d9a066", "#a8714a", "#7a4a2e", "#e8b48a", "#c68863"];

function heroMap(cls) { return [...HEADS[(CLASSES[cls] || CLASSES.Wanderer).head], ...BODY]; }
function heroPalette(cls, skinIndex = 0) {
  const c = CLASSES[cls] || CLASSES.Wanderer;
  return { H: c.H, T: c.T, R: c.R, A: c.A, W: c.W, S: SKIN[skinIndex % SKIN.length], E: "#1a1020",
           O: "#2a1a1a", B: "#2a1f1a" };
}

// ---------- enemies ----------

const ENEMY_ART = {
  slime: { map: mirror([
    "........", "........", "........", "........", "........", "......DD", ".....DGG", "....DGLL",
    "...DGLGG", "...DGGEP", "..DGGGEP", "..DGGGGG", "..DGGGGD", "..DGGGGG", "...DDGGG", ".....DDD"]),
    pal: { D: "#1d4a2a", G: "#4fbf5f", L: "#b6f5a0", E: "#f3e9d2", P: "#15122b" } },
  goblin: { map: mirror([
    "........", "........", "D.......", "GD...DDD", ".GDDDGGG", "..DGGGGG", "..DGYDGG", "...DGGGG",
    "....DGWG", ".....DDD", "....CCCC", "...GCCSS", "...GCCCC", "....CCCC", "....DD.D", "........"]),
    pal: { D: "#1f2a12", G: "#7aa84a", Y: "#ffe066", W: "#f3e9d2", C: "#7a4a2e", S: "#e8d6a0" } },
  bat: { map: mirror([
    "........", "........", "........", "D.......", "DD......", "DWD...D.", "DWWD..DB", "DWWWDDBB",
    ".DWWWBBE", ".DWWWBBB", "..DWDBBF", "...D.DBB", "......DD", "........", "........", "........"]),
    pal: { D: "#1a1028", W: "#5a3a7a", B: "#3b2559", E: "#ff4a5a", F: "#f3e9d2" } },
  wisp: { map: mirror([
    "........", ".......O", "......OO", ".....OIO", "....OIIO", "...OIIII", "...OIICC", "..OIICEC",
    "..OIICCC", "..OIIICC", "..OIIIII", "...OIIII", "...O.OII", "..O...OI", "......O.", "........"]),
    pal: { O: "#5a3aa8", I: "#9a7aff", C: "#e6dcff", E: "#1a1028" } },
  mimic: { map: mirror([
    "........", "........", "..DDDDDD", "..DCCCCC", "..DCEDCC", "..DCCCCC", "..DDDDDD", "..DPPPPP",
    "..DTDTDT", "..DRRRRR", "..DTDTDT", "..DPPPPP", "..DDDDDD", "..DCCCCC", "..DDDDDD", "........"]),
    pal: { D: "#2a1410", C: "#8a3a2a", E: "#ffe066", P: "#e8d6a0", T: "#f3e9d2", R: "#c0294a" } },
  skeleton: { map: mirror([
    "........", "....DDDD", "...DBBBB", "...DBBBB", "...DBDDB", "...DBDDB", "....DBBB", ".....DBD",
    "....DDBD", "...DBBBB", "..DB.BDB", "..D..BBB", ".....BDB", ".....DB.", "....DB..", "....DD.."]),
    pal: { D: "#3a3446", B: "#e8e0c8" } },
  spider: { map: mirror([
    "........", "........", "L.......", ".L....DD", "..L..DBB", "LL.LDBBB", "..LLDBEB", ".L.LDBBB",
    "L..LDBBB", "..L.DBBB", ".L..LDBB", "L..L..DD", "...L....", "..L.....", "........", "........"]),
    pal: { D: "#1a1028", B: "#4a2a5a", E: "#ff4a5a", L: "#2a1a3a" } },
  phantom: { map: mirror([
    "........", "......SS", ".....SWW", "....SWWW", "...SWWWW", "...SWEEW", "...SWEEW", "...SWWWW",
    "..SWWWWW", "..SWWWEE", "..SWWWWW", "..SWWWWW", "..SWWWWW", "..SW.SWW", "..S...SW", "........"]),
    pal: { S: "#4a6a9a", W: "#c8e0ff", E: "#15122b" } },
  knight: { map: mirror([
    ".......R", "......RR", ".....DDD", "....DAAA", "....DAAA", "....DVVV", "....DAAA", "...DDAGA",
    "..DAAAAA", ".SSSDAAA", ".SGSDAAA", ".SSSDAAA", "..S.DAAA", "....DA.D", "....DA.D", "....DD.D"]),
    pal: { R: "#c0294a", D: "#1f1d2b", A: "#9a96a8", V: "#15122b", G: "#e8b847", S: "#3b2559" } },
  sentinel: { map: mirror([
    "........", ".....DDD", "....DSSS", "....DSLS", "....DSEE", "....DSSS", "..DDDDDD", ".DSSSSSS",
    ".DSLSSRS", ".DSSSSRS", ".DSS.SSS", "..DD.SSS", ".....SSD", "....DSSD", "....DSS.", "....DDD."]),
    pal: { D: "#2a2838", S: "#6a6880", L: "#9a98b0", E: "#7fe0ff", R: "#7fe0ff" } },
  wraith: { map: mirror([
    "........", ".....DDD", "....DCCC", "...DCCLL", "...DCDDD", "...DCDEE", "...DCDDD", "..DCCCDD",
    "..DCCCCC", ".HDCCLCC", ".H.DCCCC", "...DCCLC", "...DCCCC", "..DCC.CC", "..D...DC", "........"]),
    pal: { D: "#0d0b1e", C: "#3b2559", L: "#6b3fa0", E: "#d08aff", H: "#c8c0d8" } },
};

// ---------- rendering + cache ----------

const _cache = new Map();

function bake(key, map, pal) {
  if (_cache.has(key)) return _cache.get(key);
  const h = map.length, w = map[0].length;
  const c = document.createElement("canvas");
  c.width = w; c.height = h;
  const ctx = c.getContext("2d");
  map.forEach((row, y) => [...row].forEach((ch, x) => {
    if (ch !== "." && pal[ch]) { ctx.fillStyle = pal[ch]; ctx.fillRect(x, y, 1, 1); }
  }));
  _cache.set(key, c);
  return c;
}

// A white silhouette of any baked sprite, for hit flashes.
function flashOf(key, img) {
  const k = key + ":flash";
  if (_cache.has(k)) return _cache.get(k);
  const c = document.createElement("canvas");
  c.width = img.width; c.height = img.height;
  const ctx = c.getContext("2d");
  ctx.drawImage(img, 0, 0);
  ctx.globalCompositeOperation = "source-in";
  ctx.fillStyle = "#ffffff";
  ctx.fillRect(0, 0, c.width, c.height);
  _cache.set(k, c);
  return c;
}

function heroSprite(cls, skin) { return bake(`hero:${cls}:${skin}`, heroMap(cls), heroPalette(cls, skin)); }
function enemySprite(kind) { const a = ENEMY_ART[kind]; return a ? bake(`enemy:${kind}`, a.map, a.pal) : null; }

// Draw a sprite with its feet at (x, y). opts: flip, flash, alpha.
function blit(ctx, img, x, y, opts = {}) {
  if (!img) return;
  ctx.save();
  if (opts.alpha != null) ctx.globalAlpha = opts.alpha;
  const dx = Math.round(x - img.width / 2), dy = Math.round(y - img.height);
  if (opts.flip) { ctx.translate(dx + img.width, dy); ctx.scale(-1, 1); ctx.drawImage(img, 0, 0); }
  else ctx.drawImage(img, dx, dy);
  ctx.restore();
}

// ---------- tiny pixel font (3x5) for floating numbers ----------

const DIGITS = {
  0: "111101101101111", 1: "010110010010111", 2: "111001111100111", 3: "111001111001111",
  4: "101101111001001", 5: "111100111001111", 6: "111100111101111", 7: "111001010010010",
  8: "111101111101111", 9: "111101111001111", "+": "000010111010000", "-": "000000111000000",
  "%": "101001010100101", " ": "000000000000000",
};

function pixelText(ctx, text, x, y, color, shadow = COLORS.navy) {
  const s = String(text);
  const w = s.length * 4 - 1;
  let cx = Math.round(x - w / 2);
  for (const ch of s) {
    const g = DIGITS[ch];
    if (g) for (let i = 0; i < 15; i++) if (g[i] === "1") {
      const px = cx + (i % 3), py = Math.round(y) + Math.floor(i / 3);
      ctx.fillStyle = shadow; ctx.fillRect(px + 1, py + 1, 1, 1);
      ctx.fillStyle = color; ctx.fillRect(px, py, 1, 1);
    }
    cx += 4;
  }
}

// ---------- primitives shared with the bosses and worlds ----------

function rect(ctx, x, y, w, h, c) { ctx.fillStyle = c; ctx.fillRect(Math.round(x), Math.round(y), w, h); }

function disc(ctx, cx, cy, r, c) {
  ctx.fillStyle = c;
  for (let y = -r; y <= r; y++) {
    const w = Math.floor(Math.sqrt(r * r - y * y + r * 0.8));
    ctx.fillRect(Math.round(cx - w), Math.round(cy + y), w * 2 + 1, 1);
  }
}

function ellipse(ctx, cx, cy, rx, ry, c) {
  ctx.fillStyle = c;
  for (let y = -ry; y <= ry; y++) {
    const w = Math.round(rx * Math.sqrt(Math.max(0, 1 - (y * y) / (ry * ry + 0.5))));
    ctx.fillRect(Math.round(cx - w), Math.round(cy + y), w * 2 + 1, 1);
  }
}

// ---------- bosses (drawn each frame: they animate) ----------
// Each takes feet position (x, y), frame f, and a highlight flag; returns its height.

function drawChimera(ctx, x, y, f, head) {
  const bob = Math.round(Math.sin(f / 10)), gold = "#c9913a", mane = "#8a4a1a", dark = "#2a1410";
  // body + legs
  ellipse(ctx, x, y - 12, 15, 7, dark);
  ellipse(ctx, x, y - 12, 14, 6, gold);
  for (const lx of [-11, -5, 5, 11]) { rect(ctx, x + lx - 1, y - 7, 3, 7, dark); rect(ctx, x + lx, y - 7, 2, 6, gold); }
  // serpent tail (Selection Bias head) curling up behind
  const sel = head === "Selection Bias", tail = sel ? "#7fe08a" : "#3f8a4a";
  for (let i = 0; i < 12; i++) rect(ctx, x + 14 + Math.round(Math.sin(i / 2 + f / 8) * 2), y - 14 - i * 1.4 + bob, 3, 2, tail);
  disc(ctx, x + 15, y - 32 + bob, 3, tail); rect(ctx, x + 14, y - 33 + bob, 1, 1, "#ff4a5a"); rect(ctx, x + 17, y - 33 + bob, 1, 1, "#ff4a5a");
  // goat head (publication bias) on the back
  disc(ctx, x + 5, y - 25 + bob, 4, "#8a8698");
  rect(ctx, x + 2, y - 32 + bob, 2, 4, "#d8d0c0"); rect(ctx, x + 7, y - 32 + bob, 2, 4, "#d8d0c0");
  rect(ctx, x + 4, y - 25 + bob, 1, 1, "#ffe066");
  // lion head (Overfitting) in front
  const over = head === "Overfitting";
  disc(ctx, x - 10, y - 22 + bob, 8, over ? "#ff8a3a" : mane);
  disc(ctx, x - 10, y - 21 + bob, 5, gold);
  rect(ctx, x - 13, y - 23 + bob, 2, 2, over ? "#ffffff" : "#ffe066"); rect(ctx, x - 8, y - 23 + bob, 2, 2, over ? "#ffffff" : "#ffe066");
  rect(ctx, x - 12, y - 18 + bob, 5, 1, dark);
  if (f % 20 < 10) { rect(ctx, x - 12, y - 17 + bob, 1, 1, "#f3e9d2"); rect(ctx, x - 8, y - 17 + bob, 1, 1, "#f3e9d2"); }
  return 36;
}

function drawChronolock(ctx, x, y, f) {
  const bronze = "#a0632b", lit = "#ffd27a", dark = "#2a1a10", glass = "#9ad7ff";
  // pedestal
  rect(ctx, x - 12, y - 4, 24, 4, dark); rect(ctx, x - 11, y - 4, 22, 1, bronze);
  // hourglass torso
  for (let i = 0; i < 12; i++) {
    const w = 10 - Math.round(i * 0.75);
    rect(ctx, x - w, y - 6 - i, w * 2, 1, glass);
    rect(ctx, x - w, y - 29 + i, w * 2, 1, glass);
  }
  const sand = (f % 60) / 60;
  for (let i = 0; i < Math.round(10 * sand); i++) rect(ctx, x - (9 - i), y - 6 - i * 0.6, (9 - i) * 2, 1, lit);
  if (f % 4 < 2) rect(ctx, x, y - 18, 1, 10, lit);
  rect(ctx, x - 12, y - 31, 24, 2, bronze); rect(ctx, x - 12, y - 6, 24, 2, bronze);
  // clock-face head
  disc(ctx, x, y - 39, 7, bronze); disc(ctx, x, y - 39, 5, "#f3e9d2");
  const a = (f / 20) % (Math.PI * 2);
  rect(ctx, x + Math.round(Math.cos(a) * 3), y - 39 + Math.round(Math.sin(a) * 3), 1, 1, dark);
  rect(ctx, x, y - 39, 1, 1, dark); rect(ctx, x, y - 42, 1, 3, dark);
  // chains
  for (let i = 0; i < 8; i++) { rect(ctx, x - 14 - i, y - 26 + i * 2, 2, 1, "#9a96a8"); rect(ctx, x + 13 + i, y - 26 + i * 2, 2, 1, "#9a96a8"); }
  return 46;
}

function drawReaper(ctx, x, y, f) {
  const hover = Math.round(Math.sin(f / 12) * 2), cloak = "#3a2458", fold = "#6b3fa0", drip = "#4ab0ff";
  const by = y - 4 + hover;
  // robe
  for (let i = 0; i < 26; i++) { const w = 4 + Math.round(i * 0.45); rect(ctx, x - w, by - 30 + i, w * 2, 1, i % 6 === 0 ? fold : cloak); }
  for (let i = 0; i < 5; i++) if ((i + Math.floor(f / 6)) % 2) rect(ctx, x - 14 + i * 6, by - 4, 3, 2, cloak);
  // hood + face void + eyes
  disc(ctx, x, by - 30, 7, fold); disc(ctx, x, by - 30, 6, cloak); disc(ctx, x, by - 29, 4, "#05040c");
  rect(ctx, x - 2, by - 30, 1, 1, drip); rect(ctx, x + 2, by - 30, 1, 1, drip);
  // scythe
  rect(ctx, x + 12, by - 38, 1, 34, "#7a5230");
  for (let i = 0; i < 12; i++) rect(ctx, x + 12 - i, by - 38 + Math.round(i * i / 18), 2, 1, "#c8c0d8");
  // dripping leak
  for (let i = 0; i < 4; i++) { const d = (f + i * 13) % 40; rect(ctx, x - 9 + i * 6, by - 8 + d / 3, 1, 2, drip); }
  return 44;
}

function drawTitan(ctx, x, y, f) {
  const stone = "#5a5668", lit = "#8a86a0", dark = "#1f1d2b", tape = "#c0294a";
  const breathe = f % 40 < 20 ? 0 : 1;
  rect(ctx, x - 10, y - 10, 7, 10, dark); rect(ctx, x + 3, y - 10, 7, 10, dark);
  rect(ctx, x - 16, y - 36 + breathe, 32, 27, dark); rect(ctx, x - 15, y - 35 + breathe, 30, 25, stone);
  rect(ctx, x - 15, y - 35 + breathe, 30, 2, lit);
  // filing-cabinet drawers on the chest
  for (let i = 0; i < 3; i++) { rect(ctx, x - 9, y - 30 + i * 7 + breathe, 18, 5, dark); rect(ctx, x - 2, y - 28 + i * 7 + breathe, 4, 1, "#e8b847"); }
  // red tape across
  for (let i = 0; i < 30; i++) rect(ctx, x - 15 + i, y - 34 + Math.round(i * 0.8) + breathe, 1, 2, tape);
  // head with visor
  rect(ctx, x - 7, y - 46 + breathe, 14, 10, dark); rect(ctx, x - 6, y - 45 + breathe, 12, 8, stone);
  rect(ctx, x - 5, y - 42 + breathe, 10, 2, f % 50 < 4 ? dark : "#ffe066");
  // the giant stamp
  rect(ctx, x - 26, y - 30 + breathe, 9, 4, "#7a5230"); rect(ctx, x - 27, y - 26 + breathe, 11, 3, "#c0294a");
  return 48;
}

function drawGuardian(ctx, x, y, f) {
  const pulse = Math.sin(f / 9), robe = "#2a1a44", gold = "#e8b847", lit = "#ffe08a";
  const hover = Math.round(Math.sin(f / 14) * 2), by = y + hover - 2;
  // wings
  for (let i = 0; i < 14; i++) {
    const w = 18 - i;
    rect(ctx, x - 14 - w, by - 46 + i * 2, w, 2, i % 3 === 0 ? "#6b3fa0" : "#3b2559");
    rect(ctx, x + 14, by - 46 + i * 2, w, 2, i % 3 === 0 ? "#6b3fa0" : "#3b2559");
  }
  // robe
  for (let i = 0; i < 34; i++) { const w = 7 + Math.round(i * 0.35); rect(ctx, x - w, by - 36 + i, w * 2, 1, i % 8 === 0 ? "#3b2559" : robe); }
  rect(ctx, x - 1, by - 36, 2, 34, gold);
  // head: one great eye
  disc(ctx, x, by - 42, 8, robe); ellipse(ctx, x, by - 42, 6, 3, "#f3e9d2");
  disc(ctx, x + Math.round(pulse * 2), by - 42, 2, "#c0294a"); rect(ctx, x + Math.round(pulse * 2), by - 42, 1, 1, "#15122b");
  // crown of false gold, flickering
  for (let i = -3; i <= 3; i++) rect(ctx, x + i * 3 - 1, by - 53 - (i % 2 ? 0 : 2), 2, 4 + (i % 2 ? 0 : 2), (f + i * 7) % 30 < 3 ? lit : gold);
  // orbiting false-discovery sigils
  for (let k = 0; k < 4; k++) {
    const a = f / 25 + k * Math.PI / 2;
    const ox = x + Math.round(Math.cos(a) * 26), oy = by - 28 + Math.round(Math.sin(a) * 8);
    rect(ctx, ox - 1, oy - 1, 3, 3, k % 2 ? "#ff4a8a" : lit); rect(ctx, ox, oy, 1, 1, "#ffffff");
  }
  return 58;
}

const BOSSES = { chimera_overfit: drawChimera, chimera_selection: drawChimera, chronolock: drawChronolock,
                 reaper: drawReaper, titan: drawTitan, guardian: drawGuardian };
// The Knight and the Sentinel are bosses' lieutenants: drawn from maps, at double weight.

function drawEnemy(ctx, kind, x, y, f, head, opts = {}) {
  if (BOSSES[kind]) {
    ctx.save();
    if (opts.alpha != null) ctx.globalAlpha = opts.alpha;
    const h = BOSSES[kind](ctx, x, y, f, head);
    ctx.restore();
    return h;
  }
  const img = enemySprite(kind);
  const bob = kind === "bat" || kind === "wisp" || kind === "phantom" || kind === "wraith"
    ? Math.round(Math.sin(f / 8) * 2) - 4 : (kind === "slime" ? 0 : 0);
  const squash = kind === "slime" && f % 30 < 15;
  if (opts.flash) blit(ctx, flashOf(`enemy:${kind}`, img), x, y + bob, opts);
  else if (squash) { ctx.save(); if (opts.alpha != null) ctx.globalAlpha = opts.alpha;
    ctx.drawImage(img, Math.round(x - 9), Math.round(y - 15 + bob), 18, 15); ctx.restore(); }
  else blit(ctx, img, x, y + bob, opts);
  return 16;
}

if (typeof module !== "undefined") module.exports = { mirror, HEADS, BODY, ENEMY_ART, CLASSES };

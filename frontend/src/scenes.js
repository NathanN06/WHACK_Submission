// Pixel-art backdrops, drawn at 160x90 and scaled up with image-rendering: pixelated.

const PAL = {
  sky: ["#1e1330", "#2b1a44", "#45275e", "#6b3468", "#a8495f", "#e07a5a"],
  star: "#f3e9d2",
  moon: "#f3e9d2",
  stone: "#d9a76a", stoneLit: "#ecc48d", stoneDark: "#9c6640", shade: "#6e3f33",
  hole: "#2a1426", sand: "#c98f55", sandDark: "#a8703f",
  brick: "#7a5a6e", brickLit: "#93718a", mortar: "#4a3350",
  tunnel: "#140b1f", iron: "#3a3446", ironLit: "#6c6680",
  flame: ["#fff2b0", "#f7c548", "#e8692e"],
};

const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

function px(ctx, x, y, w = 1, h = 1, c) { ctx.fillStyle = c; ctx.fillRect(x, y, w, h); }

// Deterministic noise so stars and grit don't jump between redraws.
function rand(seed) { let s = seed; return () => (s = (s * 16807) % 2147483647) / 2147483647; }

function sky(ctx, top, bottom) {
  const bands = PAL.sky, h = (bottom - top) / bands.length;
  bands.forEach((c, i) => {
    const y = Math.round(top + i * h);
    px(ctx, 0, y, 160, Math.ceil(h) + 1, c);
    // dither the seam into the next band
    if (i < bands.length - 1) for (let x = (i % 2); x < 160; x += 2) px(ctx, x, Math.round(top + (i + 1) * h) - 1, 1, 1, bands[i + 1]);
  });
  const r = rand(7);
  for (let i = 0; i < 46; i++) px(ctx, Math.floor(r() * 160), Math.floor(r() * 36), 1, 1, PAL.star);
}

function moon(ctx, cx, cy) {
  for (let y = -5; y <= 5; y++) for (let x = -5; x <= 5; x++)
    if (x * x + y * y <= 26 && (x - 2) * (x - 2) + (y + 1) * (y + 1) > 16) px(ctx, cx + x, cy + y, 1, 1, PAL.moon);
}

function arch(ctx, x, y, w, h, c) {
  px(ctx, x + 1, y, w - 2, 1, c);
  px(ctx, x, y + 1, w, h - 1, c);
}

function colosseum(ctx, ground) {
  const left = 22, right = 138;
  const tiers = [{ h: 9, w: 4, step: 8 }, { h: 8, w: 4, step: 8 }, { h: 7, w: 3, step: 8 }];
  let y = ground;
  tiers.forEach((t, ti) => {
    const top = y - t.h;
    // the top tier is broken away on the right, as ruins are
    const rEdge = ti === 2 ? 112 : right;
    px(ctx, left, top, rEdge - left, t.h, PAL.stone);
    px(ctx, left, top, rEdge - left, 1, PAL.stoneLit);           // cornice catch-light
    px(ctx, left, y - 1, rEdge - left, 1, PAL.stoneDark);        // ledge shadow
    for (let x = left + 3; x + t.w < rEdge - 1; x += t.step) {
      arch(ctx, x, top + 3, t.w, t.h - 4, PAL.hole);
      px(ctx, x + t.w, top + 3, 1, t.h - 4, PAL.stoneDark);      // pillar shading
    }
    if (ti === 2) { // jagged broken edge
      [[112, 0, 3], [115, 2, 2], [117, 4, 3]].forEach(([x, dy, w]) => px(ctx, x, top + dy, w, t.h - dy, PAL.stone));
      px(ctx, 120, top + 7, 18, 1, PAL.stoneDark);
    }
    y = top;
  });
  // right-hand curve of the bowl falling into shadow
  px(ctx, right - 6, ground - 17, 6, 17, PAL.shade);
  for (let i = 0; i < 17; i += 2) px(ctx, right - 7, ground - 17 + i, 1, 1, PAL.shade);
}

function sand(ctx, top) {
  px(ctx, 0, top, 160, 90 - top, PAL.sand);
  const r = rand(3);
  for (let i = 0; i < 120; i++) px(ctx, Math.floor(r() * 160), top + 1 + Math.floor(r() * (89 - top)), 1, 1, PAL.sandDark);
}

function torch(ctx, x, y, frame) {
  px(ctx, x, y, 2, 7, PAL.shade);
  px(ctx, x - 1, y - 1, 4, 1, PAL.stoneDark);
  const f = frame % 3, fl = PAL.flame;
  px(ctx, x - 1, y - 4 + (f === 1 ? 1 : 0), 4, 3, fl[2]);
  px(ctx, x, y - 6 + (f === 2 ? 1 : 0), 2, 4, fl[1]);
  px(ctx, x + (f === 0 ? 0 : 1), y - 7, 1, 2, fl[0]);
}

function drawTitle(ctx, frame) {
  sky(ctx, 0, 76);
  moon(ctx, 136, 12);
  sand(ctx, 76);
  colosseum(ctx, 76);
  torch(ctx, 12, 69, frame);
  torch(ctx, 146, 69, frame + 1);
}

// ---- the gate ----

const GATE = { cx: 80, cy: 40, r: 26, left: 54, right: 106, bottom: 90 };

function inOpening(x, y) {
  if (x < GATE.left || x >= GATE.right) return false;
  if (y >= GATE.cy) return true;
  const dx = x + 0.5 - GATE.cx, dy = y + 0.5 - GATE.cy;
  return dx * dx + dy * dy <= GATE.r * GATE.r;
}

function wall(ctx) {
  px(ctx, 0, 0, 160, 90, PAL.mortar);
  for (let row = 0; row * 5 < 90; row++) {
    const off = row % 2 ? 4 : 0;
    for (let x = -off; x < 160; x += 9) {
      px(ctx, x, row * 5, 8, 4, PAL.brick);
      px(ctx, x, row * 5, 8, 1, PAL.brickLit);
    }
  }
}

function drawGate(ctx, lift, frame) {
  wall(ctx);
  // opening: dark tunnel with a sliver of sand-light at the far end
  for (let y = 0; y < 90; y++) for (let x = GATE.left; x < GATE.right; x++) {
    if (!inOpening(x, y)) continue;
    px(ctx, x, y, 1, 1, PAL.tunnel);
  }
  // voussoirs: a ring of lighter stones around the arch
  for (let a = Math.PI; a <= 2 * Math.PI + 0.01; a += Math.PI / 18) {
    const x = Math.round(GATE.cx + Math.cos(a) * (GATE.r + 2)), y = Math.round(GATE.cy + Math.sin(a) * (GATE.r + 2));
    px(ctx, x - 1, y - 1, 3, 3, PAL.stone);
  }
  px(ctx, GATE.left - 3, GATE.cy, 3, 50, PAL.stone);
  px(ctx, GATE.right, GATE.cy, 3, 50, PAL.stone);
  // portcullis, raised by `lift` pixels, clipped to the opening
  for (let y = 0; y < 90; y++) for (let x = GATE.left; x < GATE.right; x++) {
    if (!inOpening(x, y)) continue;
    const gy = y + lift;
    if (gy >= 90) continue;
    const bar = (x - GATE.left) % 6 < 2, rail = gy % 10 < 2, spike = gy >= 86 && (x - GATE.left) % 6 < 2;
    if (bar || rail || spike) px(ctx, x, y, 1, 1, (x - GATE.left) % 6 === 0 || gy % 10 === 0 ? PAL.ironLit : PAL.iron);
  }
  torch(ctx, 36, 40, frame);
  torch(ctx, 122, 40, frame + 2);
}

// Drives a scene's torch flicker; returns a stop function.
function animate(canvas, draw) {
  const ctx = canvas.getContext("2d");
  let frame = 0, timer = null;
  const tick = () => { draw(ctx, frame++); };
  tick();
  if (!reduceMotion) timer = setInterval(tick, 180);
  return () => clearInterval(timer);
}

// Raises the portcullis in whole-pixel steps, then resolves.
function raiseGate(canvas) {
  const ctx = canvas.getContext("2d");
  if (reduceMotion) { drawGate(ctx, 90, 0); return Promise.resolve(); }
  return new Promise((done) => {
    let lift = 0, frame = 0;
    const step = () => {
      lift += 2;
      drawGate(ctx, lift, frame++ >> 2);
      if (lift >= 90) return setTimeout(done, 220);
      setTimeout(step, 22);
    };
    step();
  });
}

// Drops the portcullis from fully open to shut, speeding up as it falls, with a small bounce.
function lowerGate(canvas) {
  const ctx = canvas.getContext("2d");
  if (reduceMotion) { drawGate(ctx, 0, 0); return Promise.resolve(); }
  return new Promise((done) => {
    let lift = 90, v = 0.5, frame = 0;
    const bounce = [3, 5, 3, 1, 0];
    const fall = () => {
      v += 0.45; lift = Math.max(0, lift - v);
      drawGate(ctx, Math.round(lift), frame++ >> 2);
      if (lift > 0) return setTimeout(fall, 16);
      done();  // it has hit the ground: let the caller shake the screen now
      bounce.forEach((b, i) => setTimeout(() => drawGate(ctx, b, frame >> 2), 40 * (i + 1)));
    };
    fall();
  });
}

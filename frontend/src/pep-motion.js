// Motion helpers for the game screen: easing, a pixel diamond-dissolve wipe, pixel particles and number tweens.
// Purely visual: nothing here reads or changes a ledger number, it only animates what is already on screen.

const ease = {
  out: (t) => 1 - Math.pow(1 - t, 3),
  inOut: (t) => (t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2),
};
const clamp01 = (t) => Math.max(0, Math.min(1, t));

// Frame-rate independent glide of `cur` toward `target` (rate ~ 1/seconds to close most of the gap).
function approach(cur, target, dt, rate = 12) {
  return cur + (target - cur) * (1 - Math.exp(-rate * dt));
}

// The signature move: square cells shrink or grow in diamond order, edges first, centre last.
// p = 0 leaves the area clear, p = 1 covers it completely. Sizes snap to whole pixels.
function drawDissolve(ctx, w, h, p, cell, color) {
  if (p <= 0) return;
  ctx.fillStyle = color;
  if (p >= 1) { ctx.fillRect(0, 0, w, h); return; }
  const cols = Math.ceil(w / cell), rows = Math.ceil(h / cell), cx = cols / 2, cy = rows / 2, far = cx + cy;
  for (let r = 0; r < rows; r++) {
    for (let c = 0; c < cols; c++) {
      const d = (Math.abs(c + 0.5 - cx) + Math.abs(r + 0.5 - cy)) / far;   // 0 at the centre, 1 at a corner
      const t = clamp01(p * 2 - (1 - d));
      if (!t) continue;
      const s = Math.round(cell * t), o = Math.floor((cell - s) / 2);
      ctx.fillRect(c * cell + o, r * cell + o, s, s);
    }
  }
}

// ---------- pixel particles (stage units: 320 x 180) ----------

function burst(list, x, y, n, colors, opts = {}) {
  const { speed = 60, up = 0, gravity = 140, life = 0.6, size = 1 } = opts;
  for (let i = 0; i < n; i++) {
    const a = Math.random() * Math.PI * 2, v = speed * (0.35 + Math.random() * 0.65);
    list.push({ x, y, vx: Math.cos(a) * v, vy: Math.sin(a) * v - up, g: gravity, t: 0,
                life: life * (0.6 + Math.random() * 0.6), c: colors[i % colors.length], s: size });
  }
}

function stepParticles(ctx, list, dt) {
  for (let i = list.length - 1; i >= 0; i--) {
    const p = list[i];
    p.t += dt;
    if (p.t >= p.life) { list.splice(i, 1); continue; }
    p.vy += p.g * dt; p.x += p.vx * dt; p.y += p.vy * dt;
    ctx.globalAlpha = 1 - ease.inOut(p.t / p.life) * 0.9;
    ctx.fillStyle = p.c;
    ctx.fillRect(Math.round(p.x), Math.round(p.y), p.s, p.s);
  }
  ctx.globalAlpha = 1;
}

// ---------- number tweens for HTML text ----------

function tweenNumber(el, to, ms = 450, suffix = "") {
  const from = Number(el.dataset.v ?? to);
  el.dataset.v = to;
  cancelAnimationFrame(el._raf);
  if (from === to || ms <= 0) { el.textContent = `${to}${suffix}`; return; }
  const t0 = performance.now();
  const tick = (now) => {
    const t = clamp01((now - t0) / ms);
    el.textContent = `${Math.round(from + (to - from) * ease.out(t))}${suffix}`;
    if (t < 1) el._raf = requestAnimationFrame(tick);
  };
  el._raf = requestAnimationFrame(tick);
}

// Restart a one-shot CSS animation class on an element.
function pulse(el, cls) {
  if (!el) return;
  el.classList.remove(cls);
  void el.offsetWidth;
  el.classList.add(cls);
  clearTimeout(el[`_${cls}`]);
  el[`_${cls}`] = setTimeout(() => el.classList.remove(cls), 700);
}

// ---------- screen reveal: whenever a screen appears, it opens out of the same diamond dissolve ----------

const Wipe = { canvas: null, ctx: null, raf: 0 };

function revealScreen(ms = 520) {
  if (motionOff()) return;
  if (!Wipe.canvas) {
    Wipe.canvas = document.createElement("canvas");
    Wipe.canvas.className = "screen-wipe";
    Wipe.canvas.setAttribute("aria-hidden", "true");
    document.body.appendChild(Wipe.canvas);
    Wipe.ctx = Wipe.canvas.getContext("2d");
  }
  const c = Wipe.canvas, ctx = Wipe.ctx;
  c.width = Math.ceil(innerWidth / 4); c.height = Math.ceil(innerHeight / 4);   // 4 CSS px per wipe pixel
  c.hidden = false;
  cancelAnimationFrame(Wipe.raf);
  const t0 = performance.now();
  const tick = (now) => {
    const t = clamp01((now - t0) / ms);
    ctx.clearRect(0, 0, c.width, c.height);
    drawDissolve(ctx, c.width, c.height, 1 - ease.inOut(t), 8, "#0d0b1e");
    if (t < 1) Wipe.raf = requestAnimationFrame(tick); else c.hidden = true;
  };
  Wipe.raf = requestAnimationFrame(tick);
}

function motionOff() {
  return document.body.classList.contains("reduced") ||
    (window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches);
}

// Watch every .screen: when one is un-hidden (from any script), it opens out of the dissolve.
function watchScreens() {
  const obs = new MutationObserver((muts) => {
    if (muts.some((m) => m.oldValue !== null && !m.target.hidden)) revealScreen();
  });
  for (const s of document.querySelectorAll(".screen")) obs.observe(s, { attributes: true, attributeFilter: ["hidden"], attributeOldValue: true });
}

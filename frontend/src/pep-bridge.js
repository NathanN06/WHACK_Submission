// The Bridge of Judgment: the hero's self-assessment, the Research Director's choice, the Evolution Trial and the
// Trial of Truth, on a crumbling bridge over the abyss with a golden portal to the Overworld at the far end.
// Everything shown is read from ledger rows (bridge.py); the scene only animates what the Judge decided.

const BR = { phase: "idle", t0: 0, heroX: 30, flash: 0, outcome: null, crossed: false, holdTimer: null, pendingChoice: false,
             kind: null, verdictX: 140, parts: [], fell: {}, entered: false, screamed: false, last: 0 };
const BRIDGE_Y = 112, PORTAL_X = 286, PORTAL_Y = 100;

function showBridge() {
  for (const d of document.querySelectorAll("dialog[open]")) d.close();
  $("screen-game").hidden = true; $("screen-room").hidden = true; $("screen-bridge").hidden = false;
  $("bridge-events").innerHTML = "";
  $("bridge-banner").className = "banner";
  $("bridge-speech").innerHTML = '<p class="muted">The hero steps onto the bridge and opens its notebook…</p>';
  $("bridge-review").innerHTML = "";
  Object.assign(BR, { phase: "arrive", t0: performance.now(), heroX: 6, flash: 0, outcome: null, crossed: false,
                      kind: null, parts: [], fell: {}, entered: false, screamed: false });
  window.scrollTo(0, 0);
}

function bridgeLog(e, cls = "") {
  const li = document.createElement("li");
  li.className = `k-${e.action} ${cls}`;
  li.innerHTML = `${e.hp_delta ? `<b class="${e.hp_delta < 0 ? "neg" : "pos"}">${e.hp_delta > 0 ? "+" : ""}${e.hp_delta}</b> ` : ""}${esc(e.line || e.action)}`;
  li.onclick = () => { G.pinned = e.seq; inspect(e); };
  li.title = "Open in the Test Inspector";
  $("bridge-events").appendChild(li);
  $("bridge-events").scrollTop = $("bridge-events").scrollHeight;
}

function bridgeBanner(title, sub) {
  const b = $("bridge-banner");
  b.innerHTML = `<strong>${esc(title)}</strong>${sub ? `<small>${esc(sub)}</small>` : ""}`;
  b.hidden = false;
  pulse(b, "in");
  clearTimeout(b._t);
  b._t = setTimeout(() => { b.classList.add("out"); setTimeout(() => { b.hidden = true; b.classList.remove("out"); }, 240); },
                    BR.phase === "verdict" ? 4200 : 2600 / G.speed);   // the verdict is read at its own pace
}

function bridgeEvent(e) {
  const r = e.result || {};
  if (e.action === "bridge_enter") { showBridge(); bridgeLog(e); return; }
  if ($("screen-bridge").hidden) return;
  switch (e.action) {
    case "self_assessment": renderAssessment(r.assessment); BR.phase = "review"; break;
    case "bridge_choice":
      bridgeLog(e);
      markChoice(r);
      break;
    case "evolution_start": bridgeLog(e); bridgeBanner("EVOLUTION", "Researcher V1 is preserved"); BR.phase = "evolve"; break;
    case "evolution_transform": bridgeLog(e); BR.flash = performance.now(); bridgeBanner("RESEARCHER V2", "A focused second expedition"); break;
    case "spec_locked":
      bridgeLog(e);
      BR.phase = "trial"; BR.t0 = performance.now();
      bridgeBanner("THE TRIAL OF TRUTH", `Specification locked · ${(r.sha256 || "").slice(0, 12)}`);
      break;
    case "trial_result":
      bridgeLog(e, "trial");
      BR.outcome = r.trial.outcome; BR.crossed = !!r.trial.crossed; BR.phase = "verdict"; BR.t0 = performance.now();
      BR.kind = verdictKind(BR.outcome, BR.crossed); BR.verdictX = BR.heroX;
      $("bridge-banner").className = `banner bridge-verdict v-${BR.kind}`;
      bridgeBanner(r.trial.outcome, r.trial.outcome === "NO NEW INDEPENDENT CONFIRMATION"
        ? "The claim held on a vault already opened: nothing new is confirmed"
        : { win: "The path lights up. The hero crosses into the Overworld",
            honest: "No discovery claimed. The hero carries an honest report across",
            escape: "The bridge breaks behind the hero", fall: "The bridge gives way" }[BR.kind]);
      renderTrial(r.trial);
      if (!G.pinned) inspect(e);
      break;
    case "finale": {
      // open the brief only once the verdict has finished playing
      const wait = BR.kind && !G.reduced ? Math.max(600, verdictLength(BR.kind) - (performance.now() - BR.t0) + 400) : 1200;
      setTimeout(() => { if (G.state.finale && !$("screen-bridge").hidden) { $("screen-bridge").hidden = true; showRoom(); } }, wait);
      break;
    }
    default:
      if (e.level === 5 && e.line && e.action !== "self_assessment") bridgeLog(e);
      if (e.action === "mystery_result" && !G.pinned) inspect(e);
  }
}

// ---------- the review and the choice ----------

const CHOICE_TEXT = {
  cross: "Commit the current research specification to the final test on the sealed vault.",
  evolve: "Authorise a focused second expedition (Researcher V2) to investigate a specific weakness.",
  inconclusive: "Deliver a qualified report without asserting an unsupported discovery.",
};

function renderAssessment(A) {
  const s = G.state, rec = A.recommendation;
  $("bridge-speech").innerHTML = `<div class="speaker"><img src="${portrait("hero")}" alt="" width="48" height="48">
      <div><small>THE HERO SPEAKS${A.version === "V2" ? " · Researcher V2" : ""}</small><p>“${esc(A.speech)}”</p></div></div>
    <p class="rec">Recommendation: <strong>${esc(rec.label)}</strong> <span class="muted">${esc(rec.why)}</span></p>
    <div class="choices">${["cross", "evolve", "inconclusive"].map((k) => {
      const o = A.options[k];
      return `<button class="btn choice ${k === rec.choice ? "gold" : ""}" data-choice="${k}" ${o.enabled ? "" : "disabled"}
        title="${esc(o.reason)}"><span>${esc(o.label)}</span><small>${esc(o.enabled ? CHOICE_TEXT[k] : o.reason)}</small>
        ${k === "evolve" && o.enabled ? `<small>Cost ${o.cost} credits · ${o.plan.length} weakness(es)</small>` : ""}</button>`;
    }).join("")}</div>
    <p class="muted small" id="choice-note">${G.interactive && G.mode === "live" ? "You choose whether to proceed; the hero designs the experiments and the Judge decides. Nobody can override the Judge."
      : "Recorded run: the Director's choice follows in a moment."}</p>`;
  const live = G.interactive && G.mode === "live";
  for (const b of document.querySelectorAll("#bridge-speech [data-choice]")) {
    b.onclick = () => chooseAtBridge(b.dataset.choice);
    if (!live) b.disabled = true;
  }
  // the review: everything the hero looked at before speaking
  const c = A.candidate;
  const fmtN = (v, d = 3) => (v == null ? "—" : Number(v).toFixed(d));
  const scrolls = A.scrolls.map((x) => `<tr class="${x.status !== "active" ? "fallen" : ""}"><td>${esc(x.name)}</td><td>${x.hp}</td><td>${x.credits}</td>
    <td>${x.status !== "active" ? "shattered" : x.eureka ? "beat comparator" : "not better"}</td><td>${fmtN(x.ss_oos, 4)}</td>
    <td>${x.design === "new_user" ? "time-zero" : "immortal time"}</td><td>${x.replicating}/${x.sites}</td>
    <td>${x.failed_tests.map(esc).join(", ") || "—"}</td></tr>`).join("");
  const ws = A.weaknesses.map((w) => `<li class="sev${Math.min(3, w.severity)}">${esc(w.label)} <small>severity ${w.severity}${w.fix ? ` · fix: ${esc(w.fix === "RETEST" ? "re-test" : abilityName(w.fix))}` : " · no fix available here"}${w.source === "director" ? " · raised by you" : ""}</small></li>`).join("");
  const un = A.unresolved.map((m) => `<li><strong>${esc(m.id)}</strong> ${esc(m.boss)}: “${esc(m.text)}” <small>raised in level ${m.raised_level} · ${esc(m.status)}</small></li>`).join("");
  const links = A.causal_links.map((l) => `<li>${esc(l.mystery)} → ${esc(l.effect)}</li>`).join("");
  $("bridge-review").innerHTML = `<header><h3>The research history</h3></header>
    ${c ? `<p><b>Strongest finding:</b> ${esc(c.name)} — “${esc(c.claim)}”. SS<sub>oos</sub> ${fmtN(c.ss_oos, 4)}, paired p ${c.p_dm == null ? "—" : Number(c.p_dm).toPrecision(2)} on the holdout.</p>` : "<p>No claim survives.</p>"}
    <table class="review"><thead><tr><th>Scroll</th><th>HP</th><th>Credits</th><th>Holdout</th><th>SS</th><th>Design</th><th>Sites</th><th>Failed tests</th></tr></thead><tbody>${scrolls}</tbody></table>
    <h4>Weaknesses in the claim it would submit</h4><ul class="weak">${ws || "<li>None found.</li>"}</ul>
    <h4>Unresolved Mystery Encounters</h4><ul>${un || "<li>None.</li>"}</ul>
    ${links ? `<h4>How your challenges shaped this decision</h4><ul>${links}</ul>` : ""}
    <p class="muted small">Leakage risk: ${A.leakage.length ? esc(A.leakage.join(", ")) : "none in the surviving scrolls"} ·
      Independent evidence: ${A.independent_evidence.vault2_patients} patients in the sealed vault (${A.independent_evidence.untouched ? "never opened" : "opened"}) ·
      Policy: evolve if the fixable weaknesses the credits pay for weigh ≥ ${A.policy.evolve_threshold}.</p>`;
  if (s.chat && !$("chat-dlg").open) { /* the console closes at the bridge */ }
  // pause playback until the Director chooses (live), or let the recorded choice play after a beat
  G.hold = true;
  clearTimeout(BR.holdTimer);
  if (!live) BR.holdTimer = setTimeout(() => { G.hold = false; G.nextAt = 0; }, 4500 / G.speed);
}

async function chooseAtBridge(choice) {
  if (BR.pendingChoice) return;
  BR.pendingChoice = true;
  for (const b of document.querySelectorAll("#bridge-speech [data-choice]")) b.disabled = true;
  $("choice-note").textContent = "The hero prepares…";
  try {
    BR.req = BR.req || {};
    BR.req[choice] = BR.req[choice] || newRequestId();
    await directorPost("bridge", { choice, request_id: BR.req[choice] });
    BR.req = {};
    G.hold = false; G.nextAt = 0; setRun(true);
  } catch (err) {
    $("choice-note").textContent = `Not accepted: ${String(err.message || err).slice(0, 200)}`;
    renderAssessment(G.state.assessment);
  } finally {
    BR.pendingChoice = false;
  }
}

function markChoice(r) {
  clearTimeout(BR.holdTimer);
  G.hold = false; G.nextAt = 0;
  for (const b of document.querySelectorAll("#bridge-speech [data-choice]")) {
    b.disabled = true;
    b.classList.toggle("chosen", b.dataset.choice === r.choice);
  }
  const note = $("choice-note");
  if (note) note.textContent = `${r.by === "director" ? "You chose" : "Autopilot chose"} ${r.choice.toUpperCase()}${r.followed_hero ? ", as the hero recommended." : `; the hero had recommended ${r.recommended.toUpperCase()}.`}`;
}

function renderTrial(t) {
  const sk = t.skill || {};
  $("bridge-review").insertAdjacentHTML("afterbegin", `<div class="trial-card o-${t.outcome.replace(/\s/g, "")}">
    <small>THE TRIAL OF TRUTH</small><strong>${esc(t.outcome)}</strong><p>${esc(t.line)}</p>
    ${t.evaluated ? `<p class="muted small">Locked spec ${esc((t.sha256 || "").slice(0, 12))}: ${esc(t.spec.claim)} · stance ${esc(t.spec.stance)} ·
      design ${esc(t.spec.design)}${t.spec.subgroup ? ` · ${esc(t.spec.direction || "")} in ${esc(t.spec.subgroup)}` : ""} · SS<sub>oos</sub> ${sk.ss_oos == null ? "—" : Number(sk.ss_oos).toFixed(4)} on ${sk.matched_pairs ?? "—"} matched pairs,
      paired p ${sk.p_dm == null ? "—" : Number(sk.p_dm).toPrecision(3)}${t.hp_delta ? ` · ${t.hp_delta} HP` : ""}</p>` : ""}
    ${t.confirmation_label ? `<p class="small"><b>${esc(t.confirmation_label)}</b>${t.independent === false
      ? " · this cohort's vault had been opened before, so it cannot confirm anything again" : ""}</p>` : ""}
    ${(t.failures || []).map((f) => `<p class="neg small">${esc(f)}</p>`).join("")}</div>`);
}

// ---------- the scene ----------
// The verdict is choreographed by outcome, always in the same order: the beam of judgment falls on the hero,
// then the bridge answers. VALIDATED DISCOVERY: the runes light a golden path and the portal flares.
// JUSTIFIED UNCERTAINTY: a calm lantern walk into a moonlit portal. INVALID METHODOLOGY / UNJUSTIFIED CONFIDENCE:
// cracks spread, the bridge crumbles and the portal seals (the hero escapes only if the Judge says it crossed).

const MOOD = {
  win: { beam: "255,224,138", rune: "#ffe08a", flood: "#fff3c4", tint: "255,200,90" },
  honest: { beam: "190,220,255", rune: "#cfe6ff", flood: "#dceaff", tint: "120,160,230" },
  fall: { beam: "255,74,90", rune: "#ff4a5a", flood: "#07040e", tint: "200,30,60" },
  escape: { beam: "255,74,90", rune: "#ff8a5a", flood: "#fff3c4", tint: "200,60,40" },
};
// timeline (ms after the verdict): beam, then the walk, the portal and the flood
const TL = {
  win: { walk: 1000, walkDur: 2800, enter: 450, flood: 1300 },
  honest: { walk: 1100, walkDur: 4000, enter: 600, flood: 1500 },
  escape: { walk: 1500, walkDur: 1500, enter: 400, flood: 1100 },
  fall: { crack: 900, drop: 1700, flood: 1400 },
};

function verdictKind(outcome, crossed) {
  if (outcome === "VALIDATED DISCOVERY") return "win";
  if (outcome === "JUSTIFIED UNCERTAINTY" || outcome === "NO NEW INDEPENDENT CONFIRMATION") return "honest";
  return crossed ? "escape" : "fall";
}

// How long the verdict takes to play, so the brief opens only once it has finished.
function verdictLength(kind) {
  const t = TL[kind];
  return kind === "fall" ? t.drop + 1800 + t.flood : t.walk + t.walkDur + t.enter + t.flood;
}

function bridgeLoop() {
  const ctx = crispContext($("bridge-canvas"));
  const frame = (now) => {
    if (!$("screen-bridge").hidden) {
      step(now);
      drawBridge(ctx, now, G.reduced ? 0 : G.f);
      G.f++;
    }
    requestAnimationFrame(frame);
  };
  requestAnimationFrame(frame);
}

function drawBridge(ctx, now, f) {
  const dt = Math.min(0.05, BR.last ? (now - BR.last) / 1000 : 0.016);
  BR.last = now;
  const V = BR.phase === "verdict" ? (G.reduced ? 1e6 : now - BR.t0) : -1;
  const kind = BR.kind, M = kind ? MOOD[kind] : null, T = kind ? TL[kind] : null;
  const breaking = V >= 0 && (kind === "fall" || kind === "escape");
  ctx.save();
  ctx.clearRect(0, 0, 320, 180);
  if (breaking && V > 900 && V < 2600 && !G.reduced) {   // the bridge breaking shakes the world
    const k = 1 - (V - 900) / 1700;
    ctx.translate(Math.round(Math.sin(V / 24) * 3 * k), Math.round(Math.cos(V / 33) * 2 * k));
  }
  // the abyss: deep violet bands
  const bands = ["#120a22", "#160c2a", "#1a0e32", "#1f1038", "#24123e", "#1c0e30", "#140a24", "#0c0616", "#07040e"];
  bands.forEach((c, i) => rect(ctx, -4, i * 20, 328, 20, c));
  for (let k = 0; k < 30; k++) rect(ctx, (k * 53) % 320, (k * 29) % 70, 1, 1, k % 3 ? "#5a4a8a" : "#9a8ad0");
  // distant ruined castles
  const ruin = "#22183a";
  for (const [x0, h] of [[4, 46], [20, 62], [34, 40], [210, 54], [228, 70], [246, 44]]) {
    rect(ctx, x0, 82 - h, 14, h, ruin);
    for (let b = 0; b < 3; b++) rect(ctx, x0 + b * 5, 78 - h, 3, 4, ruin);
    if ((x0 + Math.floor(f / 40)) % 3 === 0) rect(ctx, x0 + 5, 90 - h, 2, 3, "#3f7fbf");
  }
  rect(ctx, -4, 80, 328, 4, "#1a1230");
  // drifting fog in the abyss (it rises for an honest ending)
  const fogUp = kind === "honest" && V > 0 ? Math.min(18, V / 220) : 0;
  for (let k = 0; k < 8; k++) {
    const fx = ((k * 61 + f * 0.25 * (k % 2 ? 1 : -1)) % 380) - 30;
    ellipse(ctx, fx, 140 + (k % 3) * 12 - fogUp, 26, 4, k % 2 ? "#2a1a48" : "#22143c");
  }
  // floating stone fragments
  for (let k = 0; k < 7; k++) {
    const x = 18 + k * 44, y = 60 + (k % 3) * 34 + Math.round(Math.sin(f / 30 + k) * 3);
    rect(ctx, x, y, 8 + (k % 3) * 3, 4, "#3a3050"); rect(ctx, x + 1, y, 6 + (k % 3) * 3, 1, "#5a5078"); rect(ctx, x + 2, y + 4, 4, 2, "#2a2240");
  }
  // the mood washes over the sky once the Judge has spoken
  if (M && V > 300) {
    const a = Math.min(1, (V - 300) / 1400) * (kind === "fall" ? 0.22 + 0.06 * Math.sin(V / 160) : 0.16);
    ctx.fillStyle = `rgba(${M.tint},${a})`; ctx.fillRect(-4, -4, 328, 92);
  }
  drawPortal(ctx, f, V, kind);
  drawDeck(ctx, now, f, V, kind, M);
  drawBridgeHero(ctx, now, f, V, kind, T);
  stepParticles(ctx, BR.parts, dt);
  // the beam of judgment
  if (M && V >= 0 && V < 1100) {
    const t = V / 1100, w = Math.round(2 + Math.sin(Math.PI * t) * 12), x = Math.round(BR.heroX);
    ctx.fillStyle = `rgba(${M.beam},${0.25 * Math.sin(Math.PI * t)})`; ctx.fillRect(x - w * 2, 0, w * 4, BRIDGE_Y);
    ctx.fillStyle = `rgba(${M.beam},${0.75 * Math.sin(Math.PI * t)})`; ctx.fillRect(x - Math.floor(w / 2), 0, w, BRIDGE_Y);
    if (V < 120 && !G.reduced) { ctx.fillStyle = `rgba(${M.beam},0.35)`; ctx.fillRect(-4, -4, 328, 188); }
  }
  // the evolution flash
  if (BR.flash && now - BR.flash < 1800 && !G.reduced) {
    const t = (now - BR.flash) / 1800;
    for (let k = 0; k < 3; k++) {
      const r = Math.round((t * 60 + k * 14) % 70);
      ctx.save(); ctx.globalAlpha = 1 - t; ctx.strokeStyle = k % 2 ? "#7fe0ff" : "#ffffff"; ctx.lineWidth = 2;
      ctx.beginPath(); ctx.ellipse(Math.round(BR.heroX), BRIDGE_Y - 14, r, r * 0.6, 0, 0, Math.PI * 2); ctx.stroke(); ctx.restore();
    }
    ctx.save(); ctx.globalAlpha = Math.max(0, 0.6 - t); ctx.fillStyle = "#ffffff"; ctx.fillRect(0, 0, 320, 180); ctx.restore();
  }
  ctx.restore();
  // the ending floods the screen: light through the portal, or the dark of the abyss
  if (M && V >= 0) {
    const start = kind === "fall" ? T.drop + 1800 : T.walk + T.walkDur + T.enter;
    const k = clamp01((V - start) / T.flood);
    if (k > 0) drawDissolve(ctx, 320, 180, ease.inOut(k), 10, M.flood);
  }
}

function drawPortal(ctx, f, V, kind) {
  // win: it flares; honest: it cools to moonlight; fall/escape: it seals (after the hero, if it escapes)
  let scale = 1, flare = 0;
  if (kind === "win" && V > 600) flare = Math.min(1, (V - 600) / 900);
  if (kind === "fall" && V > 700) scale = 1 - ease.inOut(clamp01((V - 700) / 1600));
  if (kind === "escape") { const sealAt = TL.escape.walk + TL.escape.walkDur + TL.escape.enter; if (V > sealAt) scale = 1 - ease.inOut(clamp01((V - sealAt) / 700)); }
  const rx = 22 * scale, ry = 36 * scale;
  if (scale > 0.02) {
    ctx.save();
    ctx.beginPath(); ctx.ellipse(PORTAL_X, PORTAL_Y, rx, ry, 0, 0, Math.PI * 2); ctx.clip();
    rect(ctx, PORTAL_X - 22, PORTAL_Y - 36, 44, 40, "#9ccaf2"); rect(ctx, PORTAL_X - 22, PORTAL_Y - 8, 44, 10, "#c4e0f6");
    disc(ctx, PORTAL_X + 8, PORTAL_Y - 24, 4, "#ffe08a");
    ellipse(ctx, PORTAL_X - 8, PORTAL_Y + 4, 20, 8, "#5fbf6a"); ellipse(ctx, PORTAL_X + 12, PORTAL_Y + 8, 18, 8, "#4fae5a");
    rect(ctx, PORTAL_X - 22, PORTAL_Y + 10, 44, 30, "#3c8a46");
    for (const tx of [-12, -2, 10]) { rect(ctx, PORTAL_X + tx, PORTAL_Y + 2, 2, 5, "#6a4a2a"); disc(ctx, PORTAL_X + tx + 1, PORTAL_Y, 3, "#2f7a3a"); }
    if (kind === "honest" && V > 500) { ctx.fillStyle = `rgba(30,40,90,${Math.min(0.55, (V - 500) / 2000)})`; ctx.fillRect(PORTAL_X - 22, PORTAL_Y - 36, 44, 72); }
    ctx.restore();
  }
  const gold = kind === "honest" && V > 500 ? "190,220,255" : "255,224,138";
  aura(ctx, PORTAL_X, PORTAL_Y, 46 * Math.max(scale, 0.01) + flare * 30, gold, (0.28 + 0.06 * Math.sin(f / 14)) * Math.max(scale, 0.01) + flare * 0.25);
  const ring = kind === "fall" && V > 700 ? "#6a6880" : kind === "honest" && V > 500 ? "#cfe6ff" : "#e8b847";
  ctx.save(); ctx.strokeStyle = ring; ctx.lineWidth = 4;
  ctx.beginPath(); ctx.ellipse(PORTAL_X, PORTAL_Y, Math.max(0.5, 24 * scale), Math.max(0.5, 38 * scale), 0, 0, Math.PI * 2); ctx.stroke();
  if (scale > 0.02) { ctx.strokeStyle = "#ffe08a"; ctx.lineWidth = 1; ctx.beginPath(); ctx.ellipse(PORTAL_X, PORTAL_Y, 26 * scale + flare * 3, 40 * scale + flare * 4, 0, 0, Math.PI * 2); ctx.stroke(); }
  ctx.restore();
  const n = 8 + Math.round(flare * 10);
  for (let k = 0; k < n * scale; k++) {
    const a = f / (40 - flare * 20) + k * Math.PI * 2 / n;
    rect(ctx, PORTAL_X + Math.round(Math.cos(a) * (30 + flare * 6) * scale), PORTAL_Y + Math.round(Math.sin(a) * (44 + flare * 6) * scale), 2, 2, k % 2 ? "#ffe08a" : "#e8b847");
  }
  if (kind === "fall" && V > 2200 && V < 2500 && !G.reduced) { ctx.fillStyle = "rgba(255,255,255,0.5)"; ctx.fillRect(PORTAL_X - 3, PORTAL_Y - 3, 6, 6); }
}

// The deck: stone blocks with runes. Runes light up in a wave toward the portal on a good verdict;
// on a bad one cracks run out from under the hero and the middle span falls away, block by block.
function drawDeck(ctx, now, f, V, kind, M) {
  const breaking = V >= 0 && (kind === "fall" || kind === "escape");
  const crackT = breaking ? clamp01((V - 700) / 900) : 0;
  const wave = V >= 0 && (kind === "win" || kind === "honest") ? BR.verdictX + Math.max(0, V - 700) * (kind === "win" ? 0.16 : 0.09) : -1;
  for (let x = 4; x < PORTAL_X - 16; x += 8) {
    const span = kind === "fall" ? x > 110 && x < 230 : x > 150 && x < 200;
    let dy = 0, rot = 0;
    if (breaking && span) {
      const delay = Math.abs(x - 170) * 6, t = Math.max(0, V - 1500 - delay) / 1000;
      dy = Math.round(t * t * 160); rot = t * ((x / 8) % 2 ? 1.6 : -1.3);
      if (t > 0 && !BR.fell[x] && !G.reduced) {
        BR.fell[x] = true;
        burst(BR.parts, x + 4, BRIDGE_Y + 4, 8, ["#6e6488", "#8a80a6", "#3a3050"], { speed: 40, up: 10, gravity: 160, life: 0.9 });
      }
    }
    if (dy > 90) continue;
    ctx.save(); ctx.translate(x + 4, BRIDGE_Y + 5 + dy); ctx.rotate(rot);
    rect(ctx, -4, -5, 8, 10, "#4a4060"); rect(ctx, -3, -4, 6, 8, (x / 8) % 2 ? "#6e6488" : "#625a7c"); rect(ctx, -3, -4, 6, 1, "#8a80a6");
    if ((x / 8) % 5 === 2) {
      const lit = wave >= 0 && x <= wave;
      const c = lit ? M.rune : breaking && V > 400 ? `rgba(255,74,90,${0.5 + 0.4 * Math.sin(f / 4 + x)})` : `rgba(127,224,255,${0.45 + 0.4 * Math.sin(f / 10 + x)})`;
      rect(ctx, -1, -1, 2, 3, c);   // runes
      if (lit) aura(ctx, 0, 0, 7, kind === "win" ? "255,224,138" : "190,220,255", 0.5);
    }
    if ((x / 8) % 7 === 3) rect(ctx, -2, 3, 3, 1, "#2a2240");  // old cracks
    if (breaking && crackT > 0 && Math.abs(x - 170) < 70 * crackT) {   // fractures run out from the middle
      const a = ((x * 5) % 5) - 2, flip = (x / 8) % 2 ? 1 : -1;
      for (const [dx, dy] of [[0, -5], [1, -4], [0, -3], [1, -2], [2, -1], [1, 0], [2, 1]]) rect(ctx, a + dx * flip, dy, 1, 1, "#140a20");
      if (V > 1100) rect(ctx, a + flip, -2, 1, 1, `rgba(255,74,90,${0.5 + 0.5 * Math.sin(f / 3 + x)})`);   // glowing from inside
    }
    ctx.restore();
  }
  // pillars with blue flames (they turn the colour of the verdict)
  for (const px of [24, 96, 168, 240]) {
    rect(ctx, px, BRIDGE_Y - 14, 4, 14, "#3a3050"); rect(ctx, px - 1, BRIDGE_Y - 16, 6, 2, "#5a5078");
    const fl = f % 12 < 6, red = breaking && V > 400, warm = kind === "win" && wave > px;
    const c1 = red ? (fl ? "#ff4a5a" : "#d8304a") : warm ? (fl ? "#ffd04a" : "#e8a830") : fl ? "#3fa0ff" : "#2f7fdf";
    const c2 = red ? "#ffb0b8" : warm ? "#fff3c4" : fl ? "#9fe0ff" : "#7fc0ff";
    rect(ctx, px, BRIDGE_Y - 21, 4, 5, c1); rect(ctx, px + 1, BRIDGE_Y - 24, 2, 3, c2);
    aura(ctx, px + 2, BRIDGE_Y - 20, 14, red ? "255,74,90" : warm ? "255,208,74" : "63,160,255", 0.25);
  }
}

function drawBridgeHero(ctx, now, f, V, kind, T) {
  const img = pepSprite("Alchemist");
  let x = BR.heroX, y = BRIDGE_Y, rot = 0, scale = 2, alpha = 1, walking = false;
  if (V < 0) {   // before the verdict: walk to the review spot, then to the middle for the trial
    const target = BR.phase === "trial" ? 140 : 34;
    walking = Math.abs(x - target) > 0.5;
    if (walking) x += Math.sign(target - x) * Math.min(G.reduced ? 99 : 0.9, Math.abs(target - x));
  } else if (kind === "fall") {
    // it steps out over the middle span, still confident, just before the span gives way
    const w = clamp01((V - 300) / (TL.fall.drop - 500));
    walking = w > 0 && w < 1;
    x = BR.verdictX + (172 - BR.verdictX) * ease.inOut(w);
    const t = Math.max(0, V - TL.fall.drop) / 1800;
    if (t > 0) { y += Math.round(t * t * 140); rot = t * 2.4; }
    if (t > 0 && !BR.screamed && !G.reduced) { BR.screamed = true; burst(BR.parts, x, y - 10, 10, ["#ff4a5a", "#ffffff"], { speed: 50, life: 0.5 }); }
    if (y > 200) alpha = 0;
  } else {
    const t = clamp01((V - T.walk) / T.walkDur), e = kind === "escape" ? ease.out(t) : ease.inOut(t);
    walking = t > 0 && t < 1;
    x = BR.verdictX + (PORTAL_X - BR.verdictX) * e;
    if (kind === "escape" && walking && !G.reduced) y -= Math.round(Math.abs(Math.sin(t * Math.PI * 5)) * 6);   // leaping the gaps
    const k = clamp01((V - T.walk - T.walkDur) / T.enter);   // stepping into the portal
    if (k > 0) {
      scale = 2 * (1 - ease.inOut(k)); alpha = 1 - k;
      if (!BR.entered && !G.reduced) {
        BR.entered = true;
        burst(BR.parts, PORTAL_X, PORTAL_Y + 4, kind === "win" ? 46 : 22, kind === "win" ? ["#ffe08a", "#fff3c4", "#e8b847"] : ["#cfe6ff", "#ffffff"], { speed: 70, up: 20, gravity: 30, life: 1.2 });
      }
    }
    if (kind === "win" && walking && f % 3 === 0 && !G.reduced) burst(BR.parts, x - 6, y - 4, 1, ["#ffe08a", "#fff3c4"], { speed: 8, up: 14, gravity: -10, life: 0.8 });
  }
  BR.heroX = x;
  if (alpha <= 0 || scale <= 0.05) return;
  const bob = walking && !G.reduced ? (Math.floor(f / (kind === "honest" ? 9 : 5)) % 2) : 0;
  if (G.state.version === "V2") aura(ctx, x, y - 14, 18, "127,224,255", 0.45);
  if (kind === "honest" && V > 600) {   // the lantern of an honest report
    aura(ctx, x + 9, y - 14, 30, "255,214,140", 0.4 + 0.05 * Math.sin(f / 8));
    rect(ctx, x + 8, y - 22 - bob, 1, 4, "#3a3050"); rect(ctx, x + 6, y - 18 - bob, 5, 5, "#ffd68c"); rect(ctx, x + 7, y - 17 - bob, 3, 3, "#fff6d0");
  }
  ctx.save(); ctx.globalAlpha = alpha; ctx.translate(Math.round(x), y - bob); ctx.scale(scale, scale);
  if (rot) ctx.rotate(rot);
  blit(ctx, img, 0, 0); ctx.restore();
  if (G.state.version === "V2" && scale >= 2) pixelText(ctx, "V2", x, y - img.height * 2 - 10, "#7fe0ff");
}

// ---------- the Overworld report (appended to the Research Brief) ----------

function renderOverworld(f) {
  const o = f.overworld;
  if (!o) return;
  const t = o.trial || {}, c = o.conclusion, j = o.journey, u = o.contributions, ev = o.evolution, L = o.ledger;
  const hpRows = Object.entries(j.hp_by_level).map(([id, by]) => {
    const name = (G.state.agents[id] && G.state.agents[id].name) || id;
    return `<tr><td>${esc(name)}</td>${[1, 2, 3, 4].map((l) => `<td>${by[l] ?? "—"}</td>`).join("")}<td>${j.final_hp[id]}</td></tr>`;
  }).join("");
  const list = (xs, fn) => (xs && xs.length ? `<ul>${xs.map(fn).join("")}</ul>` : '<p class="muted">None.</p>');
  const html = `<section class="overworld">
    <div class="ow-verdict o-${(t.outcome || "").replace(/\s/g, "")}"><small>THE TRIAL OF TRUTH</small><strong>${esc(t.outcome || "No trial")}</strong>
      <p>${esc(c.text)}</p></div>
    <h3>Final scientific conclusion</h3>
    <ul><li><b>Strongest claim:</b> ${c.strongest ? `${esc(c.strongest.scroll)} — “${esc(c.strongest.claim)}”` : "none"}</li>
      <li><b>Evidence:</b> ${c.evidence && c.evidence.ss_oos != null ? `SS<sub>oos</sub> ${Number(c.evidence.ss_oos).toFixed(4)} on ${c.evidence.matched_pairs} matched pairs of the sealed vault, paired p ${Number(c.evidence.p_dm).toPrecision(3)}` : "not evaluated"}</li>
      <li><b>Remaining uncertainty:</b> ${esc(c.uncertainty)}</li>
      <li><b>Independent validation:</b> ${c.validated ? "succeeded" : "did not establish a discovery"}</li></ul>
    <h3>Research journey</h3>
    <table><thead><tr><th>Scroll</th><th>I</th><th>II</th><th>III</th><th>IV</th><th>Final</th></tr></thead><tbody>${hpRows}</tbody></table>
    <p>Research credits used: <b>${j.credits_used}</b> · Tests executed: <b>${j.tests_executed}</b> · Bosses: ${esc(j.bosses.join(", "))}</p>
    ${j.weaknesses.length ? `<p>Methodological weaknesses reviewed at the bridge: ${esc(j.weaknesses.join("; "))}</p>` : ""}
    <h3>Your contributions as Research Director</h3>
    <h4>Evidence submitted</h4>${list(u.evidence, (x) => `<li><b>${esc(x.id)}</b> ${esc(x.classification)} · ${esc(x.url || x.filename || "statement")}: “${esc((x.claim || "").slice(0, 140))}”${x.missing && x.missing.length ? ` <small class="muted">missing: ${esc(x.missing.join("; "))}</small>` : ""}</li>`)}
    <h4>Mystery Bosses summoned</h4>${list(u.summoned, (m) => `<li><b>${esc(m.id)}</b> ${esc(m.boss)}: ${esc(m.status)}${m.hp_delta ? ` (${m.hp_delta > 0 ? "+" : ""}${m.hp_delta} HP)` : ""} · “${esc(m.text)}” <small>${esc(m.resolved_by || "")}</small></li>`)}
    <h4>Secret levels</h4>${list(u.secret_levels, (sl) => `<li>${esc(sl.name)} (${esc(sl.id)}): ${esc(sl.outcome || "")}</li>`)}
    <h4>Still unresolved</h4>${list(u.unresolved, (m) => `<li><b>${esc(m.id)}</b> “${esc(m.text)}” ${m.reason ? `<small class="muted">${esc(m.reason)}</small>` : ""}</li>`)}
    <h4>Questions that changed the research</h4>${list(u.changed_research, (m) => `<li><b>${esc(m.id)}</b> ${esc(m.how)}: “${esc(m.text)}”</li>`)}
    <h3>Evolution history</h3>
    ${ev.occurred ? `<p>The hero evolved to investigate: ${esc(ev.why.join("; ") || "its open weaknesses")}.</p>
      <table><thead><tr><th></th><th>Design</th><th>Adjusted</th><th>K</th><th>Holdout SS</th><th>Sites replicating</th><th>HP</th></tr></thead><tbody>
      ${[["V1", ev.v1], ["V2", ev.v2]].map(([k, v]) => v ? `<tr><td>${k}</td><td>${esc(v.design)}</td><td>${v.adjusted ? "yes" : "no"}</td><td>${v.K}</td>
        <td>${v.ss_oos == null ? "—" : Number(v.ss_oos).toFixed(4)}</td><td>${v.replicating}/${v.sites}</td><td>${v.hp}</td></tr>` : "").join("")}</tbody></table>
      <p class="muted small">V2's holdout figure is exploratory (V1 had already seen the holdout); only the sealed vault validated the final claim.</p>`
      : "<p>The hero did not evolve.</p>"}
    <details><summary>Evidence Ledger: specification, provenance and decisions</summary>
      <p><b>Data version:</b> ${esc(L.data_version)}</p>
      ${L.spec ? `<p><b>Locked specification</b> (sha256 ${esc((L.spec_sha256 || "").slice(0, 16))}…)</p><pre>${esc(JSON.stringify(L.spec, null, 2))}</pre>` : ""}
      <p><b>Original hypotheses:</b></p><ul>${L.hypotheses.map((h) => `<li>${esc(h.claim)} <small class="muted">from ${esc(h.origin)}</small></li>`).join("")}</ul>
      <p><b>Bridge decisions:</b> ${L.decisions.map((d) => `${esc(d.choice)} (by ${esc(d.by)}; hero recommended ${esc(d.recommended)})`).join(" → ")}</p>
    </details></section>`;
  $("brief").insertAdjacentHTML("afterbegin", html);
}

// The Overworld: the last scene, drawn in the room above the brief. Its mood follows the Trial of Truth:
// a bright day and a walk home to fireworks for a validated discovery; a dusk walk with a lantern for an honest,
// qualified report; night over a sealed portal if the claim fell.
const OW = { key: null, t0: 0, parts: [], last: 0, nextFw: 0 };

function drawOverworld(ctx, f, s) {
  const now = performance.now();
  if (OW.key !== s.finale) Object.assign(OW, { key: s.finale, t0: now, parts: [], nextFw: now + 2600 });
  const dt = Math.min(0.05, OW.last ? (now - OW.last) / 1000 : 0.016);
  OW.last = now;
  const t = G.reduced ? 1e6 : now - OW.t0;
  const o = s.finale.overworld || {}, outcome = (o.trial || {}).outcome;
  const kind = !o.crossed ? "night" : outcome === "VALIDATED DISCOVERY" ? "day" : "dusk";
  const P = {
    day: { sky: ["#9ccaf2", "#a8d2f4", "#b6daf6", "#c4e0f6"], sun: ["#ffe08a", "#fff6d0"], hill1: "#5fbf6a", hill2: "#4fae5a", grass: "#3c8a46", tree: ["#2f7a3a", "#3f8f45"], road: ["#d8c8a0", "#e8dcb8"], wall: "#e6eff6", roof: "#c0294a" },
    dusk: { sky: ["#3b2559", "#6b3f7a", "#b0587a", "#e88a6a"], sun: ["#ff9a5a", "#ffd08a"], hill1: "#4a5a6a", hill2: "#3e4c5e", grass: "#2e3c4a", tree: ["#22303e", "#283646"], road: ["#8a7a8a", "#9a8a98"], wall: "#b8b4c8", roof: "#7a2a4a" },
    night: { sky: ["#07040e", "#0c0818", "#120c22", "#18102a"], sun: ["#cfd6e8", "#eef2ff"], hill1: "#141a2a", hill2: "#10162a", grass: "#0c1220", tree: ["#0a0e1a", "#0e1424"], road: ["#2a2a3a", "#323244"], wall: "#2a2e40", roof: "#2a1a2a" },
  }[kind];
  P.sky.forEach((c, i) => rect(ctx, 0, i * 28, 320, 28, c));
  rect(ctx, 0, 112, 320, 8, P.sky[3]);
  if (kind !== "day") for (let k = 0; k < (kind === "night" ? 50 : 18); k++) {
    const tw = (k + Math.floor(f / 20)) % 7 ? 1 : 0.4;
    ctx.globalAlpha = tw; rect(ctx, (k * 61) % 320, (k * 37) % (kind === "night" ? 100 : 50), 1, 1, "#e8e6f2"); ctx.globalAlpha = 1;
  }
  // the sun (or the setting sun, or the moon)
  const sunY = kind === "dusk" ? 92 + Math.min(10, t / 1500) : 30;
  disc(ctx, 262, sunY, 12, P.sun[0]); disc(ctx, 262, sunY, 9, P.sun[1]);
  if (kind === "night") disc(ctx, 266, 27, 9, P.sky[0]);   // a crescent
  if (kind === "day") for (let k = 0; k < 4; k++) { const cx = (k * 90 + f * 0.15) % 360 - 20; ellipse(ctx, cx, 22 + k * 9, 14, 4, "#ffffff"); }
  ellipse(ctx, 70, 120, 120, 30, P.hill1); ellipse(ctx, 250, 124, 130, 32, P.hill2);
  rect(ctx, 0, 124, 320, 56, P.grass);
  for (let k = 0; k < 12; k++) { const tx = 12 + k * 27, ty = 112 + (k % 3) * 6; rect(ctx, tx, ty, 3, 8, kind === "day" ? "#6a4a2a" : "#2a1e1a"); disc(ctx, tx + 1, ty - 3, 6, P.tree[k % 2]); }
  rect(ctx, 150, 130, 20, 50, P.road[0]); rect(ctx, 152, 130, 16, 50, P.road[1]);   // the road home
  rect(ctx, 136, 96, 48, 30, P.wall); rect(ctx, 132, 92, 56, 6, P.roof); rect(ctx, 154, 110, 10, 16, "#7a5230");   // the academy
  if (kind !== "night") {   // its windows are lit; on a discovery a gold flag climbs the pole
    const lit = kind === "dusk" ? "#ffd68c" : "#9ccaf2";
    rect(ctx, 140, 102, 8, 7, lit); rect(ctx, 172, 102, 8, 7, lit);
    if (kind === "dusk") { aura(ctx, 144, 105, 12, "255,214,140", 0.35); aura(ctx, 176, 105, 12, "255,214,140", 0.35); }
  }
  if (kind === "day") {
    rect(ctx, 186, 66, 2, 30, "#5a4a3a");
    const fy = Math.round(68 + 18 * (1 - ease.out(clamp01((t - 3600) / 1400))));
    const wv = Math.floor(f / 8) % 2;
    rect(ctx, 188, fy, 12, 7, "#e8b847"); rect(ctx, 200, fy + 1 + wv, 3, 5, "#e8b847"); rect(ctx, 190, fy + 2, 4, 3, "#fff3c4");
  }
  if (kind === "night") {   // the sealed portal, a grey ring in the dark where the road should begin
    ctx.save(); ctx.strokeStyle = "#3a3848"; ctx.lineWidth = 2; ctx.beginPath(); ctx.ellipse(160, 160, 10, 16, 0, 0, Math.PI * 2); ctx.stroke(); ctx.restore();
  } else {
    // the hero walks up the road from the portal at its foot to the academy door
    const walk = clamp01((t - 300) / (kind === "day" ? 3200 : 4600)), e = ease.inOut(walk);
    const portalA = 1 - clamp01((t - 2200) / 900);
    if (portalA > 0) {
      ctx.save(); ctx.globalAlpha = portalA; ctx.strokeStyle = kind === "day" ? "#e8b847" : "#cfe6ff"; ctx.lineWidth = 2;
      ctx.beginPath(); ctx.ellipse(160, 168, 12 * portalA + 2, 18 * portalA + 2, 0, 0, Math.PI * 2); ctx.stroke(); ctx.restore();
      aura(ctx, 160, 168, 26, kind === "day" ? "255,224,138" : "190,220,255", 0.4 * portalA);
    }
    const hx = 160, hy = Math.round(176 - e * 48), sc = 2 - e * 0.8;
    const bob = walk > 0 && walk < 1 && !G.reduced ? Math.floor(f / 7) % 2 : 0;
    if (kind === "dusk") {
      aura(ctx, hx + 7, hy - 12, 26, "255,214,140", 0.45);
      rect(ctx, hx + 6, hy - 16 - bob, 4, 4, "#ffd68c"); rect(ctx, hx + 7, hy - 15 - bob, 2, 2, "#fff6d0");
    }
    const img = pepSprite("Alchemist");
    ctx.save(); ctx.translate(hx, hy - bob); ctx.scale(sc, sc); blit(ctx, img, 0, 0); ctx.restore();
    if (s.version === "V2") pixelText(ctx, "V2", hx, hy - img.height * sc - 8, kind === "day" ? "#1f8a8a" : "#7fe0ff");
  }
  // fireworks for a discovery, fireflies at dusk
  if (!G.reduced) {
    if (kind === "day" && t > 3600 && now > OW.nextFw && t < 16000) {
      OW.nextFw = now + 700 + Math.random() * 600;
      const fx = 70 + Math.random() * 180, fy = 24 + Math.random() * 36;
      const col = [["#ffe08a", "#fff6d0"], ["#ff8ad8", "#ffd1f0"], ["#7fe0ff", "#d8f6ff"], ["#5fd67a", "#c8ffd4"]][Math.floor(Math.random() * 4)];
      burst(OW.parts, fx, fy, 34, col, { speed: 55, gravity: 40, life: 1.3 });
    }
    if (kind === "dusk" && f % 18 === 0 && OW.parts.length < 24) {
      burst(OW.parts, 20 + Math.random() * 280, 120 + Math.random() * 50, 1, ["#e8f070", "#c8e050"], { speed: 6, up: 6, gravity: -2, life: 3 });
    }
  }
  stepParticles(ctx, OW.parts, dt);
  if (kind === "night") { ctx.fillStyle = "rgba(7,4,14,0.25)"; ctx.fillRect(0, 0, 320, 180); }
}

bridgeLoop();

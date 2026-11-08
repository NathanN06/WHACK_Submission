// The Bridge of Judgment: the hero's self-assessment, the Research Director's choice, the Evolution Trial and the
// Trial of Truth, on a crumbling bridge over the abyss with a golden portal to the Overworld at the far end.
// Everything shown is read from ledger rows (bridge.py); the scene only animates what the Judge decided.

const BR = { phase: "idle", t0: 0, heroX: 30, flash: 0, outcome: null, crossed: false, holdTimer: null, pendingChoice: false };
const BRIDGE_Y = 112, PORTAL_X = 286, PORTAL_Y = 100;

function showBridge() {
  for (const d of document.querySelectorAll("dialog[open]")) d.close();
  $("screen-game").hidden = true; $("screen-room").hidden = true; $("screen-bridge").hidden = false;
  $("bridge-events").innerHTML = "";
  $("bridge-speech").innerHTML = '<p class="muted">The hero steps onto the bridge and opens its notebook…</p>';
  $("bridge-review").innerHTML = "";
  Object.assign(BR, { phase: "arrive", t0: performance.now(), heroX: 6, flash: 0, outcome: null, crossed: false });
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
  clearTimeout(b._t);
  b._t = setTimeout(() => { b.hidden = true; }, 2600 / G.speed);
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
      bridgeBanner(r.trial.outcome, r.trial.crossed ? "The hero crosses" : "The bridge gives way");
      renderTrial(r.trial);
      if (!G.pinned) inspect(e);
      break;
    case "finale":
      setTimeout(() => { if (G.state.finale && !$("screen-bridge").hidden) { $("screen-bridge").hidden = true; showRoom(); } },
                 (BR.crossed ? 5200 : 4200) / G.speed);
      break;
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
      design ${esc(t.spec.design)} · SS<sub>oos</sub> ${sk.ss_oos == null ? "—" : Number(sk.ss_oos).toFixed(4)} on ${sk.matched_pairs ?? "—"} matched pairs,
      paired p ${sk.p_dm == null ? "—" : Number(sk.p_dm).toPrecision(3)}${t.hp_delta ? ` · ${t.hp_delta} HP` : ""}</p>` : ""}
    ${(t.failures || []).map((f) => `<p class="neg small">${esc(f)}</p>`).join("")}</div>`);
}

// ---------- the scene ----------

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
  ctx.clearRect(0, 0, 320, 180);
  // the abyss: deep violet bands
  const bands = ["#120a22", "#160c2a", "#1a0e32", "#1f1038", "#24123e", "#1c0e30", "#140a24", "#0c0616", "#07040e"];
  bands.forEach((c, i) => rect(ctx, 0, i * 20, 320, 20, c));
  for (let k = 0; k < 30; k++) rect(ctx, (k * 53) % 320, (k * 29) % 70, 1, 1, k % 3 ? "#5a4a8a" : "#9a8ad0");
  // distant ruined castles
  const ruin = "#22183a";
  for (const [x0, h] of [[4, 46], [20, 62], [34, 40], [210, 54], [228, 70], [246, 44]]) {
    rect(ctx, x0, 82 - h, 14, h, ruin);
    for (let b = 0; b < 3; b++) rect(ctx, x0 + b * 5, 78 - h, 3, 4, ruin);
    if ((x0 + Math.floor(f / 40)) % 3 === 0) rect(ctx, x0 + 5, 90 - h, 2, 3, "#3f7fbf");
  }
  rect(ctx, 0, 80, 320, 4, "#1a1230");
  // drifting fog in the abyss
  for (let k = 0; k < 8; k++) {
    const fx = ((k * 61 + f * 0.25 * (k % 2 ? 1 : -1)) % 380) - 30;
    ellipse(ctx, fx, 140 + (k % 3) * 12, 26, 4, k % 2 ? "#2a1a48" : "#22143c");
  }
  // floating stone fragments
  for (let k = 0; k < 7; k++) {
    const x = 18 + k * 44, y = 60 + (k % 3) * 34 + Math.round(Math.sin(f / 30 + k) * 3);
    rect(ctx, x, y, 8 + (k % 3) * 3, 4, "#3a3050"); rect(ctx, x + 1, y, 6 + (k % 3) * 3, 1, "#5a5078"); rect(ctx, x + 2, y + 4, 4, 2, "#2a2240");
  }
  // the golden portal, with the green Overworld inside
  drawPortal(ctx, f);
  // the bridge: stone blocks, cracks and runes; collapsing under an unjustified or invalid claim
  const collapse = BR.phase === "verdict" && (BR.outcome === "INVALID METHODOLOGY" || BR.outcome === "UNJUSTIFIED CONFIDENCE");
  const ct = collapse ? Math.min(1, (now - BR.t0) / 1800) : 0;
  for (let x = 4; x < PORTAL_X - 16; x += 8) {
    const mid = x > 120 && x < 210, fall = collapse && mid && (BR.outcome === "INVALID METHODOLOGY" || x > 150 && x < 190);
    const dy = fall ? Math.round(ct * ct * (60 + (x % 24))) : 0;
    rect(ctx, x, BRIDGE_Y + dy, 8, 10, "#4a4060"); rect(ctx, x + 1, BRIDGE_Y + 1 + dy, 6, 8, (x / 8) % 2 ? "#6e6488" : "#625a7c");
    rect(ctx, x + 1, BRIDGE_Y + 1 + dy, 6, 1, "#8a80a6");
    if ((x / 8) % 5 === 2) rect(ctx, x + 3, BRIDGE_Y + 4 + dy, 2, 3, `rgba(127,224,255,${0.45 + 0.4 * Math.sin(f / 10 + x)})`);  // runes
    if ((x / 8) % 7 === 3) rect(ctx, x + 2, BRIDGE_Y + 8 + dy, 3, 1, "#2a2240");  // cracks
  }
  // pillars with blue flames
  for (const px of [24, 96, 168, 240]) {
    rect(ctx, px, BRIDGE_Y - 14, 4, 14, "#3a3050"); rect(ctx, px - 1, BRIDGE_Y - 16, 6, 2, "#5a5078");
    const fl = f % 12 < 6;
    rect(ctx, px, BRIDGE_Y - 21, 4, 5, fl ? "#3fa0ff" : "#2f7fdf"); rect(ctx, px + 1, BRIDGE_Y - 24, 2, 3, fl ? "#9fe0ff" : "#7fc0ff");
    aura(ctx, px + 2, BRIDGE_Y - 20, 14, "63,160,255", 0.25);
  }
  // the hero
  drawBridgeHero(ctx, now, f, collapse, ct);
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
  // crossing: the portal light floods the screen
  if (BR.phase === "verdict" && BR.crossed && BR.heroX > PORTAL_X - 6) {
    const t = Math.min(1, (now - BR.arrived) / 1500);
    ctx.save(); ctx.globalAlpha = t * 0.85; ctx.fillStyle = "#fff6d0"; ctx.fillRect(0, 0, 320, 180); ctx.restore();
  }
}

function drawPortal(ctx, f) {
  ctx.save();
  ctx.beginPath(); ctx.ellipse(PORTAL_X, PORTAL_Y, 22, 36, 0, 0, Math.PI * 2); ctx.clip();
  rect(ctx, PORTAL_X - 22, PORTAL_Y - 36, 44, 40, "#9ccaf2"); rect(ctx, PORTAL_X - 22, PORTAL_Y - 8, 44, 10, "#c4e0f6");
  disc(ctx, PORTAL_X + 8, PORTAL_Y - 24, 4, "#ffe08a");
  ellipse(ctx, PORTAL_X - 8, PORTAL_Y + 4, 20, 8, "#5fbf6a"); ellipse(ctx, PORTAL_X + 12, PORTAL_Y + 8, 18, 8, "#4fae5a");
  rect(ctx, PORTAL_X - 22, PORTAL_Y + 10, 44, 30, "#3c8a46");
  for (const tx of [-12, -2, 10]) { rect(ctx, PORTAL_X + tx, PORTAL_Y + 2, 2, 5, "#6a4a2a"); disc(ctx, PORTAL_X + tx + 1, PORTAL_Y, 3, "#2f7a3a"); }
  ctx.restore();
  aura(ctx, PORTAL_X, PORTAL_Y, 46, "255,224,138", 0.28 + 0.06 * Math.sin(f / 14));
  ctx.save(); ctx.strokeStyle = "#e8b847"; ctx.lineWidth = 4;
  ctx.beginPath(); ctx.ellipse(PORTAL_X, PORTAL_Y, 24, 38, 0, 0, Math.PI * 2); ctx.stroke();
  ctx.strokeStyle = "#ffe08a"; ctx.lineWidth = 1; ctx.beginPath(); ctx.ellipse(PORTAL_X, PORTAL_Y, 26, 40, 0, 0, Math.PI * 2); ctx.stroke();
  ctx.restore();
  for (let k = 0; k < 8; k++) {
    const a = f / 40 + k * Math.PI / 4;
    rect(ctx, PORTAL_X + Math.round(Math.cos(a) * 30), PORTAL_Y + Math.round(Math.sin(a) * 44), 2, 2, k % 2 ? "#ffe08a" : "#e8b847");
  }
}

function drawBridgeHero(ctx, now, f, collapse, ct) {
  const t = now - BR.t0;
  let target = 34;
  if (BR.phase === "arrive") target = 34;
  if (BR.phase === "trial") target = 140;
  if (BR.phase === "verdict") target = BR.crossed ? PORTAL_X : 158;
  const speed = BR.phase === "verdict" && BR.crossed ? 0.9 : 0.6;
  if (Math.abs(BR.heroX - target) > 0.5) BR.heroX += Math.sign(target - BR.heroX) * Math.min(speed, Math.abs(target - BR.heroX));
  else if (BR.phase === "verdict" && BR.crossed && !BR.arrived) BR.arrived = now;
  if (BR.phase !== "verdict") BR.arrived = 0;
  let y = BRIDGE_Y;
  const falls = collapse && !BR.crossed;
  if (falls) y += Math.round(ct * ct * 90);
  if (BR.phase === "verdict" && BR.crossed && BR.heroX > PORTAL_X - 10) return;  // through the portal
  const walking = Math.abs(BR.heroX - target) > 0.5;
  const bob = walking && !G.reduced ? (Math.floor(f / 6) % 2) : 0;
  if (G.state.version === "V2") aura(ctx, BR.heroX, y - 14, 18, "127,224,255", 0.45);
  const img = pepSprite("Alchemist");
  ctx.save(); ctx.translate(Math.round(BR.heroX), y - bob); ctx.scale(2, 2);
  if (falls) ctx.rotate(ct * 1.2);
  blit(ctx, img, 0, 0); ctx.restore();
  if (G.state.version === "V2") pixelText(ctx, "V2", BR.heroX, y - img.height * 2 - 10, "#7fe0ff");
  if (collapse && BR.crossed && !G.reduced && f % 10 < 5) pixelText(ctx, "!", BR.heroX + 10, y - 40, "#ff4a5a");
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

// The Overworld: drawn in the room scene once the hero has crossed (or seen from the abyss if it fell).
function drawOverworld(ctx, f, s) {
  const crossed = s.finale.overworld && s.finale.overworld.crossed;
  rect(ctx, 0, 0, 320, 110, "#9ccaf2"); rect(ctx, 0, 70, 320, 40, "#c4e0f6");
  disc(ctx, 262, 30, 12, "#ffe08a"); disc(ctx, 262, 30, 9, "#fff6d0");
  for (let k = 0; k < 4; k++) { const cx = (k * 90 + f * 0.15) % 360 - 20; ellipse(ctx, cx, 22 + k * 9, 14, 4, "#ffffff"); }
  ellipse(ctx, 70, 120, 120, 30, "#5fbf6a"); ellipse(ctx, 250, 124, 130, 32, "#4fae5a");
  rect(ctx, 0, 124, 320, 56, "#3c8a46");
  for (let k = 0; k < 12; k++) { const tx = 12 + k * 27, ty = 112 + (k % 3) * 6; rect(ctx, tx, ty, 3, 8, "#6a4a2a"); disc(ctx, tx + 1, ty - 3, 6, k % 2 ? "#2f7a3a" : "#3f8f45"); }
  rect(ctx, 150, 130, 20, 50, "#d8c8a0"); rect(ctx, 152, 130, 16, 50, "#e8dcb8");  // the road home
  rect(ctx, 136, 96, 48, 30, "#e6eff6"); rect(ctx, 132, 92, 56, 6, "#c0294a"); rect(ctx, 154, 110, 10, 16, "#7a5230");  // the academy
  if (crossed) {
    const img = pepSprite("Alchemist");
    ctx.save(); ctx.translate(160, 150); ctx.scale(2, 2); blit(ctx, img, 0, 0); ctx.restore();
    if (s.version === "V2") pixelText(ctx, "V2", 160, 104, "#1f8a8a");
  } else {
    ctx.save(); ctx.globalAlpha = 0.45; ctx.fillStyle = "#1a1230"; ctx.fillRect(0, 0, 320, 180); ctx.restore();
  }
}

bridgeLoop();

// The endgame: the Alchemist's bright laboratory and the Research Decision Brief.
// Everything here is read from the finale ledger row; each claim cites its encounter id.

function showRoom() {
  const f = G.state.finale;
  if (!f) return;
  for (const d of document.querySelectorAll("dialog[open]")) d.close();
  $("screen-game").hidden = true; $("screen-room").hidden = false;
  $("room-headline").innerHTML = `<span class="sim">SIMULATED</span><h2>${esc(f.headline)}</h2>`;
  renderBrief(f);
  if (typeof renderOverworld === "function") renderOverworld(f);
  window.scrollTo(0, 0);
}

let roomFrame = 0;
function roomLoop() {
  const ctx = crispContext($("room-canvas"));
  const tick = () => {
    if (!$("screen-room").hidden && G.state.finale) {
      const draw = G.state.finale.overworld && typeof drawOverworld === "function" ? drawOverworld : drawLab;
      draw(ctx, G.reduced ? 0 : roomFrame++, G.state);
    }
    requestAnimationFrame(tick);
  };
  tick();
}

function drawLab(ctx, f, s) {
  const fin = s.finale, champ = fin.champion;
  // walls, windows and daylight
  rect(ctx, 0, 0, 320, 112, "#e6eff6"); rect(ctx, 0, 104, 320, 8, "#c9d8e4"); rect(ctx, 0, 103, 320, 1, "#a8bccc");
  for (const wx of [8, 262]) {
    rect(ctx, wx, 16, 50, 62, "#b8c8d6"); rect(ctx, wx + 2, 18, 46, 58, "#9ccaf2");
    rect(ctx, wx + 2, 52, 46, 24, "#c4e0f6");
    const cx = wx + 2 + ((f * 0.2 + wx) % 60) - 10;
    ctx.save(); ctx.beginPath(); ctx.rect(wx + 2, 18, 46, 58); ctx.clip();
    ellipse(ctx, cx, 30, 9, 3, "#ffffff"); ellipse(ctx, cx + 22, 42, 7, 2, "#ffffff");
    for (let b = 0; b < 5; b++) rect(ctx, wx + 4 + b * 9, 60 - (b % 3) * 6, 7, 16 + (b % 3) * 6, "#8aa8c8");
    ctx.restore();
    rect(ctx, wx + 24, 16, 2, 62, "#b8c8d6"); rect(ctx, wx, 46, 50, 2, "#b8c8d6");
  }
  // the big wall screen
  rect(ctx, 78, 8, 164, 84, "#3a4658"); rect(ctx, 80, 10, 160, 80, "#10182a");
  const ok = !!champ;
  rect(ctx, 80, 10, 160, 10, ok ? "#2f9a5a" : "#c08a1a");
  for (let i = 0; i < 26; i++) rect(ctx, 84 + i * 6, 14, 4, 2, f % 60 < 30 || i % 2 ? "#ffffff" : (ok ? "#2f9a5a" : "#c08a1a"));
  // the EHR network: five sites, rural ones in cyan
  const regions = (s.campaign && s.campaign.sites) || [];
  const pos = [[112, 52], [134, 40], [128, 70], [98, 36], [100, 72]];
  for (let i = 0; i < 3; i++) for (let j = 0; j < 4; j++) rect(ctx, 88 + j * 14, 28 + i * 16, 12, 14, "#18243a");
  regions.forEach((r, i) => {
    const [x, y] = pos[i % pos.length], pulse = (f / 10 + i) % 6 < 3 ? 1 : 0;
    disc(ctx, x, y, (i === 0 ? 4 : 3) + pulse, r.rural ? "#7fe0ff" : "#ffb347");
    rect(ctx, x, y, 1, 1, "#ffffff");
  });
  // a risk curve on the wall screen, with the champion's prediction traced in gold
  rect(ctx, 156, 26, 78, 58, "#141f34");
  let prev = null;
  for (let x = 0; x < 74; x++) {
    const y = 78 - Math.round(18 * Math.exp(-((x - 44) ** 2) / 120) + 4 * Math.sin(x / 6) + 8);
    if (prev != null) rect(ctx, 158 + x, Math.min(prev, y), 1, Math.abs(prev - y) + 1, "#f3e9d2");
    prev = y;
    if (ok && x % 2 === 0) { const y2 = 78 - Math.round(18 * Math.exp(-((x - 37) ** 2) / 120) + 8); rect(ctx, 158 + x, y2, 1, 1, "#e8b847"); }
  }
  if (ok) rect(ctx, 158 + 30, 28, 1, 54, f % 30 < 20 ? "#5fd67a" : "#2f6a4a");
  // floor
  rect(ctx, 0, 112, 320, 68, "#d9d4cb");
  for (let y = 112; y < 180; y += 12) rect(ctx, 0, y, 320, 1, "#c8c2b6");
  for (let x = 0; x < 320; x += 24) rect(ctx, x + ((Math.floor(x / 24) % 2) * 12), 112, 1, 68, "#c8c2b6");
  // desks with monitors and plants
  for (const [dx, flip] of [[18, 0], [234, 1]]) {
    rect(ctx, dx, 118, 68, 6, "#8a6a4a"); rect(ctx, dx, 124, 4, 22, "#6a4a30"); rect(ctx, dx + 64, 124, 4, 22, "#6a4a30");
    for (let m = 0; m < 2; m++) {
      const mx = dx + 8 + m * 30;
      rect(ctx, mx, 100, 22, 16, "#2a3040"); rect(ctx, mx + 1, 101, 20, 13, "#10182a"); rect(ctx, mx + 10, 116, 2, 2, "#2a3040");
      for (let b = 0; b < 5; b++) { const h = 2 + ((b * 5 + m * 3 + Math.floor(f / 24) + flip) % 9); rect(ctx, mx + 2 + b * 4, 113 - h, 3, h, b % 2 ? "#7fe0ff" : "#5fd67a"); }
    }
  }
  for (const px of [4, 304]) { rect(ctx, px, 136, 10, 10, "#c0623a"); disc(ctx, px + 5, 130, 6, "#3f8a3a"); disc(ctx, px + 3, 126, 4, "#5aa84a"); }
  // the Alchemist at the centre: holding up the champion scroll, or beside the Gatekeeper if the baseline holds
  const rows = fin.ranking || [];
  ellipse(ctx, 160, 158, 20, 4, ok ? "#e8b847" : "#b9b0cc"); ellipse(ctx, 160, 157, 18, 3, ok ? "#ffe08a" : "#d8d0e8");
  if (ok) {
    for (let k = 0; k < 6; k++) {
      const ang = f / 30 + k * Math.PI / 3, sx = 160 + Math.cos(ang) * 16, sy = 128 + Math.sin(ang) * 10;
      rect(ctx, sx, sy, 1, 1, "#ffffff"); rect(ctx, sx - 1, sy, 3, 1, k % 2 ? "#ffe08a" : "#ffffff");
    }
    const a = s.agents[champ.id];
    ctx.save(); ctx.translate(160, 156); ctx.scale(2, 2); blit(ctx, pepSprite("Alchemist"), 0, 0); ctx.restore();
    const bob = Math.round(Math.sin(f / 10));
    ctx.save(); ctx.translate(186, 134 + bob); ctx.scale(2, 2); blit(ctx, scrollSprite(a.archetype), 0, 0); ctx.restore();
  } else {
    ctx.save(); ctx.translate(150, 156); ctx.scale(2, 2); blit(ctx, pepSprite("Alchemist"), 0, 0); ctx.restore();
    ctx.save(); ctx.translate(186, 156); ctx.scale(2, 2); blit(ctx, pepSprite("Gatekeeper"), 0, 0, { flip: true }); ctx.restore();
  }
  // the other scrolls: still rolled up if they survived, a heap of ash if they shattered
  rows.filter((r) => !champ || r.id !== champ.id).forEach((r, i) => {
    const a = s.agents[r.id], x = [100, 220, 76, 244, 52, 268][i % 6], y = 162;
    if (r.status !== "active") { ctx.save(); ctx.translate(x, y); ctx.scale(2, 2); drawAsh(ctx, 0, 0); ctx.restore(); }
    else { ctx.save(); ctx.translate(x, y - 4 + Math.round(Math.sin(f / 12 + i))); ctx.scale(2, 2); blit(ctx, scrollSprite(a.archetype), 0, 0); ctx.restore(); }
  });
}

const STATUS_TONE = { SUPPORTED: "ok", REFUTED: "bad", INCONCLUSIVE: "warn", "NOT ASSESSED": "none" };

function statusBadge(st) {
  return `<span class="sci-badge t-${STATUS_TONE[st] || "none"}">${esc(st || "NOT ASSESSED")}</span>`;
}

function rrText(e) {
  if (!e || e.rr == null) return "—";
  return `${fmt(e.rr, 2)} <small>(95% CI ${fmt(e.lo, 2)} to ${fmt(e.hi, 2)})</small>`;
}

function renderBrief(f) {
  const b = f.brief, s = G.state;
  const cite = (id) => (id ? `<button class="cite" data-cite="${esc(id)}" title="Open this encounter in the Test Inspector">${esc(id)}</button>` : "");
  const evid = (list) => list.map((x) => `<li>${esc(x.text)} ${cite(x.cite)}</li>`).join("");
  const tracks = f.tracks || [];
  const trackOf = Object.fromEntries(tracks.map((t) => [t.outcome, t]));
  // the composite score, grouped by research question: a champion is crowned per track, never across them
  let lastTrack = null, n = 0;
  const scoreRows = f.ranking.map((r) => {
    let head = "";
    if (tracks.length && r.track !== lastTrack) {
      lastTrack = r.track; n = 0;
      const t = trackOf[r.track] || {};
      head = `<tr class="track-row"><td colspan="13"><b>${t.primary ? "Primary question" : "Question"}:</b> ${esc(t.label || r.outcome || r.track)}
        ${statusBadge(t.science && t.science.status)} ${t.champion_name ? `· champion <strong>${esc(t.champion_name)}</strong>` : "· no champion"}</td></tr>`;
    }
    n += 1;
    return head + `<tr class="${r.champion_of ? "champ" : ""} ${r.status !== "active" ? "fallen" : ""}">
    <td>${n}</td><td><strong>${esc(r.name)}</strong><small>${esc(r.title || r.archetype)} · ${esc(r.outcome || "")}</small></td>
    <td><span class="verdict v-${r.verdict.replace(/\s/g, "")}">${esc(r.verdict)}</span></td>
    <td>${r.skill && r.skill.ss_oos != null ? (r.skill.ss_oos >= 0 ? "+" : "") + r.skill.ss_oos.toFixed(4) : "—"}</td><td>${r.skill ? fmt(r.skill.p_dm, 3) : "—"}</td>
    <td>${r.hp}</td><td>${r.traps_falsified}/${r.traps_faced}</td><td>${r.spent}</td>
    <td>${fmt(r.score.skill, 1)}</td><td>${fmt(r.score.hp, 1)}</td><td>${fmt(r.score.traps, 1)}</td><td>${fmt(r.score.efficiency, 1)}</td>
    <td><strong>${fmt(r.score.total, 1)}</strong></td></tr>`;
  }).join("")
    + (f.benchmark ? `<tr class="bench"><td></td><td><strong>${esc(f.benchmark.name)}</strong><small>${esc(f.benchmark.title)} · ${esc(f.benchmark.claim)}</small></td>
      <td><span class="verdict v-BASELINE">BASELINE</span></td><td colspan="10" class="muted">the bar itself: SS<sub>oos</sub> = 0 by definition</td></tr>` : "");
  const maxDmg = Math.max(1, ...f.damage.map((d) => d.hp_lost));
  const dmg = f.damage.map((d) => `<li><span>${esc(d.trap)}</span><i style="width:${(d.hp_lost / maxDmg * 100).toFixed(0)}%"></i><b>${d.hp_lost} HP · ${Math.round(d.share * 100)}%</b></li>`).join("");
  const champ = f.champion;
  const primary = tracks.find((t) => t.primary) || tracks[0];
  const science = tracks.length ? `<section><h3>Is the effect real? The scientific status of each question</h3>
      <p class="small muted">Prediction and causation are judged separately. The verdicts above ask whether a scroll predicts unseen
      patients better than the Gatekeeper's benchmark; this asks whether the drug changes the risk at all, on the same
      matched holdout patients. ${f.science_rules ? `Smallest effect of interest: risk ratio ${fmt(f.science_rules.sesoi_rr)}; 95% intervals; detectable effect at ${Math.round(f.science_rules.power * 100)}% power.` : ""}</p>
      <div class="table-wrap"><table class="score tracks"><thead><tr><th>Question (outcome)</th><th>Status</th><th>Risk ratio, matched holdout</th>
        <th>Events (drug / comparator)</th><th title="The smallest risk ratio these patients could detect with 80% power">Detectable</th><th>Champion</th><th></th></tr></thead>
      <tbody>${tracks.map((t) => `<tr class="${t.primary ? "primary" : ""}"><td><strong>${esc(t.label)}</strong>${t.primary ? "<small>primary question</small>" : ""}</td>
        <td>${statusBadge(t.science.status)}${t.science.below_sesoi ? '<small>smaller than the effect of interest</small>' : ""}</td>
        <td>${rrText(t.effect)}${t.effect && t.effect.method ? `<small>${esc(t.effect.method)}</small>` : ""}</td>
        <td>${t.effect ? `${t.effect.events_treated} / ${t.effect.events_comparator} <small>of ${t.effect.n_treated} / ${t.effect.n_comparator}</small>` : "—"}</td>
        <td>${t.science.mde_rr != null ? fmt(t.science.mde_rr, 2) : "—"}</td>
        <td>${t.champion_name ? esc(t.champion_name) : '<span class="muted">none</span>'}</td><td>${cite(t.cite)}</td></tr>
        <tr class="why"><td colspan="7">${esc(t.science.why || "")}</td></tr>`).join("")}</tbody></table></div></section>` : "";
  const ch = f.challenger;
  const challenger = ch ? `<section class="challenger-card r-${esc((ch.result || "").split(" ")[0])}"><small>Challenger round ${ch.round} · ${esc(ch.track)} · fresh cohort, seed ${ch.seed}</small>
      <h3>${esc(ch.result)}${ch.winner_name ? `: ${esc(ch.winner_name)}` : ""}</h3><p>${esc(ch.why)}</p>
      ${ch.champion ? `<p class="muted small">Champion ${esc(ch.champion.hid)}: won round ${ch.champion.won_round}${ch.champion.defended ? `, defended ${ch.champion.defended}×` : ""}${ch.champion.not_defended ? `, not defended ${ch.champion.not_defended}×` : ""}. Its claim is frozen (SHA-256 ${esc((ch.champion.claim_hash || "").slice(0, 16))}…).</p>` : ""}
      ${ch.applied === false ? `<p class="muted small">Not written to the registry${ch.would_have_been ? ` (it would have been ${esc(ch.would_have_been)})` : ""}.</p>` : ""}
      <div class="table-wrap"><table class="score"><thead><tr><th>Scroll</th><th>Eligible</th><th>Why</th><th>Verdict</th><th>Status</th><th>SS<sub>oos</sub></th></tr></thead>
      <tbody>${(ch.entries || []).map((x) => `<tr class="${x.id === ch.winner ? "champ" : ""}"><td><strong>${esc(x.name)}</strong>${x.incumbent ? "<small>the incumbent</small>" : ""}</td>
        <td>${x.eligible ? "✓" : "✗"}</td><td>${esc(x.why)}</td><td>${esc(x.verdict)}</td><td>${statusBadge(x.science)}</td>
        <td>${x.ss_oos != null ? (x.ss_oos >= 0 ? "+" : "") + Number(x.ss_oos).toFixed(4) : "—"}</td></tr>`).join("")}</tbody></table></div>
      <p class="small muted">Eligible to win: ${esc(ch.eligibility || "")}.</p></section>` : "";
  const holdText = primary && primary.science
    ? `No scroll predicted unseen, matched patients better than the Gatekeeper's benchmark (${esc(f.campaign.comparator)}, no drug effect) with a gain unlikely to be luck. The question itself is ${esc(primary.science.status.toLowerCase())}: ${esc(primary.science.why || "")}`
    : `No scroll predicted unseen, matched patients better than the Gatekeeper's benchmark (${esc(f.campaign.comparator)}, no drug effect) with a gain unlikely to be luck.`;
  const arc = f.archive;
  const broken = arc && arc.check && !arc.check.complete;
  $("brief").innerHTML = `
    <p class="disclaimer">${esc(b.disclaimer)}</p>
    ${broken ? `<p class="trace-warn" role="alert">The Archivist's trace is incomplete: ${arc.check.problems.length} problem${arc.check.problems.length === 1 ? "" : "s"}. Open the Archivist's Ledger tab before relying on any number below.</p>` : ""}
    <header class="brief-head"><small>Research Decision Brief · Campaign ${esc(f.campaign.letter)}</small>
      <h2>${esc(f.campaign.title)}</h2><p class="q">${esc(f.campaign.question)}</p></header>
    <div class="brief-tabs" role="tablist">
      <button class="tab" role="tab" id="tab-brief" aria-selected="true" aria-controls="pane-brief">Research Decision Brief</button>
      ${arc ? `<button class="tab" role="tab" id="tab-arc" aria-selected="false" aria-controls="pane-arc">📜 Archivist's Ledger · Sources &amp; Methods</button>` : ""}
    </div>
    <div id="pane-brief" role="tabpanel" aria-labelledby="tab-brief">
    <section class="decision ${f.baseline_holds ? "hold" : "go"}"><small>Decision</small><h3>${esc(b.decision)}</h3><p>${esc(b.recommendation)}</p></section>
    ${challenger}
    ${champ ? `<section class="champ-card"><img src="${portrait(champ.archetype)}" alt="" width="48" height="48">
        <div><small>Champion scroll${primary && tracks.length > 1 ? ` · ${esc(primary.label)}` : ""}</small><strong>${esc(champ.name)}, ${esc(champ.title || "")}</strong>
        <p>"${esc(champ.claim)}"</p><p class="muted">Outcome: ${esc(champ.outcome)} · ${champ.design === "new_user" ? "new-user, time-zero design" : "design as carried"} · K = ${champ.K}</p></div></section>`
      : `<section class="champ-card hold"><img src="${portrait("gatekeeper")}" alt="" width="48" height="48"><div><small>Result</small><strong>Baseline Holds${b.status ? `: question ${esc(b.status.toLowerCase())}` : ""}</strong>
        <p>${holdText}</p></div></section>`}
    ${science}
    ${b.evidence.length ? `<section><h3>Evidence</h3><ul class="evidence">${evid(b.evidence)}</ul></section>` : ""}
    ${b.misleading.length ? `<section><h3>What misled the others</h3><ul class="evidence">${evid(b.misleading)}</ul></section>` : ""}
    <section><h3>Uncertainty</h3><p>${esc(b.uncertainty)}</p></section>
    <section><h3>Composite score</h3><div class="table-wrap"><table class="score">
      <thead><tr><th>#</th><th>Scroll</th><th>Verdict</th><th>SS<sub>oos</sub></th><th>Paired p</th><th>HP</th><th>Traps</th><th>Credits</th>
      <th title="${esc(f.score_rules.skill)}">Skill</th><th title="${esc(f.score_rules.hp)}">HP pts</th><th title="${esc(f.score_rules.traps)}">Trap pts</th>
      <th title="${esc(f.score_rules.efficiency)}">Efficiency</th><th>Total</th></tr></thead><tbody>${scoreRows}</tbody></table></div>
      <p class="small muted">Score = ${Object.values(f.score_rules).map(esc).join(" + ")}. Each question's champion is its highest-scoring VALIDATED scroll; scrolls on different questions are never ranked against each other.</p></section>
    <div class="two">
      <section><h3>HP after each level</h3>${hpChart(f.ranking)}</section>
      <section><h3>Where the HP went</h3><ul class="dmg">${dmg || "<li>No damage dealt.</li>"}</ul></section>
    </div>
    <section><details class="truth"><summary>Reveal the planted truth of this simulated world</summary><p>${esc(f.truth)}</p></details></section>
    <p class="small muted">${f.totals.encounters} encounters · ${f.totals.credits_spent} credits spent · ${f.totals.traps_sprung} traps sprung · ${f.totals.shattered} shattered</p>
    </div>
    ${arc ? `<div id="pane-arc" role="tabpanel" aria-labelledby="tab-arc" hidden>${archivistHTML(arc, cite)}</div>` : ""}
    <div class="brief-buttons"><button class="btn" id="back-log">Back to the battle log</button>
      <button class="btn" id="dl">Download the ledger (JSONL)</button>
      ${arc ? '<button class="btn" id="dl-manifest">Download the manifest (JSON)</button>' : ""}
      <button class="btn gold" id="again">Choose another campaign</button></div>`;
  for (const c of document.querySelectorAll("[data-cite]")) c.onclick = () => openCite(c.dataset.cite);
  for (const t of document.querySelectorAll(".brief-tabs .tab")) {
    t.onclick = () => {
      for (const o of document.querySelectorAll(".brief-tabs .tab")) {
        o.setAttribute("aria-selected", String(o === t));
        $(o.getAttribute("aria-controls")).hidden = o !== t;
      }
    };
  }
  $("back-log").onclick = backToLog;
  $("again").onclick = exitGame;
  $("dl").onclick = () => download(G.state.events.map((e) => JSON.stringify(e)).join("\n") + "\n", "application/x-ndjson",
                                    `pep-${f.campaign.letter}-ledger.jsonl`);
  if (arc) $("dl-manifest").onclick = () => download(JSON.stringify(arc, null, 2) + "\n", "application/json",
                                                      `pep-${f.campaign.letter}-manifest.json`);
}

function download(text, type, name) {
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([text], { type })); a.download = name; a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 1000);
}

// The Archivist's Ledger: every source a number came from, the method behind every encounter, and the manifest's hash.
function archivistHTML(arc, cite) {
  const ok = arc.check && arc.check.complete;
  const short = (h) => (h ? `<code title="${esc(h)}">${esc(h.slice(0, 12))}…</code>` : "—");
  const fp = Object.entries(arc.fingerprints || {}).map(([k, v]) => `<tr><th>${esc(k)}</th><td>${short(v)}</td></tr>`).join("");
  const src = (arc.sources || []).map((x) => `<tr><td><code>${esc(x.id)}</code></td><td><span class="stype t-${esc(x.type)}">${esc(x.type.replace(/_/g, " "))}</span></td>
    <td>${esc(x.label)}${x.sealed ? ' <span class="tag">sealed</span>' : ""}${x.opened_by_spec ? ` <small>opened once by the locked spec ${esc(x.opened_by_spec.slice(0, 12))}…</small>` : ""}</td>
    <td>${esc((x.usage || "").replace(/_/g, " ").toLowerCase())}</td><td>${short(x.sha256 || x.claim_sha256)}</td></tr>`).join("");
  const methods = Object.entries(arc.methods || {}).map(([k, v]) => `<li><code>${esc(k)}</code> ${esc(v)}</li>`).join("");
  const trace = (arc.trace || []).map((r) => `<tr><td>${cite(r.encounter)}</td><td>${ROMAN[r.level] || r.level || ""}</td><td>${esc(r.scroll || "")}</td>
    <td>${esc(r.enemy || "")}</td><td><code>${esc(r.method || "")}</code></td><td>${(r.sources || []).map((x) => `<code>${esc(x)}</code>`).join(" ")}</td></tr>`).join("");
  return `<section class="archivist">
    <p class="trace-check ${ok ? "ok" : "bad"}">${ok
      ? `Trace complete: every one of ${arc.check.encounters} encounters names a known method and only registered sources, and every citation in the brief points at a traced encounter.`
      : `Trace incomplete: ${arc.check.problems.map(esc).join("; ")}`}</p>
    <table class="nums"><tr><th>Run</th><td><code>${esc(arc.run_id)}</code></td></tr>
      <tr><th>Campaign · seed</th><td>${esc(arc.campaign)} · ${arc.seed}</td></tr>
      <tr><th>Ruleset · generator</th><td><code>${esc(arc.ruleset_version)}</code> · <code>${esc(arc.generator)}</code></td></tr>
      <tr><th>Manifest SHA-256</th><td><code>${esc(arc.sha256)}</code></td></tr>
      ${arc.trial ? `<tr><th>Trial of Truth</th><td>${esc(arc.trial.outcome || "")} · spec ${short(arc.trial.spec_sha256)}</td></tr>` : ""}</table>
    <h3>Commitments</h3><p class="small muted">SHA-256 of each partition of the simulated cohort, published in the first ledger row before anything was measured.</p>
    <table class="nums">${fp}</table>
    <h3>Sources</h3><div class="table-wrap"><table class="score"><thead><tr><th>Id</th><th>Type</th><th>What it is</th><th>Use</th><th>SHA-256</th></tr></thead><tbody>${src}</tbody></table></div>
    <h3>Methods used</h3><ul class="methods">${methods}</ul>
    <h3>Trace</h3><div class="table-wrap"><table class="score"><thead><tr><th>Encounter</th><th>Lv</th><th>Scroll</th><th>Enemy</th><th>Method</th><th>Sources</th></tr></thead><tbody>${trace}</tbody></table></div>
  </section>`;
}

function backToLog() {
  $("screen-room").hidden = true; $("screen-game").hidden = false;
}

function openCite(id) {
  const e = findEncounter(G.state.events, id);
  if (!e) return;
  backToLog();
  G.pinned = e.seq; inspect(e);
  const tr = document.querySelector(`#ledger tr[data-seq="${e.seq}"]`);
  if (tr) { tr.classList.add("hl"); tr.scrollIntoView({ block: "center" }); setTimeout(() => tr.classList.remove("hl"), 2000); }
  $("inspector").scrollIntoView({ behavior: G.reduced ? "auto" : "smooth", block: "start" });
}

// the ✦ node returns to the room once the campaign is over
document.addEventListener("click", (ev) => {
  const li = ev.target.closest("#nodes li");
  if (li && G.state.finale && li.textContent.includes("✦")) showRoom();
});

roomLoop();

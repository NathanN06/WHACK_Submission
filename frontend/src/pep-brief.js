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
    const a = s.agents[r.id], x = [100, 220, 76, 244][i % 4], y = 162;
    if (r.status !== "active") { ctx.save(); ctx.translate(x, y); ctx.scale(2, 2); drawAsh(ctx, 0, 0); ctx.restore(); }
    else { ctx.save(); ctx.translate(x, y - 4 + Math.round(Math.sin(f / 12 + i))); ctx.scale(2, 2); blit(ctx, scrollSprite(a.archetype), 0, 0); ctx.restore(); }
  });
}

function renderBrief(f) {
  const b = f.brief, s = G.state;
  const cite = (id) => (id ? `<button class="cite" data-cite="${esc(id)}" title="Open this encounter in the Test Inspector">${esc(id)}</button>` : "");
  const evid = (list) => list.map((x) => `<li>${esc(x.text)} ${cite(x.cite)}</li>`).join("");
  const scoreRows = f.ranking.map((r, i) => `<tr class="${r.id === (f.champion && f.champion.id) ? "champ" : ""} ${r.status !== "active" ? "fallen" : ""}">
    <td>${i + 1}</td><td><strong>${esc(r.name)}</strong><small>${esc(r.title || r.archetype)} · ${esc(r.outcome || "")}</small></td>
    <td><span class="verdict v-${r.verdict.replace(/\s/g, "")}">${esc(r.verdict)}</span></td>
    <td>${r.skill && r.skill.ss_oos != null ? (r.skill.ss_oos >= 0 ? "+" : "") + r.skill.ss_oos.toFixed(4) : "—"}</td><td>${r.skill ? fmt(r.skill.p_dm, 3) : "—"}</td>
    <td>${r.hp}</td><td>${r.traps_falsified}/${r.traps_faced}</td><td>${r.spent}</td>
    <td>${fmt(r.score.skill, 1)}</td><td>${fmt(r.score.hp, 1)}</td><td>${fmt(r.score.traps, 1)}</td><td>${fmt(r.score.efficiency, 1)}</td>
    <td><strong>${fmt(r.score.total, 1)}</strong></td></tr>`).join("")
    + (f.benchmark ? `<tr class="bench"><td></td><td><strong>${esc(f.benchmark.name)}</strong><small>${esc(f.benchmark.title)} · ${esc(f.benchmark.claim)}</small></td>
      <td><span class="verdict v-BASELINE">BASELINE</span></td><td colspan="10" class="muted">the bar itself: SS<sub>oos</sub> = 0 by definition</td></tr>` : "");
  const maxDmg = Math.max(1, ...f.damage.map((d) => d.hp_lost));
  const dmg = f.damage.map((d) => `<li><span>${esc(d.trap)}</span><i style="width:${(d.hp_lost / maxDmg * 100).toFixed(0)}%"></i><b>${d.hp_lost} HP · ${Math.round(d.share * 100)}%</b></li>`).join("");
  const champ = f.champion;
  $("brief").innerHTML = `
    <p class="disclaimer">${esc(b.disclaimer)}</p>
    <header class="brief-head"><small>Research Decision Brief · Campaign ${esc(f.campaign.letter)}</small>
      <h2>${esc(f.campaign.title)}</h2><p class="q">${esc(f.campaign.question)}</p></header>
    <section class="decision ${f.baseline_holds ? "hold" : "go"}"><small>Decision</small><h3>${esc(b.decision)}</h3><p>${esc(b.recommendation)}</p></section>
    ${champ ? `<section class="champ-card"><img src="${portrait(champ.archetype)}" alt="" width="48" height="48">
        <div><small>Champion scroll</small><strong>${esc(champ.name)}, ${esc(champ.title || "")}</strong>
        <p>"${esc(champ.claim)}"</p><p class="muted">Outcome: ${esc(champ.outcome)} · ${champ.design === "new_user" ? "new-user, time-zero design" : "design as carried"} · K = ${champ.K}</p></div></section>`
      : `<section class="champ-card hold"><img src="${portrait("gatekeeper")}" alt="" width="48" height="48"><div><small>Result</small><strong>Baseline Holds: inconclusive</strong>
        <p>No scroll predicted unseen, matched patients better than the Gatekeeper's benchmark (${esc(f.campaign.comparator)}, no drug effect) with a gain unlikely to be luck.</p></div></section>`}
    ${b.evidence.length ? `<section><h3>Evidence</h3><ul class="evidence">${evid(b.evidence)}</ul></section>` : ""}
    ${b.misleading.length ? `<section><h3>What misled the others</h3><ul class="evidence">${evid(b.misleading)}</ul></section>` : ""}
    <section><h3>Uncertainty</h3><p>${esc(b.uncertainty)}</p></section>
    <section><h3>Composite score</h3><div class="table-wrap"><table class="score">
      <thead><tr><th>#</th><th>Scroll</th><th>Verdict</th><th>SS<sub>oos</sub></th><th>Paired p</th><th>HP</th><th>Traps</th><th>Credits</th>
      <th title="${esc(f.score_rules.skill)}">Skill</th><th title="${esc(f.score_rules.hp)}">HP pts</th><th title="${esc(f.score_rules.traps)}">Trap pts</th>
      <th title="${esc(f.score_rules.efficiency)}">Efficiency</th><th>Total</th></tr></thead><tbody>${scoreRows}</tbody></table></div>
      <p class="small muted">Score = ${Object.values(f.score_rules).map(esc).join(" + ")}. The champion is the highest-scoring VALIDATED scroll.</p></section>
    <div class="two">
      <section><h3>HP after each level</h3>${hpChart(f.ranking)}</section>
      <section><h3>Where the HP went</h3><ul class="dmg">${dmg || "<li>No damage dealt.</li>"}</ul></section>
    </div>
    <section><details class="truth"><summary>Reveal the planted truth of this simulated world</summary><p>${esc(f.truth)}</p></details></section>
    <p class="small muted">${f.totals.encounters} encounters · ${f.totals.credits_spent} credits spent · ${f.totals.traps_sprung} traps sprung · ${f.totals.shattered} shattered</p>
    <div class="brief-buttons"><button class="btn" id="back-log">Back to the battle log</button>
      <button class="btn" id="dl">Download the ledger (JSONL)</button><button class="btn gold" id="again">Choose another campaign</button></div>`;
  for (const c of document.querySelectorAll("[data-cite]")) c.onclick = () => openCite(c.dataset.cite);
  $("back-log").onclick = backToLog;
  $("again").onclick = exitGame;
  $("dl").onclick = () => {
    const blob = new Blob([G.state.events.map((e) => JSON.stringify(e)).join("\n") + "\n"], { type: "application/x-ndjson" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob); a.download = `pep-${f.campaign.letter}-ledger.jsonl`; a.click();
    setTimeout(() => URL.revokeObjectURL(a.href), 1000);
  };
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

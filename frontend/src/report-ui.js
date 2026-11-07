// Screens built from the ledger: level complete, the Overworld final report, the research
// ledger view, the raw-number inspector, the tutorial and the glossary. Every number shown
// here was written by the backend; this file only lays it out.

const GLOSSARY = [
  ["Hypothesis", "A claim that could be wrong, e.g. \"fibre lowers the spike\". Each agent defends one."],
  ["Baseline", "What we can already predict without the claim: here, the carbs in the meal."],
  ["Confidence interval (CI)", "The range the true value plausibly lies in (95% of the time). If it includes zero, the effect might be nothing."],
  ["p-value", "How often pure chance would look this good. Small (below 0.05) means luck is an unlikely explanation."],
  ["Permutation test", "Scramble the evidence many times. If scrambled copies do as well as the real thing, the result is luck."],
  ["Replication", "Repeating the finding in separate groups of people. Real effects replicate."],
  ["Multiple-testing correction", "Try 20 claims and one will look good by chance. The correction raises the bar for every extra try."],
  ["Confounding", "When something else (like carbs) is behind a pattern you credited to your claim."],
  ["Data leakage", "Using information you would not have had at prediction time, or that is built from the answer itself."],
  ["Holdout", "People kept completely apart until the end. The final test of whether a claim works on someone new."],
  ["Ablation", "Comparing predictions with and without a piece of evidence, to measure what it adds."],
  ["HP", "Research integrity in the game. It drops when a check fails. It is not the chance the claim is true."],
  ["Research credits", "Each agent's budget for tests. Spending wisely matters; running more tests does not win by itself."],
];

function glossaryHtml() {
  return `<h3>Plain-English glossary</h3><dl class="glossary">${GLOSSARY.map(([t, d]) =>
    `<div><dt>${esc(t)}</dt><dd>${esc(d)}</dd></div>`).join("")}</dl>`;
}

function scoreTableHtml(components, hpBonus = 0.05) {
  if (!components) return "";
  const rows = Object.values(components).map((c) => `<tr><td>${esc(c.label)}</td><td>${c.max}</td><td>${esc(c.rule)}</td></tr>`).join("");
  return `<h3>The scoring rule (decided before any run)</h3>
    <table><tr><th>Component</th><th>Max</th><th>How it is earned</th></tr>${rows}
    <tr><td>HP bonus</td><td>5</td><td>${hpBonus} per HP left: part of the story, never enough to beat better evidence</td></tr></table>`;
}

const pct = (x) => `${Math.round(x * 100)}%`;
const list = (xs) => xs && xs.length ? xs.map((x) => esc(x)).join(", ") : "<span class=\"muted\">none</span>";

// ---------- level complete (spec section 8) ----------

async function levelComplete(e) {
  const L = e.result;
  scene.portal = true;
  foe = null;
  for (const id of state.order) if (state.heroes[id].status === "questing") home(id);
  banner("Level complete", "");
  await wait(900);
  banner(null);
  const md = L.most_damaging;
  const rows = (L.rows || []).map((r) => {
    const h = state.heroes[r.id];
    return `<tr><td>${heroImg(r.id, 24)}${esc(r.name)}</td>
      <td><span class="bar ${barClass(r.hp)}"><i style="width:${r.hp}%"></i></span>${r.hp}</td>
      <td>${r.credits_left}</td><td>${r.tests}</td>
      <td class="pass small">${list(r.strengthened)}</td><td class="fail small">${list(r.weakened)}</td>
      <td>${r.status === "questing" ? (L.level < 4 ? "Onward" : "Survived") : verdictTag(r.verdict || (h && h.verdict) || r.status.toUpperCase())}</td></tr>`;
  }).join("");
  const d = $("#level-done");
  d.innerHTML = `<h2 tabindex="-1">Level complete</h2><p class="sub">${esc(L.name)} · ${L.cleared.length} of ${state.order.length} still standing</p>
    <div class="totals">
      <div><b>${md ? esc(md.name) : "None"}</b><small>most damaging enemy${md ? ` · ${md.hp_dealt} HP dealt (${esc(md.weakness)})` : ""}</small></div>
      <div><b>${L.leader ? esc(L.leader.name) : "Nobody"}</b><small>current leader${L.leader ? ` · score ${L.leader.score}` : ""}</small></div>
      <div><b>${(L.rows || []).reduce((n, r) => n + r.tests, 0)}</b><small>research tests performed</small></div>
    </div>
    <div class="table-wrap"><table><tr><th>Agent</th><th title="Research integrity left">HP left</th><th title="Research credits remaining">Credits left</th><th>Tests</th>
      <th>Evidence that strengthened it</th><th>Evidence that weakened it</th><th>Status</th></tr>${rows}</table></div>
    <div class="lesson"><b>Lesson:</b> ${esc(LESSONS[L.level] || "")}</div>
    <form method="dialog" class="actions"><button class="btn gold" value="go">${L.level < 4 ? "Enter the portal" : "Step through to the real world"}</button></form>`;
  d.showModal();
  d.scrollTop = 0; d.querySelector("h2").focus();
  await new Promise((r) => {
    d.addEventListener("close", r, { once: true });
    if (skipping) { skipping = false; $("#skip").disabled = false; }
    if (autoContinue) wait(12000).then(() => { if (d.open) d.close(); });
  });
  // the transition: the party walks into the portal, the screen dissolves
  for (const id of state.order) if (state.heroes[id].status === "questing") { const v = ensureVis(id); v.tx = 340; v.ty = 122; }
  await wait(1400);
  if (!reduced) for (let i = 0; i < 6; i++) { burst(336, 110, i % 2 ? "#e8b847" : "#d08aff", 10, 2); await wait(80); }
  await fadeTo(1);
  scene.portal = false;
}

// ---------- the Overworld and the final report (spec section 10) ----------

async function finale(e) {
  const F = e.result;
  scene.mode = "overworld";
  $("#hud-num").textContent = "✦";
  $("#hud-name").textContent = "The Overworld";
  $("#hud-evidence").textContent = F.champion ? "The real world: the champion delivers its report" : "No hypothesis made it out";
  for (const id of state.order) { const v = ensureVis(id); v.dead = false; v.ghost = false; v.alpha = 0; }
  const champ = F.champion && ensureVis(F.champion.id);
  if (champ) { champ.alpha = 1; champ.x = 34; champ.y = 146; champ.tx = 34; champ.ty = 146; }
  renderHud();
  await fadeTo(0);
  if (champ) {
    banner("The Overworld", "The real world");
    burst(34, 130, "#e8b847", 30, 1.6);
    await wait(700);
    champ.tx = 214; champ.ty = 150;   // walks up the path to the institute
    await wait(2600);
    banner(null);
  } else {
    banner("Inconclusive", "No hypothesis survived every validation step.");
    await wait(2200);
    banner(null);
  }
  showReport(F);
}

function hpChart(F) {
  const W = 320, H = 130, pad = 26, stepX = (W - pad * 2) / 4;
  const y = (hp) => H - 20 - (hp / 100) * (H - 40);
  const lines = F.ranking.map((r) => {
    const pts = [100, ...[1, 2, 3, 4].map((l) => r.hp_by_level[l] ?? r.hp_by_level[String(l)] ?? null)];
    let last = 100, d = "";
    pts.forEach((p, i) => { const v = p == null ? last : p; last = v; d += `${i ? "L" : "M"}${pad + i * stepX},${y(v)} `; });
    const champ = F.champion && r.id === F.champion.id;
    return `<path d="${d}" fill="none" stroke="${champ ? "#e8b847" : "#6b5a8a"}" stroke-width="${champ ? 3 : 1}" ${champ ? "" : 'opacity=".6"'}/>`;
  });
  const champLine = lines.splice(F.ranking.findIndex((r) => F.champion && r.id === F.champion.id), 1);
  const labels = ["Start", "I", "II", "III", "IV"].map((t, i) => `<text x="${pad + i * stepX}" y="${H - 4}" text-anchor="middle">${t}</text>`).join("");
  const grid = [0, 50, 100].map((v) => `<line x1="${pad}" x2="${W - pad}" y1="${y(v)}" y2="${y(v)}" stroke="#2a2440"/><text x="4" y="${y(v) + 4}">${v}</text>`).join("");
  return `<svg class="chart" viewBox="0 0 ${W} ${H}" role="img" aria-label="HP after each level">${grid}${lines.join("")}${champLine.join("")}${labels}</svg>`;
}

function damageBars(rows) {
  if (!rows || !rows.length) return "<p>No damage taken.</p>";
  const max = rows[0].hp_lost;
  return `<table class="dmg"><tr><th>Weakness</th><th>HP lost</th><th>Share</th></tr>${rows.map((d) =>
    `<tr><td>${esc(d.weakness)}</td><td><span class="bar low"><i style="width:${(d.hp_lost / max) * 100}%"></i></span>${d.hp_lost}</td><td>${pct(d.share)}</td></tr>`).join("")}</table>`;
}

function showReport(F) {
  const C = F.champion, K = F.consensus || {};
  const comps = F.score_components || {};
  const compCols = Object.keys(comps);
  const rank = F.ranking.map((r, i) => `<tr class="${C && r.id === C.id ? "champ" : ""}"><td>${i + 1}</td><td>${heroImg(r.id, 24)}${esc(r.name)}</td>
    <td>${esc(r.claim)}${r.crowd ? ' <span class="tag-v">yours</span>' : ""}</td><td>${verdictTag(r.verdict)}</td>
    ${compCols.map((k) => `<td>${r.components[k]}</td>`).join("")}<td>${r.hp}</td><td><b>${r.score}</b></td></tr>`).join("");
  const decoys = F.decoys.map((d) => `<li><b>${esc(d.name)}</b> was secretly <i>${esc(d.decoy.replace(/_/g, " "))}</i>: ${d.caught ? '<span class="pass">caught</span>' : '<span class="fail">slipped through</span>'} (${esc(d.verdict)})</li>`).join("");
  const t = F.totals;
  const cites = (K.citations || []).map((c) => `<button type="button" class="cite" data-enc="${esc(c)}">${esc(c)}</button>`).join(" ");
  const demo = F.sources && F.sources.synthetic
    ? `<p class="demo-note">DEMO MODE: synthetic meals with planted, known effects. These are not real scientific findings.</p>` : "";
  const dlg = $("#finale");
  dlg.innerHTML = `<h2 tabindex="-1">${C ? "Final research report" : "Inconclusive"}</h2>
    <p class="sub">${esc(F.question || "")}</p>${demo}
    ${C ? `<section class="rep"><h3>A · Winning researcher</h3>
      <div class="champ-card">${heroImg(C.id, 64)}<div>
        <b class="big">${esc(C.name)} the ${esc(C.cls)}</b>
        <p>Hypothesis: <b>${esc(C.claim)}</b></p>
        <p>Total research performance: <b>${C.score}</b> of 105 · Final HP: <b>${C.hp}</b></p>
        <p class="small">${esc(C.why || "")}</p></div></div></section>` :
      `<section class="rep"><h3>A · No winner</h3><p>${esc(F.conclusion)}</p></section>`}
    <section class="rep"><h3>B · HP after each level</h3>${hpChart(F)}
      <p class="small">${C ? "Gold: the champion. Purple: every other agent." : "Every agent's HP across the four levels."}</p></section>
    <section class="rep"><h3>C · What did the damage</h3>${damageBars(F.damage)}
      ${C && C.damage && C.damage.length ? `<p class="small">The champion itself lost HP to: ${C.damage.map((d) => `${esc(d.weakness)} (${d.hp_lost})`).join(", ")}.</p>` : ""}</section>
    ${C ? `<section class="rep"><h3>D · Which evidence carried the conclusion</h3>
      <p class="small">Measured by ablation (prediction error with vs without the evidence) and the other tests that ran. No percentages are invented.</p>
      <table class="contrib"><tr><th>Evidence source</th><th>Test</th><th>Result</th><th></th></tr>${C.contributions.map((c) =>
        `<tr><td>${esc(c.source)}</td><td>${esc(c.test)}</td><td>${esc(c.value)}</td><td>${c.supports ? '<span class="pass">supports</span>' : '<span class="fail">against</span>'}</td></tr>`).join("")}</table></section>` : ""}
    <section class="rep"><h3>E · Final scientific consensus</h3>
      <p class="conclusion">${esc(K.answer || F.conclusion)}</p>
      ${K.supporting && K.supporting.length ? `<p><b>Evidence for it:</b></p><ul>${K.supporting.map((x) => `<li>${esc(x)}</li>`).join("")}</ul>` : ""}
      ${K.also_validated && K.also_validated.length ? `<p><b>Also validated:</b> ${list(K.also_validated)}</p>` : ""}
      ${K.misleading && K.misleading.length ? `<p><b>What was misleading:</b></p><ul>${K.misleading.map((x) => `<li>${esc(x)}</li>`).join("")}</ul>` : ""}
      <p><b>Remaining uncertainty:</b> ${esc(K.uncertainty || "")}</p>
      ${C ? `<p><b>Did the original hypothesis survive?</b> ${K.original_claim_survived ? "Yes, unchanged." : "Only after the Researcher revised it."}</p>` : ""}
      ${cites ? `<p><b>Executed tests cited:</b> ${cites}</p>` : ""}</section>
    <section class="rep"><h3>Scores for every agent</h3><div class="table-wrap"><table class="scores"><tr><th>#</th><th>Agent</th><th>Hypothesis</th><th>Verdict</th>
      ${compCols.map((k) => `<th title="${esc(comps[k].rule)}">${esc(comps[k].label)} /${comps[k].max}</th>`).join("")}<th>HP</th><th>Score</th></tr>${rank}</table></div></section>
    <div class="totals"><div><b>${t.tests_attempted}</b><small>tests attempted</small></div><div><b>${t.credits_spent}</b><small>credits spent</small></div>
      <div><b>${t.invalid_claims_detected}</b><small>weak claims detected</small></div><div><b>${t.useful_evidence}</b><small>checks passed</small></div>
      <div><b>${t.redundant}</b><small>redundant checks</small></div><div><b>${F.caught}/${F.decoys.length}</b><small>impostors caught</small></div></div>
    ${decoys ? `<h3>The impostors revealed</h3><ul>${decoys}</ul>` : ""}
    <form method="dialog" class="actions"><button class="btn gold" value="ledger">View full evidence ledger</button>
      <button class="btn" value="replay">Replay</button><button class="btn" value="again">New quest</button><button class="btn ghost" value="stay">Close</button></form>`;
  for (const b of dlg.querySelectorAll(".cite")) b.addEventListener("click", () => inspectRecord(state.records.find((r) => r.encounter_id === b.dataset.enc)));
  dlg.showModal();
  dlg.scrollTop = 0; dlg.querySelector("h2").focus();
}

$("#finale").addEventListener("close", () => {
  const v = $("#finale").returnValue;
  if (v === "again") location.href = location.pathname;
  if (v === "replay") replay();
  if (v === "ledger") setView(true);
});

// ---------- research ledger view + inspector (spec sections 11, 12) ----------

function renderLedgerTable() {
  const rows = state.records.map((r, i) => `<tr data-i="${i}" tabindex="0"><td>${esc(r.encounter_id)}</td><td>${ROMAN[r.level]}</td><td>${esc(r.hero)}</td>
    <td>${esc(r.enemy_name || r.enemy_type)}</td><td>${esc(ABILITIES[r.research_action] || r.research_action)}</td><td>${esc(r.test_requested)}</td>
    <td class="${r.methodological_verdict === "PASS" ? "pass" : r.methodological_verdict === "FAIL" || r.methodological_verdict === "CONCEDED" ? "fail" : ""}">${esc(r.methodological_verdict)}</td>
    <td>${r.hp_change > 0 ? "+" : ""}${r.hp_change}</td><td class="small">${esc(r.line || r.explanation)}</td></tr>`).join("");
  $("#ledger-table").innerHTML = `<tr><th>ID</th><th>Lvl</th><th>Agent</th><th>Enemy</th><th>Action</th><th>Test</th><th>Verdict</th><th>HP</th><th>Result</th></tr>${rows}`;
  for (const tr of document.querySelectorAll("#ledger-table tr[data-i]")) {
    const open = () => inspectRecord(state.records[Number(tr.dataset.i)]);
    tr.addEventListener("click", open);
    tr.addEventListener("keydown", (ev) => { if (ev.key === "Enter") open(); });
  }
}

let ledgerOn = false;
function setView(ledger) {
  ledgerOn = ledger;
  $("#view").setAttribute("aria-pressed", String(ledger));
  $("#view").textContent = ledger ? "Game view" : "Ledger view";
  $("#ledger-view").hidden = !ledger;
  for (const sel of [".stage", "#combat"]) $(sel).hidden = ledger;
  if (ledger) renderLedgerTable();
}
$("#view").addEventListener("click", () => setView(!ledgerOn));

function fmt(v) {
  if (v == null) return "—";
  if (typeof v === "number") return Number.isInteger(v) ? String(v) : v.toFixed(4);
  if (typeof v === "object") return `<pre>${esc(JSON.stringify(v, null, 1))}</pre>`;
  return esc(v);
}

function inspectRecord(r) {
  if (!r) return;
  const nums = r.numerical_result ? Object.entries(r.numerical_result).map(([k, v]) => `<tr><td>${esc(k)}</td><td>${fmt(v)}</td></tr>`).join("") : "";
  const fields = ["encounter_id", "level", "agent_id", "hypothesis_id", "evidence_source", "evidence_version", "enemy_type",
                  "research_action", "test_requested", "methodological_verdict", "hp_change", "explanation"];
  const d = $("#inspect-dlg");
  d.innerHTML = `<h2 tabindex="-1">${esc(r.encounter_id)}</h2>
    <p class="sub">${esc(r.hero)} vs ${esc(r.enemy_name || r.enemy_type)} · ${esc(TESTS[r.test_requested] || r.test_requested)}</p>
    <h3>Numbers the engine returned</h3>${nums ? `<table>${nums}</table>` : "<p>No test ran: the challenge was conceded.</p>"}
    <h3>The full record</h3><table>${fields.map((k) => `<tr><td>${k}</td><td>${fmt(r[k])}</td></tr>`).join("")}
      <tr><td>timestamp</td><td>${new Date(r.timestamp * 1000).toISOString()}</td></tr></table>
    <form method="dialog" class="actions"><button class="btn gold">Close</button></form>`;
  d.showModal();
  d.scrollTop = 0; d.querySelector("h2").focus();
}

$("#inspect").addEventListener("click", () => {
  const enc = state.encounter;
  if (!enc) return;
  const r = [...state.records].reverse().find((x) => x.agent_id === enc.hero && x.enemy_type === enc.enemy);
  inspectRecord(r);
});

// ---------- tutorial: four cards, under 30 seconds ----------

const TUTORIAL = [
  ["The AI researchers are the players", "Each hero defends one hypothesis about blood sugar after meals. You watch and direct; they investigate."],
  ["Every enemy is a real test", "When a monster attacks, the statistics engine runs a real check. The panel below the dungeon says what ran, what it found, and why it matters."],
  ["HP and research credits", "HP is research integrity: failed checks hurt, passed checks heal a little. Credits limit how many tests each hero can afford."],
  ["Four levels, then the real world", "Rumours, early studies, replication, then people never seen before. Only a claim that survives everything leaves the dungeon. If none does, the verdict is Inconclusive."],
];

async function showTutorial() {
  const d = $("#tutorial");
  const wasPaused = paused;
  paused = true;
  let i = 0, timer = null;
  const draw = () => {
    const [h, p] = TUTORIAL[i];
    d.innerHTML = `<p class="sub">How to watch · ${i + 1} of ${TUTORIAL.length}</p><h2 tabindex="-1">${esc(h)}</h2><p class="tut">${esc(p)}</p>
      <div class="dots">${TUTORIAL.map((_, k) => `<i class="${k === i ? "on" : ""}"></i>`).join("")}</div>
      <div class="actions"><button class="btn ghost" id="tut-skip">Skip</button><button class="btn gold" id="tut-next">${i < TUTORIAL.length - 1 ? "Next" : "Start watching"}</button></div>`;
    $("#tut-skip").onclick = () => d.close();
    $("#tut-next").onclick = () => { if (i < TUTORIAL.length - 1) { i++; draw(); arm(); } else d.close(); };
  };
  const arm = () => { clearTimeout(timer); timer = setTimeout(() => { if (!d.open) return; if (i < TUTORIAL.length - 1) { i++; draw(); arm(); } else d.close(); }, 7000); };
  draw();
  d.showModal();
  arm();
  await new Promise((r) => d.addEventListener("close", r, { once: true }));
  clearTimeout(timer);
  paused = wasPaused;
  try { localStorage.setItem("gauntlet-tutorial-seen", "1"); } catch { /* private mode */ }
}
$("#tutorial-btn").addEventListener("click", showTutorial);

function maybeTutorial() {
  let seen = false;
  try { seen = localStorage.getItem("gauntlet-tutorial-seen") === "1"; } catch { /* private mode */ }
  if (!seen && !new URLSearchParams(location.search).has("fast")) showTutorial();
}

// ---------- replay + reduced motion ----------

function replay() {
  const p = new URLSearchParams(location.search);
  if (currentQuest) location.href = `${location.pathname}?quest=${encodeURIComponent(currentQuest)}`;
  else location.href = `${location.pathname}?${p.get("file") ? `file=${encodeURIComponent(p.get("file"))}` : "demo"}`;
}
$("#replay").addEventListener("click", replay);

function setReduced(on) {
  reduced = on;
  $("#motion").setAttribute("aria-pressed", String(on));
  document.body.classList.toggle("reduced", on);
  try { localStorage.setItem("gauntlet-reduced", on ? "1" : "0"); } catch { /* private mode */ }
  if (on) { particles = []; }
}
$("#motion").addEventListener("click", () => setReduced(!reduced));
try { const v = localStorage.getItem("gauntlet-reduced"); if (v != null) setReduced(v === "1"); else setReduced(reduced); } catch { setReduced(reduced); }

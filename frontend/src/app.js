// Screen: polls the ledger, folds events through reduce(), redraws.

const $ = (sel) => document.querySelector(sel);
const esc = (t) => String(t ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const GOOD = new Set(["SURVIVOR", "CHAMPION"]);
const WHO = { lanista: "Lanista", sceptic: "Sceptic", engine: "Arena", system: "Arena", emperor: "Decoy", crowd: "Crowd" };

let state = initialState();
let following = 0;

function card(g, sinceSeq) {
  const verdictClass = GOOD.has(g.verdict) ? "good" : "bad";
  const classes = ["card", g.status === "champion" ? "champion" : "",
                   g.bornAt > sinceSeq ? "new" : "", g.hitAt > sinceSeq ? "hit" : ""];
  return `<article class="${classes.join(" ").trim()}" data-id="${g.id}">
    <p class="claim">${esc(g.claim)}</p>
    <div class="chips">${g.features.map((f) => `<span class="chip">${esc(f)}</span>`).join("")}</div>
    <div class="hp ${g.hp <= 50 ? "low" : ""}"><div style="width:${g.hp}%"></div></div>
    ${g.verdict ? `<span class="verdict ${verdictClass}">${GOOD.has(g.verdict) ? "▲" : "▼"} ${esc(g.verdict)}</span>` : ""}
    ${g.last ? `<p class="last">${esc(g.last)}</p>` : ""}
  </article>`;
}

// sinceSeq: cards hit after this ledger seq shake on this redraw.
function render(sinceSeq) {
  $("#day").textContent = state.dayName || "Waiting for the games";
  $("#reputation").textContent = state.reputation;
  $("#rep-bar").style.width = `${Math.max(0, Math.min(100, state.reputation))}%`;
  $("#denarii").textContent = state.denarii;

  for (const lane of document.querySelectorAll(".lane")) {
    const ids = state.order.filter((id) => laneOf(state.gladiators[id]) === lane.dataset.lane);
    lane.querySelector(".cards").innerHTML = ids.map((id) => card(state.gladiators[id], sinceSeq)).join("");
  }

  $("#feed").innerHTML = state.feed.slice(0, 120).map((f) => {
    const mark = f.passed === true ? `<span class="pass">✓</span> ` : f.passed === false ? `<span class="fail">✗</span> ` : "";
    return `<li><span class="who who-${f.actor}">${WHO[f.actor] || f.actor}${f.gid ? " · " + f.gid : ""}</span>${mark}${esc(f.line)}</li>`;
  }).join("");

  const c = counts(state);
  $("#counter").textContent = `${c.fought} fought · ${c.fallen} fallen · ${c.standing} standing`;
  if (state.summary && !$("#summary").open) showSummary(state.summary);
}

function showSummary(sum) {
  const verdicts = Object.entries(sum.verdicts).sort((a, b) => b[1] - a[1])
    .map(([v, n]) => `<tr><td>${esc(v)}</td><td>${n}</td></tr>`).join("");
  const decoys = sum.decoys.map((d) => `<tr><td>${esc(d.feature)}</td><td>${esc(d.verdict || d.status)}</td>
    <td>${d.caught ? "✓ caught" : "✗ missed"}</td></tr>`).join("");
  const emperor = sum.emperor ? `<p>The Emperor's gladiator was <strong>${sum.emperor.toUpperCase()}</strong>.</p>` : "";
  $("#summary").innerHTML = `<h2>The games are over</h2>
    <p>${sum.tested} gladiators fought. Decoys caught: <strong>${sum.caught} of ${sum.total_decoys}</strong>.</p>
    ${emperor}
    <table><tr><th>Verdict</th><th>Count</th></tr>${verdicts}</table>
    <table><tr><th>Decoy</th><th>Fate</th><th></th></tr>${decoys}</table>
    <form method="dialog"><button>Close</button></form>`;
  $("#summary").showModal();
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function follow(runId) {
  const token = ++following;
  state = initialState();
  render(Infinity);
  let after = 0;
  while (token === following) {
    const res = await fetch(`/api/runs/${runId}/events?after=${after}`);
    if (!res.ok) break;
    const body = await res.json();
    for (const e of body.events) reduce(state, e);
    render(after);
    after += body.events.length;
    if (body.done && body.events.length === 0) break;
    await sleep(350);
  }
  loadRuns();
}

async function post(url, data) {
  const res = await fetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(data) });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

async function loadRuns() {
  try {
    const runs = await (await fetch("/api/runs")).json();
    $("#runs").innerHTML = runs.filter((r) => !r.startsWith("t"))  // t* = crowd theories
      .map((r) => `<option>${esc(r)}</option>`).join("");
  } catch {
    $("#runs").innerHTML = "<option value=''>no API</option>";
  }
}

// Offline mode for frontend work: ?file=<path to a ledger .jsonl> plays it with no backend.
async function playFile(url) {
  const text = await (await fetch(url)).text();
  const events = text.trim().split("\n").map((line) => JSON.parse(line));
  state = initialState();
  for (const e of events) {
    const before = e.seq - 1;
    reduce(state, e);
    render(before);
    await sleep(150);
  }
}

// ---------- the roster editor ----------

let rosterDefaults = null;
let roster = null;

function option(value, label, selected) {
  return `<option value="${esc(value)}"${selected ? " selected" : ""}>${esc(label)}</option>`;
}

function renderRoster() {
  if (!roster) return;
  $("#roster-count").textContent = `${ticked(roster)} of max ${roster.max} ticked`;
  $("#roster-list").innerHTML = roster.rows.map((r, i) => `
    <div class="roster-row${r.on ? "" : " off"}" data-row="${i}">
      <input type="checkbox" data-field="on" ${r.on ? "checked" : ""} aria-label="Let this one in">
      <textarea data-field="claim" rows="2" maxlength="200" placeholder="Your hypothesis">${esc(r.claim)}</textarea>
      <button type="button" class="remove" data-action="remove" aria-label="Remove">✕</button>
      <div class="feats">
        <select data-field="f1" aria-label="Feature">${roster.features.map((f) => option(f, f, f === r.f1)).join("")}</select>
        <select data-field="f2" aria-label="Second feature">${option("", "+ no second feature", !r.f2)}${
          roster.features.map((f) => option(f, f, f === r.f2)).join("")}</select>
      </div>
    </div>`).join("") || `<p class="roster-empty">No hypotheses yet. Add one.</p>`;
}

function note(text) {
  $("#roster-note").textContent = text;
  if (text) setTimeout(() => { if ($("#roster-note").textContent === text) $("#roster-note").textContent = ""; }, 3000);
}

async function loadRoster() {
  try {
    rosterDefaults = await (await fetch("/api/roster")).json();
    $("#max-in").value = rosterDefaults.max_in;
    roster = initRoster(rosterDefaults);
    renderRoster();
  } catch {
    $("#roster-list").innerHTML = `<p class="roster-empty">No API, so no roster. Games use the built-in Lanista.</p>`;
  }
}

$("#roster-list").addEventListener("input", (ev) => {
  const row = ev.target.closest(".roster-row");
  if (!row || !roster) return;
  const r = roster.rows[row.dataset.row];
  const field = ev.target.dataset.field;
  if (field === "claim") r.claim = ev.target.value;  // no redraw: keep the cursor where it is
  if (field === "f1" || field === "f2") r[field] = ev.target.value;
});

$("#roster-list").addEventListener("change", (ev) => {
  const row = ev.target.closest(".roster-row");
  if (!row || !roster || ev.target.dataset.field !== "on") return;
  if (ev.target.checked && !canTick(roster)) {
    ev.target.checked = false;
    note(`Only ${roster.max} can enter. Untick one first, or raise the max.`);
    return;
  }
  roster.rows[row.dataset.row].on = ev.target.checked;
  renderRoster();
});

document.addEventListener("click", (ev) => {
  const action = ev.target.dataset.action;
  if (!roster || (action !== "add" && action !== "remove")) return;
  if (action === "add") {
    roster.rows.push({ claim: "", f1: roster.features[1] || roster.features[0], f2: "", on: canTick(roster) });
    renderRoster();
    const boxes = document.querySelectorAll("#roster-list textarea");
    boxes[boxes.length - 1]?.focus();
  } else {
    roster.rows.splice(Number(ev.target.closest(".roster-row").dataset.row), 1);
    renderRoster();
  }
});

$("#max-in").addEventListener("change", () => {
  const n = Math.max(1, Math.min(40, Math.round(Number($("#max-in").value)) || 1));
  $("#max-in").value = n;
  if (roster) { setMax(roster, n); renderRoster(); }
});

$("#roster-reset").addEventListener("click", () => {
  if (!rosterDefaults) return;
  roster = initRoster(rosterDefaults, Number($("#max-in").value) || rosterDefaults.max_in);
  renderRoster();
});

async function loadStatus() {
  try {
    const { claude } = await (await fetch("/api/status")).json();
    $("#who-plays").textContent = claude ? "Claude is playing the Lanista and Sceptic"
                                         : "Scripted players (no API key in .env)";
    $("#who-plays").classList.toggle("on", claude);
  } catch {
    $("#who-plays").textContent = "Offline replay";
  }
}

$("#start").addEventListener("click", async () => {
  $("#start").disabled = true;
  try {
    const lineup = roster ? toPayload(roster) : {};
    const { run_id } = await post("/api/runs", lineup);
    $("#roster").open = false;  // make room for the fight
    await follow(run_id);
  } catch (err) {
    alert(`Could not start: ${err.message}`);
  } finally {
    $("#start").disabled = false;
  }
});

$("#replay").addEventListener("click", async () => {
  const id = $("#runs").value;
  if (!id) return;
  const { run_id } = await post("/api/runs", { replay: id, pace: 0.25 });
  follow(run_id);
});

$("#theory").addEventListener("submit", async (ev) => {
  ev.preventDefault();
  const text = $("#theory-text").value.trim();
  if (!text) return;
  $("#theory-result").textContent = "The crowd's gladiator enters the arena…";
  try {
    const body = await post("/api/theory", { text });
    const lines = body.events.filter((e) => e.line && e.actor !== "system").map((e) => esc(e.line));
    $("#theory-result").innerHTML = `<strong>${esc(body.verdict || "No feature matched")}</strong><br>${lines.join("<br>")}`;
  } catch (err) {
    $("#theory-result").textContent = `Failed: ${err.message}`;
  }
});

loadRuns();
loadRoster();
loadStatus();
const offline = new URLSearchParams(location.search).get("file");
if (offline) playFile(offline);

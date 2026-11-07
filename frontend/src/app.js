// Screen: polls the ledger, folds events through reduce(), redraws.

const $ = (sel) => document.querySelector(sel);
const esc = (t) => String(t ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const GOOD = new Set(["SURVIVOR", "CHAMPION"]);
const WHO = { lanista: "Lanista", sceptic: "Sceptic", engine: "Arena", system: "Arena", emperor: "Emperor", crowd: "Crowd" };

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
  $("#roster-days").innerHTML = roster.days.map((d, di) => {
    const rows = d.rows.map((r, ri) => `
      <div class="roster-row${r.on ? "" : " off"}" data-day="${di}" data-row="${ri}">
        <input type="checkbox" data-field="on" ${r.on ? "checked" : ""} aria-label="Let this one in">
        <textarea data-field="claim" rows="2" maxlength="200" placeholder="Your hypothesis">${esc(r.claim)}</textarea>
        <button type="button" class="remove" data-action="remove" aria-label="Remove">✕</button>
        <div class="feats">
          <select data-field="f1" aria-label="Feature">${d.features.map((f) => option(f, f, f === r.f1)).join("")}</select>
          <select data-field="f2" aria-label="Second feature">${option("", "+ no second feature", !r.f2)}${
            d.catalog.filter((f) => f.name !== "carbs" || d.day === 1).map((f) => option(f.name, f.name, f.name === r.f2)).join("")}</select>
        </div>
      </div>`).join("");
    return `<section class="roster-day">
      <h3>${esc(d.name)}<span>${ticked(roster, di)} of max ${roster.max} in</span></h3>
      ${rows || `<p class="roster-empty">Nobody fights today.</p>`}
      <button type="button" class="roster-add" data-action="add" data-day="${di}">+ Add a hypothesis</button>
    </section>`;
  }).join("");
}

function note(text) {
  $("#roster-note").textContent = text;
  if (text) setTimeout(() => { if ($("#roster-note").textContent === text) $("#roster-note").textContent = ""; }, 3000);
}

async function loadRoster() {
  try {
    const body = await (await fetch("/api/roster")).json();
    rosterDefaults = body;
    roster = initRoster(body.days, Number($("#max-per-day").value) || body.max_per_day);
    renderRoster();
  } catch {
    $("#roster-days").innerHTML = `<p class="roster-empty">No API, so no roster. Games use the built-in Lanista.</p>`;
  }
}

$("#roster-days").addEventListener("input", (ev) => {
  const row = ev.target.closest(".roster-row");
  if (!row || !roster) return;
  const r = roster.days[row.dataset.day].rows[row.dataset.row];
  const field = ev.target.dataset.field;
  if (field === "claim") r.claim = ev.target.value;  // no redraw: keep the cursor where it is
  if (field === "f1" || field === "f2") r[field] = ev.target.value;
});

$("#roster-days").addEventListener("change", (ev) => {
  const row = ev.target.closest(".roster-row");
  if (!row || !roster || ev.target.dataset.field !== "on") return;
  const di = Number(row.dataset.day);
  const r = roster.days[di].rows[row.dataset.row];
  if (ev.target.checked && !canTick(roster, di)) {
    ev.target.checked = false;
    note(`Only ${roster.max} per day. Untick one first, or raise the max.`);
    return;
  }
  r.on = ev.target.checked;
  renderRoster();
});

$("#roster-days").addEventListener("click", (ev) => {
  const action = ev.target.dataset.action;
  if (!action || !roster) return;
  if (action === "add") {
    const di = Number(ev.target.dataset.day);
    const d = roster.days[di];
    d.rows.push({ claim: "", f1: d.features[0], f2: "", on: canTick(roster, di) });
    renderRoster();
    const boxes = document.querySelectorAll(`.roster-row[data-day="${di}"] textarea`);
    boxes[boxes.length - 1]?.focus();
  }
  if (action === "remove") {
    const row = ev.target.closest(".roster-row");
    roster.days[row.dataset.day].rows.splice(Number(row.dataset.row), 1);
    renderRoster();
  }
});

$("#max-per-day").addEventListener("change", () => {
  const n = Math.max(1, Math.min(10, Math.round(Number($("#max-per-day").value)) || 1));
  $("#max-per-day").value = n;
  if (roster) { setMax(roster, n); renderRoster(); }
});

$("#roster-reset").addEventListener("click", () => {
  if (!rosterDefaults) return;
  roster = initRoster(rosterDefaults.days, Number($("#max-per-day").value) || 5);
  renderRoster();
});

$("#seal").addEventListener("click", () => $(".emperor").classList.toggle("sealed"));

$("#start").addEventListener("click", async () => {
  const emperor = document.querySelector("input[name=emperor]:checked").value || null;
  $("#start").disabled = true;
  try {
    const lineup = roster ? toPayload(roster) : {};
    const { run_id } = await post("/api/runs", { emperor, llm: $("#llm").checked, ...lineup });
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
    const body = await post("/api/theory", { text, llm: $("#llm").checked });
    const lines = body.events.filter((e) => e.line && e.actor !== "system").map((e) => esc(e.line));
    $("#theory-result").innerHTML = `<strong>${esc(body.verdict || "No feature matched")}</strong><br>${lines.join("<br>")}`;
  } catch (err) {
    $("#theory-result").textContent = `Failed: ${err.message}`;
  }
});

loadRuns();
loadRoster();
const offline = new URLSearchParams(location.search).get("file");
if (offline) playFile(offline);

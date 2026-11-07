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
  $("#day").textContent = state.dayName || "The gates are opening";
  $("#reputation").textContent = state.reputation;
  $("#rep-bar").style.width = `${Math.max(0, Math.min(100, state.reputation))}%`;
  $("#denarii").textContent = state.denarii;

  for (const lane of document.querySelectorAll(".lane")) {
    const ids = state.order.filter((id) => laneOf(state.gladiators[id]) === lane.dataset.lane);
    lane.querySelector(".cards").innerHTML = ids.map((id) => card(state.gladiators[id], sinceSeq)).join("");
  }

  $("#feed").innerHTML = state.feed.slice(0, 120).map((f) => {
    const mark = f.passed === true ? `<span class="pass">✓</span> ` : f.passed === false ? `<span class="fail">✗</span> ` : "";
    return `<li><span class="who who-${f.actor}">${WHO[f.actor] || f.actor}${f.gid ? " " + f.gid : ""}</span>${mark}${esc(f.line)}</li>`;
  }).join("");

  const c = counts(state);
  $("#counter").textContent = `${c.fought} fought, ${c.fallen} fallen, ${c.standing} standing`;
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
    <form method="dialog"><button value="again" class="open-gates">Fight again</button> <button value="stay">Stay and look</button></form>`;
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
}

async function post(url, data) {
  const res = await fetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(data) });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
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

// ---------- screens ----------

const screens = { title: $("#screen-title"), gate: $("#screen-gate"), arena: $("#screen-arena") };
let stopScene = () => {};

function show(name) {
  stopScene();
  for (const [k, el] of Object.entries(screens)) el.hidden = k !== name;
  if (name === "title") stopScene = animate($("#title-scene"), drawTitle);
  if (name === "gate") { screens.gate.classList.add("ready"); stopScene = animate($("#gate-scene"), (ctx, f) => drawGate(ctx, 0, f)); $("#start").focus(); }
}

// Press play: the gate screen falls in over the title, open, then the portcullis slams shut.
let entering = false;
async function enterGates() {
  if (entering) return;
  if (matchMedia("(prefers-reduced-motion: reduce)").matches) return show("gate");
  entering = true;
  const gate = screens.gate, canvas = $("#gate-scene");
  drawGate(canvas.getContext("2d"), 90, 0);
  gate.classList.add("dropping");
  gate.hidden = false;
  await new Promise((r) => { gate.addEventListener("animationend", r, { once: true }); setTimeout(r, 900); });
  stopScene();
  screens.title.hidden = true;
  gate.classList.remove("dropping");
  await lowerGate(canvas);
  gate.classList.add("slam");
  setTimeout(() => gate.classList.remove("slam"), 400);
  stopScene = animate(canvas, (ctx, f) => drawGate(ctx, 0, f));
  setTimeout(() => { gate.classList.add("ready"); $("#start").focus(); entering = false; }, 300);
}
$("#play").addEventListener("click", enterGates);
// Like a cartridge title screen: Enter or Space starts.
document.addEventListener("keydown", (ev) => {
  if (!screens.title.hidden && (ev.key === "Enter" || ev.key === " ")) { ev.preventDefault(); enterGates(); }
});

// ---------- how many enter ----------

let rosterBody = null;  // the default hypotheses; the first N enter
let most = 12;

function clampCount(n) { return Math.max(1, Math.min(most, Math.round(Number(n)) || 1)); }
function setCount(n) { $("#how-many").value = clampCount(n); }

$("#fewer").addEventListener("click", () => setCount(Number($("#how-many").value) - 1));
$("#more").addEventListener("click", () => setCount(Number($("#how-many").value) + 1));
$("#how-many").addEventListener("change", () => setCount($("#how-many").value));

async function loadRoster() {
  try {
    const body = await (await fetch("/api/roster")).json();
    rosterBody = body;
    most = body.hypotheses.length;
  } catch {
    most = 40;  // no API: the built-in Lanista picks them
  }
  $("#how-many").max = most;
  setCount(most);
}

async function loadStatus() {
  try {
    const { claude } = await (await fetch("/api/status")).json();
    $("#who-plays").textContent = claude ? "Claude plays the Lanista and the Sceptic"
                                         : "Scripted players tonight (no API key in .env)";
  } catch {
    $("#who-plays").textContent = "The arena server isn't running";
  }
}

// Open the gates: plaque drops away, portcullis rises, we walk into the dark of the tunnel.
async function walkThrough() {
  const gate = screens.gate;
  stopScene();
  gate.classList.remove("ready");
  await raiseGate($("#gate-scene"));
  if (matchMedia("(prefers-reduced-motion: reduce)").matches) return;
  gate.classList.add("entering");
  await new Promise((r) => setTimeout(r, 900));
  gate.classList.remove("entering");
  screens.arena.classList.add("arriving");
  setTimeout(() => screens.arena.classList.remove("arriving"), 700);
}

$("#start").addEventListener("click", async () => {
  const n = clampCount($("#how-many").value);
  $("#start").disabled = true;
  try {
    const lineup = rosterBody ? toPayload(initRoster(rosterBody, n)) : { max_in: n };
    const { run_id } = await post("/api/runs", lineup);
    await walkThrough();
    show("arena");
    await follow(run_id);
  } catch (err) {
    $("#who-plays").textContent = `The gates stayed shut: ${err.message}`;
  } finally {
    $("#start").disabled = false;
  }
});

$("#summary").addEventListener("close", () => {
  if ($("#summary").returnValue === "again") show("gate");
});

loadRoster();
loadStatus();
const offline = new URLSearchParams(location.search).get("file");
if (offline) { show("arena"); playFile(offline); } else show("title");

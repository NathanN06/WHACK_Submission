// CHALLENGE THE HERO: the Research Director's console inside the game.
// Opening it pauses the expedition. Every message, evidence check and Mystery Encounter is a ledger row written by
// the server (director.py); this file only sends what the Director typed and plays back what came back.

const DR = { mode: "ASK", wasRunning: true, busy: false, req: {} };

function directorPost(path, body) {
  if (!G.questId) return Promise.reject(new Error("no live quest"));
  return fetch(`/api/quests/${G.questId}/${path}`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
  }).then(async (r) => {
    const j = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(j.detail || r.statusText);
    return j;
  });
}

function newRequestId() {
  return (window.crypto && crypto.randomUUID) ? crypto.randomUUID() : `${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

function liveConsole() { return G.interactive && G.mode === "live" && !G.state.finale && !G.state.bridge; }

// ---------- opening and closing ----------

function openChat() {
  if ($("screen-game").hidden || $("chat-dlg").open) return;
  if (document.querySelector("dialog[open]")) return;
  DR.wasRunning = G.running;
  setRun(false);
  const s = G.state;
  $("chat-portrait").src = portrait("hero");
  $("chat-question").textContent = (s.campaign && s.campaign.question) || "";
  const active = s.order.filter((id) => s.agents[id].status === "active");
  // default to the hero's lead claim, as the server does: the healthiest scroll, the Mechanistic one on a tie
  const pick = active.slice().sort((x, y) => (s.agents[y].hp - s.agents[x].hp) ||
    ((s.agents[y].archetype === "PIONEER") - (s.agents[x].archetype === "PIONEER")))[0];
  $("chat-target").innerHTML = active.map((id) => `<option value="${id}" ${id === pick ? "selected" : ""}>${esc(s.agents[id].name)}</option>`).join("");
  showHypothesis();
  $("chat-note").textContent = liveConsole() ? "The expedition is paused. The hero answers from the Judge's ledger; it never invents a number."
    : "This is a recorded run, so the hero cannot be challenged here. Start the server and choose Begin to talk to the hero live.";
  $("chat-send").disabled = !liveConsole();
  renderChat();
  $("chat-dlg").showModal();
  $("chat-text").focus();
}

function showHypothesis() {
  const a = G.state.agents[$("chat-target").value];
  $("chat-hypothesis").textContent = a ? `${a.name}: "${a.claim}"` : "No scroll survives.";
}

function closeChat() {
  if ($("chat-dlg").open) $("chat-dlg").close();
}

function onChatClosed() {
  $("chat-offer").hidden = true;
  if (DR.wasRunning) setRun(true);
}

// ---------- the transcript and the encounter cards ----------

const CLASS_TONE = { "VERIFIED AND TESTABLE": "ok", "VERIFIED BUT NOT DIRECTLY TESTABLE": "ok", "UNVERIFIED": "warn",
                     "REQUIRES ADDITIONAL EVIDENCE": "warn", "IRRELEVANT": "bad", "INVALID OR INCOMPATIBLE DATA": "bad" };

function renderChat() {
  const s = G.state;
  const rows = s.chat.map((m) => {
    const intake = m.intake && s.intakes.find((x) => x.id === m.intake);
    const myst = m.mystery && s.mysteries[m.mystery];
    return `<li class="msg ${m.who}">
      ${m.who === "hero" ? `<img src="${portrait("hero")}" alt="" width="28" height="28">` : '<span class="you">You</span>'}
      <div><small>${m.who === "hero" ? "The Alchemist" : `Research Director · ${esc((m.mode || "").replace(/_/g, " ").toLowerCase())}`}</small>
        <p>${esc(m.text || "")}</p>
        ${m.url ? `<p class="attach">🔗 ${esc(m.url)}</p>` : ""}${m.filename ? `<p class="attach">📄 ${esc(m.filename)}</p>` : ""}
        ${intake ? intakeCard(intake) : ""}${myst ? mysteryCard(myst) : ""}</div></li>`;
  }).join("");
  const waiting = Object.values(s.mysteries).filter((m) => m.status === "saved" && !s.chat.some((c) => c.mystery === m.id && c.who === "hero"));
  $("chat-log").innerHTML = rows || `<li class="msg empty"><p class="muted">Ask the hero why it chose an ability, dispute an assumption,
    bring a paper, a link or a CSV it has not seen, or propose another explanation. A testable challenge becomes a Mystery Boss.</p></li>`;
  if (waiting.length) $("chat-log").insertAdjacentHTML("beforeend", waiting.map((m) => `<li class="msg hero">${mysteryCard(m)}</li>`).join(""));
  $("chat-log").scrollTop = $("chat-log").scrollHeight;
  for (const b of document.querySelectorAll("#chat-log [data-mact]")) {
    b.onclick = () => mysteryAction(b.dataset.mid, b.dataset.mact);
  }
}

function intakeCard(x) {
  const src = x.source || {};
  const rows = [["Source", `${src.type || ""}${src.host ? ` (${src.host})` : ""}`], ["Weight", src.tier_label],
                ["Publisher", x.publisher], ["Published", x.published], ["Contains", x.contains],
                ["Claim found in source", x.claim_represented == null ? null : x.claim_represented ? "yes" : "no"],
                ["Missing", (x.missing || []).join("; ")], ["Decision time", x.decision_time]].filter(([, v]) => v);
  return `<div class="intake"><strong>Evidence ${esc(x.id)}</strong> <span class="cls ${CLASS_TONE[x.classification] || ""}">${esc(x.classification)}</span>
    <details><summary>Verification record</summary><dl>${rows.map(([k, v]) => `<dt>${esc(k)}</dt><dd>${esc(v)}</dd>`).join("")}</dl>
    ${(x.notes || []).map((n) => `<p class="muted small">${esc(n)}</p>`).join("")}</details></div>`;
}

function mysteryCard(m) {
  const open = m.status === "offered" || m.status === "saved";
  const live = liveConsole();
  const res = m.result ? `<p class="mres ${m.status}">${esc(m.result.line || "")}${m.hp_delta ? ` (${m.hp_delta > 0 ? "+" : ""}${m.hp_delta} HP)` : ""}</p>` : "";
  return `<div class="mcard s-${m.status}">
    <div class="mhead"><canvas class="pixel boss-mini" data-boss="${esc(m.key || "")}" width="48" height="40"></canvas>
      <div><small>${m.status === "offered" ? "MYSTERY ENCOUNTER DISCOVERED" : m.secret ? "SECRET RESEARCH LEVEL" : `Mystery ${esc(m.id)}`}</small>
      <strong>${esc(m.boss)}</strong> <em class="mstatus">${esc(m.status)}</em>
      ${m.question ? `<p>${esc(m.question)}</p>` : ""}${m.test ? `<p class="muted small">Test: ${esc(m.test)}</p>` : ""}
      ${m.reason ? `<p class="muted small">${esc(m.reason)}</p>` : ""}</div></div>${res}
    ${open ? `<div class="mbtns">
      <button class="btn small gold" data-mid="${m.id}" data-mact="summon" ${live ? "" : "disabled"}>${m.secret ? "Enter the secret level" : "Summon boss now"}</button>
      ${m.status === "offered" ? `<button class="btn small" data-mid="${m.id}" data-mact="save" ${live ? "" : "disabled"}>Save for later</button>` : ""}
      <button class="btn small ghost" data-mid="${m.id}" data-mact="explain" ${live ? "" : "disabled"}>Ask for explanation</button>
      <button class="btn small ghost" data-mid="${m.id}" data-mact="cancel" ${live ? "" : "disabled"}>Cancel</button></div>` : ""}
  </div>`;
}

function paintMiniBosses() {
  for (const c of document.querySelectorAll("canvas.boss-mini")) {
    const key = c.dataset.boss, ctx = c.getContext("2d");
    ctx.imageSmoothingEnabled = false; ctx.clearRect(0, 0, c.width, c.height);
    if (!key || !BOSSES[key]) { pixelText(ctx, "?", 24, 14, "#e8b847"); continue; }
    ctx.save(); ctx.translate(24, 39); ctx.scale(0.62, 0.62); BOSSES[key](ctx, 0, 0, G.f, false); ctx.restore();
  }
}

// ---------- sending ----------

function readFile(file) {
  return new Promise((resolve, reject) => {
    if (file.size > 1_000_000) { reject(new Error("Files over 1 MB are refused.")); return; }
    const r = new FileReader();
    r.onload = () => resolve({ name: file.name, content_b64: String(r.result).split(",", 2)[1] || "" });
    r.onerror = () => reject(new Error("The file could not be read."));
    r.readAsDataURL(file);
  });
}

async function sendChat(ev) {
  ev.preventDefault();
  if (DR.busy || !liveConsole()) return;
  const text = $("chat-text").value.trim(), url = $("chat-url").value.trim(), f = $("chat-file").files[0];
  if (!text && !url && !f) { $("chat-note").textContent = "Type a message, add a link or attach a file."; return; }
  DR.busy = true;
  $("chat-send").disabled = true; $("chat-send").textContent = "…";
  $("chat-note").textContent = DR.mode === "ADD_EVIDENCE" ? "Checking the source and its provenance…" : "The hero is thinking…";
  try {
    const file = f ? await readFile(f) : null;
    const out = await directorPost("chat", { mode: DR.mode, text, url: url || null, file, level: Math.min(4, G.state.level || 1),
                                             target: $("chat-target").value || null, request_id: newRequestId() });
    for (const e of out.events) apply(e, true);
    $("chat-text").value = ""; $("chat-url").value = ""; $("chat-file").value = "";
    $("chat-note").textContent = out.mystery && out.mystery.status === "offered"
      ? "A testable challenge: summon the boss now, save it for later, or ask for an explanation." : "";
    renderAll(); renderChat();
  } catch (err) {
    $("chat-note").textContent = `The message did not reach the hero: ${String(err.message || err).slice(0, 200)}`;
  } finally {
    DR.busy = false; $("chat-send").disabled = !liveConsole(); $("chat-send").textContent = "Send";
  }
}

async function mysteryAction(id, action) {
  if (DR.busy || !liveConsole()) return;
  DR.busy = true;
  const key = `${id}:${action}`;
  DR.req[key] = DR.req[key] || newRequestId();   // a double click sends the same request id: one fight, not two
  for (const b of document.querySelectorAll(`#chat-log [data-mid="${id}"]`)) b.disabled = true;
  try {
    const out = await directorPost(`mystery/${id}`, { action, level: Math.min(4, G.state.level || 1), request_id: DR.req[key] });
    const fresh = out.events.filter((e) => !G.seen.has(e.seq));
    if (action === "summon") {
      DR.wasRunning = true;
      G.pending.unshift(...fresh);   // the boss fight plays next, then the dungeon resumes where it paused
      closeChat();
      banner(out.mystery.secret ? "A secret portal opens" : "Mystery Encounter", out.mystery.boss);
    } else {
      for (const e of fresh) apply(e, true);
      renderAll(); renderChat();
    }
  } catch (err) {
    $("chat-note").textContent = String(err.message || err).slice(0, 200);
    renderChat();
  } finally {
    DR.busy = false;
  }
}

// ---------- reacting to ledger rows ----------

function directorEvent(e) {
  const r = e.result || {};
  if (e.action === "mystery_encounter" && r.enemy) banner(r.enemy.name, r.enemy.boss ? "MYSTERY BOSS" : "Secret obstacle");
  if (e.action === "secret_level_start") {
    $("secret-badge").hidden = false;
    $("secret-badge").textContent = `Secret level: ${r.secret.name}`;
    banner("SECRET RESEARCH LEVEL", r.secret.name);
  }
  if (e.action === "secret_level_complete") $("secret-badge").hidden = true;
  if (e.action === "mystery_result" && r.outcome && r.outcome !== "MEASURED") {
    banner({ SURVIVED: "The claim survives", FALLEN: "A weakness exposed", UNRESOLVED: "Unresolved Encounter" }[r.outcome] || r.outcome,
           (r.mystery && r.mystery.boss) || "");
  }
  if (e.action === "level_start" || e.action === "bridge_enter") $("challenge").hidden = e.action === "bridge_enter";
  if ($("chat-dlg").open) renderChat();
}

function wireDirector() {
  $("challenge").onclick = openChat;
  $("chat-close").onclick = closeChat;
  $("chat-dlg").addEventListener("close", onChatClosed);
  $("chat-form").onsubmit = sendChat;
  $("chat-target").onchange = showHypothesis;
  $("chat-text").addEventListener("keydown", (ev) => { if (ev.key === "Enter" && !ev.shiftKey) { ev.preventDefault(); $("chat-form").requestSubmit(); } });
  for (const b of document.querySelectorAll(".mode")) {
    b.onclick = () => {
      DR.mode = b.dataset.mode;
      for (const o of document.querySelectorAll(".mode")) o.setAttribute("aria-pressed", String(o === b));
      $("chat-text").placeholder = {
        ASK: "Why did you buy Bias Detection for this scroll?",
        CHALLENGE: "Does this hold in the rural sites, or is it a winter effect?",
        ADD_EVIDENCE: "A new study claims… (add the link or a CSV with treated and event columns)",
        NEW_HYPOTHESIS: "Maybe it is really testosterone use, not the drug.",
        SUMMON: "Could this just be luck?",
      }[DR.mode];
    };
  }
  document.addEventListener("keydown", (ev) => {
    if (ev.key.toLowerCase() === "c" && !$("screen-game").hidden && !ev.target.matches("input, select, textarea")
        && !document.querySelector("dialog[open]") && !ev.ctrlKey && !ev.metaKey) { ev.preventDefault(); openChat(); }
  });
  const tick = () => { if ($("chat-dlg").open) paintMiniBosses(); requestAnimationFrame(tick); };
  tick();
}

wireDirector();

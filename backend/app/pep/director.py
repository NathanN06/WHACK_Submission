"""The Research Director's console: in-game research chat, evidence intake, Mystery Bosses and Secret Levels.

The user is the Research Director. At any point in the four dungeons they can pause the expedition and talk to
the hero: ask, challenge, add evidence, propose a hypothesis, or summon a Mystery Boss. This module routes each
message (QuestionRouter, in challenges.py), records it in the append-only Evidence Ledger, verifies submitted
evidence (evidence.py), and turns a testable challenge into a Mystery Encounter whose outcome is decided by a
registered, deterministic test (challenges.py). It never asks a language model for a number.

The quest thread pauses at a checkpoint after each level until the screen has finished showing it, so a Mystery
Boss always fights the scroll as it stands at the end of the level the Director is watching. Mystery tests read
the training cohort only; the Level IV holdout and the second vault are never touched here.
"""

from __future__ import annotations

import hashlib
import json
import math
import threading
import time

import numpy as np
from scipy import stats

from . import challenges as C
from . import evidence as EV
from . import rules

MODES = ("ASK", "CHALLENGE", "ADD_EVIDENCE", "NEW_HYPOTHESIS", "SUMMON")
OPEN = ("offered", "saved")                 # waiting for the Director
UNRESOLVED = ("offered", "saved", "unresolved")
WAIT_LIMIT = 3600                           # an abandoned expedition stops after an hour at a checkpoint

SECRET = {"name": "The Sunken Vault", "theme": "a flooded archive beneath the dungeon, opened by new data",
          "obstacles": [{"key": "m_golem", "name": "The Schema Golem", "test": "Data audit: usable rows, both arms, events"},
                        {"key": "m_chance", "name": "The Probability Phantom", "test": "Fisher's exact test on the new data"}],
          "boss": {"key": "m_replication", "name": "The Replication Revenant",
                   "test": "Does the new data agree with the hero's estimate? Heterogeneity z-test on the log risk ratios"}}


class DirectorError(Exception):
    """A request the console must refuse (the message says why)."""


class Expedition:
    """Everything the Director has done in one quest. Attach with Expedition(quest)."""

    def __init__(self, quest, interactive: bool = True, fetch=None):
        self.q = quest
        quest.director = self
        self.interactive = interactive
        self.fetch = fetch
        self.cv = threading.Condition()
        self.advanced = 0
        self.choice: dict | None = None
        self.waiting: str | None = None
        self.intakes: list[dict] = []
        self.mysteries: dict[str, dict] = {}
        self.secret_levels: list[dict] = []
        self._responses: dict[str, dict] = {}
        self._req_lock = threading.Lock()

    # ---------- pacing: the quest waits for the screen ----------

    def checkpoint(self, level: int) -> None:
        if not self.interactive:
            return
        self._wait(lambda: self.advanced >= level, f"level {level}")

    def advance(self, level: int) -> dict:
        with self.cv:
            self.advanced = max(self.advanced, int(level))
            self.cv.notify_all()
        return {"advanced": self.advanced}

    def wait_choice(self, assessment: dict) -> dict:
        """Block the quest thread at the Bridge until the Director chooses (interactive) or follow the hero."""
        if not self.interactive:
            return {"choice": assessment["recommendation"]["choice"], "by": "autopilot"}
        with self.cv:
            self.choice = None
        self._wait(lambda: self.choice is not None, "bridge", assessment)
        return self.choice

    def choose(self, choice: str, request_id: str | None = None) -> dict:
        def go():
            with self.cv:
                if self.waiting != "bridge":
                    raise DirectorError("The hero is not standing at the Bridge of Judgment.")
                opts = self._assessment["options"]
                if choice not in opts:
                    raise DirectorError(f"Unknown choice {choice!r}.")
                if not opts[choice]["enabled"]:
                    raise DirectorError(opts[choice]["reason"])
                self.choice = {"choice": choice, "by": "director"}
                self.cv.notify_all()
            return {"accepted": choice}
        return self._once(request_id, go)

    def _wait(self, ready, what: str, assessment: dict | None = None) -> None:
        from .campaign import QuestStopped
        start = time.time()
        with self.cv:
            self.waiting = what
            if assessment is not None:
                self._assessment = assessment
            while not ready():
                if self.q._stop:
                    raise QuestStopped
                if time.time() - start > WAIT_LIMIT:
                    self.q._stop = True
                    raise QuestStopped
                self.cv.wait(0.25)
            self.waiting = None

    # ---------- the chat ----------

    def chat(self, req: dict) -> dict:
        return self._once(req.get("request_id"), lambda: self._chat(req))

    def _chat(self, req: dict) -> dict:
        mode = (req.get("mode") or "ASK").upper()
        if mode not in MODES:
            raise DirectorError(f"Unknown mode {mode!r}.")
        text = (req.get("text") or "").strip()
        if not text and not req.get("url") and not req.get("file"):
            raise DirectorError("Say something, add a link or attach a file.")
        q = self.q
        with q.lock:
            first = len(q.ledger.events)
            level = self._level(req.get("level"))
            a = self._target(req.get("target"))
            f = req.get("file") or {}
            q._emit(level=level, actor="director", action="chat",
                    line=f"Research Director ({mode.replace('_', ' ').title()}): {text or req.get('url') or f.get('name')}"[:300],
                    result={"mode": mode, "text": text[:2000], "url": req.get("url"), "filename": f.get("name"),
                            "target": a.id if a else None, "speaker": "director"})
            route = C.route(text)
            out: dict = {"mode": mode, "route": {k: v for k, v in route.items() if k != "scores"}}
            if mode == "ASK":
                reply = self.answer(a, level, text, route)
            elif mode == "ADD_EVIDENCE":
                reply = self._evidence(a, level, text, req, route, out)
            elif mode == "NEW_HYPOTHESIS":
                reply = self._hypothesis(a, level, text, route, out)
            else:  # CHALLENGE, SUMMON
                reply = self._challenge(a, level, text, route, out, source=mode.lower())
            q._emit(level=level, actor="system", action="hero_reply", line=reply[:600],
                    result={"speaker": "hero", "text": reply, "mode": mode, "target": a.id if a else None,
                            "intake": (out.get("intake") or {}).get("id"), "mystery": (out.get("mystery") or {}).get("id")})
            out["reply"] = reply
            out["events"] = [e.model_dump() for e in q.ledger.events[first:]]
            return _plain(out)

    def answer(self, a, level: int, text: str, route: dict) -> str:
        """The hero explains itself from the ledger and the Judge's measurements, never beyond them."""
        q, t = self.q, (text or "").lower()
        if a is None:
            return "Every scroll I carried has shattered. I can explain what broke them, but there is no claim left to defend."
        done = [lv for lv in (1, 2, 3, 4) if lv < level and lv in a.m]
        decisions = {e.level: e for e in q.ledger.events if e.action == "decision" and e.agent_id == a.id and e.level <= level}
        parts = [f"I am carrying {a.name}: \"{a.claim}\""]
        if any(k in t for k in ("why", "ability", "abilities", "spend", "spent", "credit", "buy", "chose", "choose", "decid", "cast")):
            for lv, e in sorted(decisions.items()):
                picks = (e.result or {}).get("abilities") or []
                names = ", ".join(rules.ABILITIES[k]["name"] for k in picks) or "nothing"
                parts.append(f"In {rules.LEVELS[lv]['name']} I cast {names} ({e.cost or 0} credits). My reasoning: "
                             f"\"{e.line}\" {e.explain or ''}".strip())
            if len(parts) == 1:
                parts.append("I have not had to choose any abilities for this scroll yet.")
        elif any(k in t for k in ("hp", "damage", "hurt", "integrity", "health")):
            hist = ", ".join(f"after {rules.LEVELS[lv]['name']}: {hp}" for lv, hp in sorted(a.hp_by_level.items()) if lv < level)
            parts.append(f"HP measures research integrity, not whether the claim is true. {hist or 'No level is finished yet.'}")
        else:
            facts = self.facts(a, done)
            parts.append(" ".join(facts) if facts else "The Judge has not measured this scroll yet in this run.")
        if level <= 4:
            parts.append(f"Here in {rules.LEVELS[level]['name']} the trap is: {rules.LEVELS[level]['trap']}")
        open_ = [m for m in self.mysteries.values() if m["status"] in UNRESOLVED]
        if open_:
            parts.append(f"{len(open_)} of your challenges are still unresolved in the ledger; I will review them at the Bridge.")
        if route.get("archetype"):
            parts.append(f"That sounds like a challenge ({C.ARCHETYPES[route['archetype']]['question']}) "
                         "Switch to CHALLENGE and I will put it to a registered test.")
        return " ".join(parts)

    def facts(self, a, levels) -> list[str]:
        out = []
        for lv in levels:
            m = a.m[lv]
            if lv == 1:
                out.append(f"Rumours: affiliate skew {m['phi']:.2f}, {m['n_eff']} independent stories.")
            elif lv == 2:
                out.append(f"Archives: rate ratio {m['naive']['rr']:.2f} naive, {m['adjusted']['rr']:.2f} adjusted; "
                           f"{m['tau'] * 100:.0f}% of the supporting papers are non-human.")
            elif lv == 3:
                out.append(f"Temple: best of K = {m['K']} with p_raw {m['p_raw']:.2g}, Sidak {m['p_corr']:.2g}; "
                           f"replicated in {len(m['replicating'])} of {len(m['sites'])} sites; {m['n_rct']} completed RCTs.")
            elif lv == 4 and m.get("ss_oos") is not None:
                out.append(f"Citadel: SS_oos {m['ss_oos']:+.4f} on the vaulted holdout (paired p {m['p_dm']:.3g}).")
        return out

    def _challenge(self, a, level, text, route, out, source) -> str:
        if a is None:
            return "Every scroll has shattered, so there is no claim left to challenge."
        arch = route.get("archetype")
        if not arch:
            m = self._new_mystery(a, level, text, None, source, status="unresolved",
                                  reason="It does not map to any registered test yet. Name the weakness: chance, "
                                         "confounding, season, sites, leakage, replication or added value.")
            out["mystery"] = m
            return ("I hear the objection, but I cannot match it to a test I am allowed to run, so I will not pretend "
                    f"to answer it. I have logged it as unresolved challenge {m['id']}. " + m["reason"])
        m = self._new_mystery(a, level, text, arch, source, covariate=route.get("covariate"),
                              unmeasured=route.get("unmeasured"))
        out["mystery"] = m
        lead = {"challenge": "A fair challenge.", "summon": "You want it settled in battle."}.get(source, "Noted.")
        if route.get("unmeasured"):
            return (f"{lead} You point at {route['unmeasured']}, which this cohort never measured. I can still summon "
                    f"{m['boss']}, but it can only end as an Unresolved Encounter; it stays in the ledger as {m['id']}.")
        return (f"{lead} {C.ARCHETYPES[arch]['question']} The Gatekeeper proposes: {C.ARCHETYPES[arch]['test']}. "
                f"MYSTERY ENCOUNTER DISCOVERED: {m['boss']} ({m['id']}). Summon it now, save it for later, or ask me to explain.")

    def _hypothesis(self, a, level, text, route, out) -> str:
        if a is None:
            return "Every scroll has shattered; a new hypothesis would need a new expedition."
        if route.get("covariate") or route.get("unmeasured"):
            route = {**route, "archetype": "confounder"}
            return "An alternative explanation. " + self._challenge(a, level, text, route, out, "new hypothesis")
        t = (text or "").lower()
        other = next((o for o in self.q.c.outcomes if o.key != a.st.outcome and
                      any(w in t for w in EV.words(o.label) - {"within", "year", "any", "recorded"})), None)
        if other:
            m = self._new_mystery(a, level, text, "chance", "new hypothesis", outcome=other.key)
            out["mystery"] = m
            return (f"A new claim about {other.label.lower()}. Before I carry it, it must survive chance in our own cohort, "
                    f"Sidak-corrected for the search it adds. MYSTERY ENCOUNTER DISCOVERED: {m['boss']} ({m['id']}).")
        if route.get("archetype"):
            return self._challenge(a, level, text, route, out, "new hypothesis")
        m = self._new_mystery(a, level, text, None, "new hypothesis", status="unresolved",
                              reason="This campaign's data has no variable that can test it.")
        out["mystery"] = m
        return (f"Interesting, but I have no measured variable or registered test that can examine it here. It is "
                f"preserved as unresolved quest {m['id']}; I will not invent an answer.")

    def _evidence(self, a, level, text, req, route, out) -> str:
        q = self.q
        f = req.get("file") or {}
        sub = {"text": text, "url": req.get("url"), "filename": f.get("name"), "content_b64": f.get("content_b64")}
        if f.get("name") and not text:
            route = C.route("")
        rec = EV.intake(sub, {"campaign": q.c, "target": a.id if a else None, "level": level}, route, self.fetch)
        rec["id"] = f"X{len(self.intakes) + 1:02d}"
        rec["target_name"] = a.name if a else None
        self.intakes.append(rec)
        out["intake"] = EV.public(rec)
        q._emit(level=level, actor="system", action="evidence_intake",
                line=f"Evidence {rec['id']} ({rec['source']['type']}): {rec['classification']}",
                explain=("; ".join(rec["missing"]) or "Recorded with its provenance.")[:400], result={"intake": EV.public(rec)})
        cls = rec["classification"]
        src = rec["source"]
        said = [f"I logged your evidence as {rec['id']}: {cls}."]
        if src.get("tier_label"):
            said.append(f"It is {src['tier_label']}.")
        if rec["missing"]:
            said.append("Missing: " + "; ".join(rec["missing"]) + ".")
        if cls in ("IRRELEVANT", "INVALID OR INCOMPATIBLE DATA"):
            said.append("I cannot use it for this question, and I have not added it to my research context.")
            return " ".join(said)
        if cls != "VERIFIED AND TESTABLE":
            said.append("A claim I cannot verify stays in the ledger with that label; I will not treat its reported result as fact.")
        if rec.get("_data") and cls == "VERIFIED AND TESTABLE" and a is not None:
            m = self._new_mystery(a, level, text or f"New dataset {rec['filename']}", "secret", "evidence",
                                  intake=rec["id"])
            out["mystery"] = m
            said.append(f"It is a genuinely new dataset, so it opens a SECRET RESEARCH LEVEL: {SECRET['name']}, ending in "
                        f"{SECRET['boss']['name']} ({m['id']}).")
            return " ".join(said)
        if route.get("archetype") and a is not None:
            m = self._new_mystery(a, level, text, route["archetype"], "evidence", intake=rec["id"],
                                  covariate=route.get("covariate"), unmeasured=route.get("unmeasured"))
            out["mystery"] = m
            said.append(f"Whatever the source proves, the weakness it points at can be tested on our own cohort: "
                        f"{C.ARCHETYPES[route['archetype']]['question']} MYSTERY ENCOUNTER DISCOVERED: {m['boss']} ({m['id']}).")
        elif a is not None:
            m = self._new_mystery(a, level, text or rec.get("url") or "", None, "evidence", status="unresolved",
                                  intake=rec["id"], reason="No registered test in this campaign can examine it directly.")
            out["mystery"] = m
            said.append(f"No registered test can examine it here, so it stays an unresolved quest ({m['id']}).")
        return " ".join(said)

    # ---------- Mystery Encounters ----------

    def _new_mystery(self, a, level, text, archetype, source, status="offered", reason=None, intake=None,
                     covariate=None, unmeasured=None, outcome=None) -> dict:
        n = len(self.mysteries) + 1
        info = C.ARCHETYPES.get(archetype) if archetype in C.ARCHETYPES else None
        if archetype == "secret":
            info = {"boss": SECRET["boss"]["name"], "key": SECRET["boss"]["key"], "question": "Does a new dataset agree with the hero?",
                    "test": SECRET["boss"]["test"], "rule": "survives if the new data shows the claimed direction (p < 0.05) and "
                    "does not differ significantly from the hero's estimate"}
        m = {"id": f"M{n:02d}", "status": status, "archetype": archetype, "boss": info["boss"] if info else "Unresolved Encounter",
             "key": info["key"] if info else None, "question": info["question"] if info else None,
             "test": info["test"] if info else None, "rule": info.get("rule") if info else None,
             "text": (text or "")[:500], "source": source, "intake": intake, "raised_level": level,
             "target": a.id, "target_name": a.name, "covariate": covariate, "unmeasured": unmeasured, "outcome": outcome,
             "reason": reason, "result": None, "resolved_level": None, "resolved_by": None, "hp_delta": None,
             "secret": archetype == "secret", "raised_seq": len(self.q.ledger.events)}
        self.mysteries[m["id"]] = m
        self.q._emit(level=level, actor="system", action="mystery_offer" if status == "offered" else "mystery_unresolved",
                     line=(f"Mystery Encounter {m['id']} discovered: {m['boss']}" if status == "offered" else
                           f"Unresolved challenge {m['id']} preserved in the ledger"),
                     explain=m["question"] or reason, result={"mystery": dict(m)})
        return m

    def mystery(self, mid: str, action: str, request_id: str | None = None, level: int | None = None) -> dict:
        return self._once(request_id, lambda: self._mystery(mid, action.lower(), level))

    def _mystery(self, mid: str, action: str, level: int | None) -> dict:
        q = self.q
        m = self.mysteries.get(mid)
        if m is None:
            raise DirectorError(f"No mystery encounter {mid}.")
        with q.lock:
            first = len(q.ledger.events)
            lv = self._level(level)
            if action == "explain":
                q._emit(level=lv, actor="system", action="hero_reply", line=self.explain(m)[:600],
                        result={"speaker": "hero", "text": self.explain(m), "mystery": mid})
            elif action in ("save", "cancel"):
                if m["status"] not in OPEN:
                    raise DirectorError(f"{mid} is already {m['status']}.")
                m["status"] = "saved" if action == "save" else "cancelled"
                q._emit(level=lv, actor="director", action="mystery_" + m["status"],
                        line=f"{mid} {'saved for later' if action == 'save' else 'cancelled'} by the Research Director.",
                        result={"mystery": dict(m)})
            elif action == "summon":
                if m["status"] not in OPEN:
                    raise DirectorError(f"{mid} is already {m['status']}: a boss can be fought once.")
                self.fight(m, lv)
            else:
                raise DirectorError(f"Unknown action {action!r}.")
            return _plain({"mystery": dict(m), "events": [e.model_dump() for e in q.ledger.events[first:]]})

    def explain(self, m: dict) -> str:
        if not m["archetype"]:
            return f"{m['id']} could not be matched to a registered test. {m.get('reason') or ''}".strip()
        hp = rules.MYSTERY_HP
        return (f"{m['boss']} asks: {m['question']} The test: {m['test']}. The claim {m['rule']}. The Judge runs it on the "
                f"training cohort only; the vaults stay closed. If the claim survives, the scroll gains {hp['SURVIVED']} HP for a "
                f"meaningful extra test; if the boss exposes a weakness, it loses {-hp['FALLEN']} HP "
                f"({-hp['FALLEN_LEAKAGE']} for future-information leakage); if no valid test can run, nothing changes "
                "and the encounter stays unresolved.")

    def fight(self, m: dict, level: int, version: str = "V1") -> dict:
        """The Mystery Boss research loop. The registered test decides the outcome; the rules decide the HP."""
        q = self.q
        a = q.agents[m["target"]]
        state = {"hp": a.hp, "credits": a.credits, "design": a.st.design, "adjusted": a.st.adjusted, "K": a.st.K,
                 "outcome": a.st.outcome, "level": level}
        digest = hashlib.sha256(json.dumps(state, sort_keys=True).encode()).hexdigest()[:12]
        m["status"] = "summoned"
        q._emit(level=level, actor="system", action="mystery_summon", agent=a,
                line=f"The expedition pauses. {m['boss']} rises to challenge {a.name}.",
                explain=f"Game and research state saved (state {digest}).", result={"mystery": dict(m), "state": state})
        spec = {"challenge": m["question"], "archetype": m["archetype"], "target": a.id, "claim": a.claim,
                "outcome": m.get("outcome") or a.st.outcome, "design": a.st.design, "adjusted": a.st.adjusted, "K": a.st.K,
                "data": "training cohort only (index day < 1100)", "covariate": m.get("covariate"), "unmeasured": m.get("unmeasured"),
                "raised_by": m["source"], "intake": m.get("intake")}
        if m["secret"]:
            return self._secret(m, a, level, spec)
        q._emit(level=level, actor="system", action="gatekeeper",
                line=f"Gatekeeper: \"I choose the test for {m['boss']}: {m['test']}. Your claim {m['rule']}.\"",
                result={"speaker": "gatekeeper", "text": f"I choose the test: {m['test']}. Your claim {m['rule']}.",
                        "level": level, "spec": spec, "registry": m["archetype"] in C.TESTS})
        info = C.ARCHETYPES[m["archetype"]]
        q._emit(level=level, actor="judge", action="mystery_encounter", enemy=info["key"],
                line=f"{info['boss']}: \"{info['attack']}\"",
                result={"enemy": {"key": info["key"], "name": info["boss"], "test": info["test"], "attack": info["attack"],
                                  "boss": True, "mystery": True}, "boss": True, "mystery": m["id"]})
        q._emit(level=level, actor="system", action="mystery_ability", agent=a,
                line=f"The Alchemist raises {a.name} and casts {info['ability']}.", result={"ability": info["ability"]})
        res = C.run(q.w, a, m["archetype"], spec)
        return self._resolve(m, a, level, res, version)

    def _resolve(self, m: dict, a, level: int, res: dict, version: str, enemy_key: str | None = None) -> dict:
        q = self.q
        outcome = res["outcome"]
        key = "FALLEN_LEAKAGE" if outcome == "FALLEN" and res.get("leakage") else outcome
        delta = max(-rules.MYSTERY_D_MAX, rules.MYSTERY_HP[key])
        before = a.hp
        a.hp = max(0, min(rules.STARTING_HP, a.hp + delta))
        applied = a.hp - before
        m.update(status={"SURVIVED": "survived", "FALLEN": "fallen", "UNRESOLVED": "unresolved"}[outcome],
                 result=_plain({k: res[k] for k in ("outcome", "line", "plain", "numbers", "rule")}), resolved_level=level,
                 resolved_by=version, hp_delta=applied)
        if outcome == "UNRESOLVED":
            m["reason"] = res["line"]
        q._enc += 1
        enc = {"encounterId": f"E{q._enc:03d}", "campaignType": q.c.id, "level": level, "enemyName": m["boss"],
               "trapType": "MYSTERY_" + (m["archetype"] or "UNRESOLVED").upper(), "scrollId": a.id, "scrollTitle": a.name,
               "heroAction": (C.ARCHETYPES.get(m["archetype"]) or {}).get("ability", "NONE"), "mysteryId": m["id"],
               "raisedBy": m["source"], "intake": m.get("intake"),
               "combatResolution": {"outcome": outcome, "hpRule": f"MYSTERY_HP[{key}] = {rules.MYSTERY_HP[key]:+d}",
                                    "clampedHpDelta": applied, "plainEnglishVerdict": res["plain"]}}
        m["encounter"] = enc["encounterId"]
        verdict = {"SURVIVED": "The claim survives", "FALLEN": "The boss exposes a weakness",
                   "UNRESOLVED": "Unresolved Encounter"}[outcome]
        q._emit(level=level, actor="judge", action="mystery_result", agent=a, enemy=enemy_key or m["key"], hp_delta=applied,
                passed=None if outcome == "UNRESOLVED" else outcome == "SURVIVED",
                line=f"{verdict}: {res['line']}"[:400], explain=res["plain"], encounter=enc,
                payload={"numbers": res["numbers"], "chart": res.get("chart"), "formula": res["rule"], "outcome": outcome,
                         "mystery": dict(m), "mystery_id": m["id"], "version": version})
        if a.hp <= 0 and a.active:
            a.status, a.verdict = "shattered", "SHATTERED"
            q._emit(level=level, actor="judge", action="shatter", agent=a, enemy=m["key"],
                    line=f"{a.name} shatters before {m['boss']}.", explain=rules.VERDICTS["SHATTERED"])
        q._emit(level=level, actor="system", action="mystery_return",
                line=(f"The hero returns to {rules.LEVELS[level]['name']}." if level in rules.LEVELS else "The hero returns."),
                result={"mystery": dict(m)})
        return m

    # ---------- the Secret Research Level ----------

    def _secret(self, m: dict, a, level: int, spec: dict) -> dict:
        q = self.q
        rec = next(r for r in self.intakes if r["id"] == m["intake"])
        data = rec["_data"]
        t = np.array(data["treated"], dtype=int)
        y = np.array(data["event"], dtype=int)
        sl = {"id": f"S{len(self.secret_levels) + 1:02d}", "mystery": m["id"], "intake": rec["id"], "level": level,
              "name": SECRET["name"], "theme": SECRET["theme"], "steps": []}
        self.secret_levels.append(sl)
        q._emit(level=level, actor="system", action="secret_level_start",
                line=f"A secret portal opens: {SECRET['name']}, built from {rec['filename']}.",
                explain=SECRET["theme"], result={"secret": sl, "spec": spec})
        # Obstacle 1: the Schema Golem audits the data. It measures; it deals no damage.
        n1, n0 = int(t.sum()), int((1 - t).sum())
        e1, e0 = int(y[t == 1].sum()), int(y[t == 0].sum())
        audit_ok = n1 >= 10 and n0 >= 10 and (e1 + e0) >= 5
        self._obstacle(a, level, SECRET["obstacles"][0], audit_ok,
                       f"{len(t)} usable rows ({rec['dataset']['dropped']} dropped): {n1} treated with {e1} events, "
                       f"{n0} untreated with {e0} events.",
                       "Enough data in both arms to test." if audit_ok else "Too little data in one arm to test anything.",
                       {"rows": len(t), "treated": n1, "untreated": n0, "events_treated": e1, "events_untreated": e0})
        sl["steps"].append({"obstacle": "Schema Golem", "passed": audit_ok})
        if not audit_ok:
            res = C.unresolved("The new dataset is too small in one arm to run a test, so this becomes an unresolved quest.")
            self._resolve(m, a, level, res, "V1")
            sl["outcome"] = "UNRESOLVED"
            q._emit(level=level, actor="system", action="secret_level_complete", line=f"{SECRET['name']}: unresolved quest.",
                    result={"secret": sl})
            return m
        # Obstacle 2: is there any effect in the new data at all? Fisher's exact test, one-sided in the claimed direction.
        d = a.st.direction   # the claim's own direction
        _, p_fisher = stats.fisher_exact([[e1, n1 - e1], [e0, n0 - e0]], alternative="less" if d < 0 else "greater")
        r1, r0 = e1 / n1, e0 / n0
        self._obstacle(a, level, SECRET["obstacles"][1], p_fisher < rules.ALPHA,
                       f"Risk {r1 * 100:.1f}% treated vs {r0 * 100:.1f}% untreated; Fisher's exact p = {p_fisher:.3g} (one-sided).",
                       "The new data shows the claimed effect on its own." if p_fisher < rules.ALPHA else
                       "The new data alone does not show the claimed effect.",
                       {"risk_treated": r1, "risk_untreated": r0, "p_fisher": float(p_fisher)})
        sl["steps"].append({"obstacle": "Probability Phantom", "passed": bool(p_fisher < rules.ALPHA)})
        # Final boss: does the new data agree with the hero's own estimate (crude one-year risk ratio, new users, training)?
        nu = q.w.new_user(a.st.outcome, C._train(q.w) & q.w.subgroup(a.st.subgroup))
        tt, yy = nu["treated"].astype(bool), nu["y"]
        hero = _log_rr(int(yy[tt].sum()), int(tt.sum()), int(yy[~tt].sum()), int((~tt).sum()))
        new = _log_rr(e1, n1, e0, n0)
        z = (new["beta"] - hero["beta"]) / math.sqrt(new["se"] ** 2 + hero["se"] ** 2)
        p_het = float(2 * stats.norm.sf(abs(z)))
        agrees = p_fisher < rules.ALPHA and p_het >= rules.ALPHA
        contradicts = p_het < rules.ALPHA or (np.sign(new["beta"]) == -d and p_fisher > 1 - rules.ALPHA)
        q._emit(level=level, actor="judge", action="mystery_encounter", enemy=SECRET["boss"]["key"],
                line=f"{SECRET['boss']['name']}: \"Your estimate, meet data you have never seen.\"",
                result={"enemy": {"key": SECRET["boss"]["key"], "name": SECRET["boss"]["name"], "test": SECRET["boss"]["test"],
                                  "boss": True, "mystery": True}, "boss": True, "mystery": m["id"]})
        line = (f"Risk ratio {math.exp(new['beta']):.2f} in the new data vs {math.exp(hero['beta']):.2f} in the hero's training "
                f"cohort; heterogeneity z = {z:+.2f}, p = {p_het:.3g}.")
        nums = {"rr_new": math.exp(new["beta"]), "rr_hero": math.exp(hero["beta"]), "z": z, "p_heterogeneity": p_het,
                "p_fisher": float(p_fisher)}
        chart = {"kind": "forest", "title": "One-year risk ratio: hero's training cohort vs the new dataset", "ref": 1.0,
                 "rows": [{"label": "Hero (training, new users)", **_ci_rr(hero)}, {"label": f"New data ({rec['filename']})", **_ci_rr(new)}]}
        rule = m["rule"]
        if agrees:
            res = {"outcome": "SURVIVED", "line": line, "plain": "The new data agrees with the hero's estimate.",
                   "numbers": nums, "rule": rule, "chart": chart}
        elif contradicts:
            res = {"outcome": "FALLEN", "line": line, "plain": "The new data contradicts the hero's estimate.",
                   "numbers": nums, "rule": rule, "chart": chart}
        else:
            res = {"outcome": "UNRESOLVED", "line": line, "plain": "The new data is too small to confirm or refute the hero: "
                   "the quest stays open.", "numbers": nums, "rule": rule, "chart": chart}
        self._resolve(m, a, level, res, "V1", SECRET["boss"]["key"])
        sl["outcome"] = res["outcome"]
        q._emit(level=level, actor="system", action="secret_level_complete",
                line=f"{SECRET['name']} complete: {res['outcome'].lower()}.", result={"secret": sl})
        return m

    def _obstacle(self, a, level, ob, passed, line, plain, numbers) -> None:
        q = self.q
        q._emit(level=level, actor="judge", action="mystery_encounter", enemy=ob["key"], line=f"{ob['name']} blocks the way.",
                result={"enemy": {"key": ob["key"], "name": ob["name"], "test": ob["test"], "boss": False, "mystery": True}})
        q._emit(level=level, actor="judge", action="mystery_result", agent=a, enemy=ob["key"], hp_delta=0, passed=bool(passed),
                line=line, explain=plain, payload={"numbers": numbers, "formula": ob["test"], "outcome": "MEASURED",
                                                   "obstacle": True})

    # ---------- helpers ----------

    def unresolved(self, target: str | None = None) -> list[dict]:
        return [m for m in self.mysteries.values() if m["status"] in UNRESOLVED and (target is None or m["target"] == target)]

    def summary(self) -> dict:
        return _plain({"intakes": [EV.public(r) for r in self.intakes], "mysteries": [dict(m) for m in self.mysteries.values()],
                       "secret_levels": list(self.secret_levels), "waiting": self.waiting, "advanced": self.advanced})

    def _level(self, level) -> int:
        try:
            lv = int(level)
        except (TypeError, ValueError):
            lv = self.q.level or 1
        return max(1, min(lv, max(1, self.q.level or 1), 5))

    def _target(self, target: str | None):
        q = self.q
        a = q.agents.get(target or "")
        if a is not None and a.active:
            return a
        active = q._active()
        if not active:
            return None
        return max(active, key=lambda x: (x.hp, x.archetype == "PIONEER"))

    def _once(self, request_id: str | None, fn) -> dict:
        """Duplicate-request protection: the same request id always gets the first answer, and runs once."""
        if not request_id:
            return fn()
        with self._req_lock:
            if request_id in self._responses:
                return {**self._responses[request_id], "duplicate": True}
            result = fn()
            self._responses[request_id] = result
            return result


def _plain(x):
    """JSON-safe copies: numpy numbers become Python numbers (the same rounding the ledger uses)."""
    from .campaign import _round
    return _round(x)


def _log_rr(e1: int, n1: int, e0: int, n0: int) -> dict:
    """Crude log risk ratio with a 0.5 continuity correction when a cell is empty."""
    if min(e1, e0, n1 - e1, n0 - e0) == 0:
        e1, e0, n1, n0 = e1 + 0.5, e0 + 0.5, n1 + 1, n0 + 1
    beta = math.log((e1 / n1) / (e0 / n0))
    se = math.sqrt(1 / e1 - 1 / n1 + 1 / e0 - 1 / n0)
    return {"beta": beta, "se": se}


def _ci_rr(e: dict) -> dict:
    return {"est": round(math.exp(e["beta"]), 4), "lo": round(math.exp(e["beta"] - 1.96 * e["se"]), 4),
            "hi": round(math.exp(e["beta"] + 1.96 * e["se"]), 4)}



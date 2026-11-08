"""The Research Director's console, Mystery Bosses, the Bridge of Judgment, Evolution and the Trial of Truth."""

import base64
import threading
import time

import numpy as np
import pytest

from app.arena.ledger import Ledger
from app.pep import bridge, challenges, evidence, rules
from app.pep.campaign import PepQuest
from app.pep.campaigns import CAMPAIGNS
from app.pep.director import DirectorError, Expedition
from app.pep.models import QuestEvent

NO_NET = lambda url: {"ok": False, "error": "blocked by the network policy"}  # noqa: E731


class Driver:
    """Runs an interactive quest in a thread and lets the test act as the Research Director."""

    def __init__(self, tmp_path, campaign="GLP1_ADDICTION", watch_vault=False):
        self.ledger = Ledger("t", tmp_path, model=QuestEvent)
        self.q = PepQuest("t", campaign, self.ledger)
        self.d = Expedition(self.q, fetch=NO_NET)
        self.vault_reads = []
        if watch_vault:
            real = self.q.w.mask

            def mask(split):
                if split != "train":
                    self.vault_reads.append((split, self.ledger.events[-1].action if self.ledger.events else None))
                return real(split)
            self.q.w.mask = mask
        self.t = threading.Thread(target=self.q.run, daemon=True)
        self.t.start()

    def wait(self, what, timeout=60):
        end = time.time() + timeout
        while self.d.waiting != what:
            assert self.t.is_alive() and time.time() < end, f"never reached {what}"
            time.sleep(0.02)

    def to_bridge(self, start=1):
        for lv in range(start, 5):
            self.wait(f"level {lv}")
            self.d.advance(lv)
        self.wait("bridge")
        return self.d._assessment

    def finish(self, choice):
        self.d.choose(choice)
        self.t.join(60)
        assert not self.t.is_alive()
        return self.ledger.events


# ---------- routing and evidence ----------

@pytest.mark.parametrize("text,arch", [
    ("Does this even work in rural regions?", "regional"),
    ("Could this just be luck?", "chance"),
    ("Isn't it explained by testosterone use?", "confounder"),
    ("Did you peek at the future?", "chronolock"),
    ("Is it just a winter effect?", "seasonal"),
    ("Does it replicate on independent data?", "replication"),
    ("Does it add value beyond the baseline?", "redundancy"),
    ("What a lovely dungeon", None),
])
def test_the_router_maps_challenges_to_registered_tests(text, arch):
    assert challenges.route(text)["archetype"] == arch


def test_an_unmeasured_confounder_is_flagged():
    r = challenges.route("Maybe it is really income")
    assert r["archetype"] == "confounder" and r["unmeasured"] == "income" and r["covariate"] is None


def _ctx():
    return {"campaign": CAMPAIGNS["GLP1_ADDICTION"], "target": "pioneer", "level": 2}


def test_an_unretrievable_source_is_unverified_not_accepted():
    rec = evidence.intake({"text": "A new semaglutide study says it fails in rural regions", "url": "https://www.medrxiv.org/x"},
                          _ctx(), challenges.route("rural regions"), NO_NET)
    assert rec["classification"] == "UNVERIFIED" and rec["source"]["type"] == "preprint"
    assert any("blocked" in m for m in rec["missing"])


def test_a_retrieved_page_with_provenance_is_verified_and_its_html_is_never_run():
    html = ("<html><head><meta name='citation_publisher' content='The Lancet'><meta name='citation_date' content='2026/01/02'>"
            "<script>alert('pwned')</script><title>Semaglutide and alcohol relapse in rural regions</title></head>"
            "<body>Semaglutide alcohol relapse rural regions effect</body></html>")
    rec = evidence.intake({"text": "semaglutide alcohol relapse fails in rural regions", "url": "https://www.thelancet.com/x"},
                          _ctx(), challenges.route("rural regions"),
                          lambda u: {"ok": True, "status": 200, "content_type": "text/html", "bytes": len(html), "text": html})
    assert rec["classification"] == "VERIFIED AND TESTABLE"
    assert rec["publisher"] == "The Lancet" and rec["published"] == "2026/01/02"
    assert "alert" not in (rec["title"] or "")


def test_social_media_is_the_weakest_tier_and_irrelevant_text_is_irrelevant():
    assert evidence.source_type("https://x.com/someone/status/1")["tier"] < evidence.source_type("https://doi.org/10.1/x")["tier"]
    rec = evidence.intake({"text": "my cat likes tuna"}, _ctx(), challenges.route("my cat likes tuna"), NO_NET)
    assert rec["classification"] == "IRRELEVANT"


def test_the_fetcher_refuses_private_addresses_and_odd_schemes():
    assert not evidence.Fetcher()("http://127.0.0.1:8000/api/status")["ok"]
    assert not evidence.Fetcher()("file:///etc/passwd")["ok"]


def _file(name, text):
    return {"name": name, "content_b64": base64.b64encode(text.encode()).decode()}


def test_bad_uploads_are_invalid_or_need_more_evidence():
    ctx = _ctx()
    bad = evidence.intake({"filename": "x.csv", "content_b64": _file("x.csv", "a,b\n1,2\n")["content_b64"]}, ctx, {}, NO_NET)
    assert bad["classification"] == "INVALID OR INCOMPATIBLE DATA"
    pdf = evidence.intake({"filename": "x.pdf", "content_b64": base64.b64encode(b"%PDF-1.7 ...").decode()}, ctx, {}, NO_NET)
    assert pdf["classification"] == "REQUIRES ADDITIONAL EVIDENCE"
    exe = evidence.intake({"filename": "x.exe", "content_b64": base64.b64encode(b"MZ").decode()}, ctx, {}, NO_NET)
    assert exe["classification"] == "INVALID OR INCOMPATIBLE DATA"


# ---------- the console in a live quest ----------

def test_a_question_gets_an_answer_not_an_enemy(tmp_path):
    D = Driver(tmp_path)
    D.wait("level 1")
    out = D.d.chat({"mode": "ASK", "text": "Why did you pick those abilities?", "target": "pioneer"})
    assert "mystery" not in out and out["reply"]
    assert [e["action"] for e in out["events"]] == ["chat", "hero_reply"]
    D.to_bridge()
    D.finish("cross")


def test_a_mystery_boss_is_decided_by_its_test_and_the_hp_rule(tmp_path):
    D = Driver(tmp_path, watch_vault=True)
    D.wait("level 1")
    D.d.advance(1)
    D.wait("level 2")
    off = D.d.chat({"mode": "CHALLENGE", "text": "Couldn't this be luck?", "target": "hype", "request_id": "r1"})
    mid = off["mystery"]["id"]
    assert off["mystery"]["boss"] == "The Probability Phantom" and off["mystery"]["status"] == "offered"
    assert D.d.chat({"mode": "CHALLENGE", "text": "Couldn't this be luck?", "target": "hype", "request_id": "r1"})["duplicate"]
    hp0 = D.q.agents["hype"].hp
    D.vault_reads.clear()
    res = D.d.mystery(mid, "summon", "s1")
    m = res["mystery"]
    actions = [e["action"] for e in res["events"]]
    assert actions[:4] == ["mystery_summon", "gatekeeper", "mystery_encounter", "mystery_ability"]
    row = next(e for e in res["events"] if e["action"] == "mystery_result")
    expected = {"survived": rules.MYSTERY_HP["SURVIVED"], "fallen": rules.MYSTERY_HP["FALLEN"]}[m["status"]]
    assert row["hp_delta"] == expected == D.q.agents["hype"].hp - hp0
    assert m["result"]["numbers"]["permutations"] == rules.PERMUTATIONS
    assert D.d.mystery(mid, "summon", "s1").get("duplicate")          # the same click twice: one fight
    with pytest.raises(DirectorError):
        D.d.mystery(mid, "summon", "s2")                            # a boss can be fought once
    assert D.vault_reads == []                                      # the boss read the training cohort only
    D.to_bridge(2)
    D.finish("inconclusive")


def test_an_unmeasured_confounder_ends_as_an_unresolved_encounter(tmp_path):
    D = Driver(tmp_path)
    D.wait("level 1")
    off = D.d.chat({"mode": "CHALLENGE", "text": "It's really just income", "target": "pioneer"})
    m = D.d.mystery(off["mystery"]["id"], "summon")["mystery"]
    assert m["status"] == "unresolved" and m["hp_delta"] == 0
    D.to_bridge()
    D.finish("inconclusive")


def test_a_user_dataset_opens_a_secret_level_with_a_real_test(tmp_path):
    D = Driver(tmp_path)
    D.wait("level 1")
    rng = np.random.default_rng(1)
    t = rng.integers(0, 2, 600)
    y = (rng.random(600) < np.where(t == 1, 0.25, 0.38)).astype(int)
    csv = "treated,event\n" + "\n".join(f"{a},{b}" for a, b in zip(t, y))
    out = D.d.chat({"mode": "ADD_EVIDENCE", "text": "", "file": _file("clinic.csv", csv), "target": "pioneer"})
    assert out["intake"]["classification"] == "VERIFIED AND TESTABLE" and out["mystery"]["secret"]
    res = D.d.mystery(out["mystery"]["id"], "summon")
    acts = [e["action"] for e in res["events"]]
    assert "secret_level_start" in acts and acts.count("mystery_result") == 3 and "secret_level_complete" in acts
    assert res["mystery"]["result"]["numbers"]["rr_new"] > 0
    D.to_bridge()
    D.finish("inconclusive")


def test_an_unresolved_user_challenge_drives_evolution_and_v2_keeps_v1(tmp_path):
    D = Driver(tmp_path, watch_vault=True)
    D.wait("level 1")
    D.d.advance(1)
    D.wait("level 2")
    off = D.d.chat({"mode": "ADD_EVIDENCE", "text": "A new study says it does not generalise to rural regions",
                    "url": "https://www.medrxiv.org/x", "target": "pioneer"})
    D.d.mystery(off["mystery"]["id"], "save")
    A = D.to_bridge(2)
    assert any(u["id"] == off["mystery"]["id"] for u in A["unresolved"])
    assert A["recommendation"]["choice"] == "evolve"
    assert any(w.get("mystery") == off["mystery"]["id"] for w in A["weaknesses"])
    assert A["causal_links"][0]["effect"] == "in the evolution plan"
    D.d.choose("evolve")
    time.sleep(0.05)
    D.wait("bridge")
    A2 = D.d._assessment
    assert not A2["options"]["evolve"]["enabled"] and "once" in A2["options"]["evolve"]["reason"]
    events = D.finish("cross")
    acts = [e.action for e in events]
    assert acts.index("evolution_start") < acts.index("evolution_complete") < acts.index("spec_locked") < acts.index("trial_result")
    assert D.q.versions["V1"]["scrolls"] and D.q.versions["V2"]["scrolls"]
    assert D.d.mysteries[off["mystery"]["id"]]["status"] == "retested"
    # the second vault was read only after the specification was locked, and only by the trial
    vault2 = [r for r in D.vault_reads if r[0] == "vault2"]
    assert vault2 and all(r[1] == "spec_locked" for r in vault2)
    ow = events[-1].result["overworld"]
    assert ow["evolution"]["occurred"] and ow["contributions"]["changed_research"]


def test_honest_uncertainty_is_not_punished_and_overconfidence_is(tmp_path):
    D = Driver(tmp_path / "a", campaign="BPC157_TENDON")
    A = D.to_bridge()
    assert A["recommendation"]["choice"] == "inconclusive"
    ev = D.finish("inconclusive")
    tr = next(e for e in ev if e.action == "trial_result")
    assert tr.result["trial"]["outcome"] == "JUSTIFIED UNCERTAINTY" and (tr.hp_delta or 0) == 0
    D2 = Driver(tmp_path / "b", campaign="BPC157_TENDON")
    D2.to_bridge()
    tr2 = next(e for e in D2.finish("cross") if e.action == "trial_result")
    assert tr2.result["trial"]["outcome"] in ("UNJUSTIFIED CONFIDENCE", "INVALID METHODOLOGY")
    assert tr2.hp_delta < 0


def test_a_leaky_asserted_claim_is_rejected_by_the_audit(tmp_path):
    D = Driver(tmp_path)
    D.to_bridge()
    bridge.candidate(D.q).st.design = "ever"   # as if the hero had never aligned time zero
    tr = next(e for e in D.finish("cross") if e.action == "trial_result")
    assert tr.result["trial"]["outcome"] == "INVALID METHODOLOGY"


def test_without_a_director_the_hero_follows_its_own_recommendation(tmp_path):
    q = PepQuest("t", "GLP1_ADDICTION", Ledger("t", tmp_path, model=QuestEvent))
    result = q.run()
    assert q.bridge_log[0]["by"] == "autopilot"
    assert result["overworld"]["trial"]["outcome"] == "VALIDATED DISCOVERY"
    assert q.vault_opened is not None


# ---------- anti-farming, chips, sources, the fetcher and the idle timeout ----------

def test_repeating_a_boss_earns_nothing_and_a_family_rewards_once(tmp_path):
    D = Driver(tmp_path)
    D.wait("level 1")
    a = D.q.agents["pioneer"]

    def fight(rid):
        off = D.d.chat({"mode": "CHALLENGE", "archetype": "chance", "target": "pioneer", "request_id": f"c{rid}"})
        return D.d.mystery(off["mystery"]["id"], "summon", f"s{rid}")

    first = fight(1)["mystery"]
    assert first["status"] == "survived" and first["hp_delta"] == min(rules.MYSTERY_HP["SURVIVED"], 100 - (a.hp - first["hp_delta"]))
    looks = D.d.looks["pioneer"]
    hp = a.hp
    rep = fight(2)
    assert rep["mystery"]["status"] == "repeat" and rep["mystery"]["repeat_of"] == first["id"]
    row = next(e for e in rep["events"] if e["action"] == "mystery_result")
    assert row["hp_delta"] == 0 and a.hp == hp and D.d.looks["pioneer"] == looks     # not re-run, nothing changes
    D.d.advance(1)
    D.wait("level 2")                                # Bias Detection changed the scroll: the test runs again
    assert a.st.adjusted
    again = fight(3)["mystery"]
    assert again["status"] == "survived" and again["hp_delta"] == 0 and D.d.looks["pioneer"] == looks + 1
    assert "SURVIVED_AGAIN" in again["result"]["rule"] or again["result"]["plain"].endswith("no more HP.")
    D.to_bridge(2)
    D.finish("inconclusive")


def test_a_challenge_chip_names_the_registered_test(tmp_path):
    D = Driver(tmp_path)
    D.wait("level 1")
    out = D.d.chat({"mode": "ASK", "archetype": "regional", "text": "", "target": "pioneer"})
    assert out["mode"] == "CHALLENGE" and out["route"]["archetype"] == "regional" and out["route"]["forced"]
    assert out["mystery"]["boss"] == challenges.ARCHETYPES["regional"]["boss"]
    assert out["events"][0]["result"]["text"] == challenges.ARCHETYPES["regional"]["question"]
    with pytest.raises(DirectorError):
        D.d.chat({"mode": "CHALLENGE", "archetype": "astrology", "target": "pioneer"})
    D.to_bridge()
    D.finish("inconclusive")


def test_evidence_is_registered_as_a_source_with_its_usage(tmp_path):
    import hashlib
    D = Driver(tmp_path)
    D.wait("level 1")
    rng = np.random.default_rng(2)
    t = rng.integers(0, 2, 200)
    csv = "treated,event\n" + "\n".join(f"{a},{int(b)}" for a, b in zip(t, rng.random(200) < 0.3))
    up = D.d.chat({"mode": "ADD_EVIDENCE", "file": _file("clinic.csv", csv), "target": "pioneer"})
    src = next(e for e in up["events"] if e["action"] == "source_registered")["result"]["source"]
    assert src["type"] == "USER_UPLOADED" and src["usage"] == "NUMERIC_TEST"
    assert src["sha256"] == hashlib.sha256(csv.encode()).hexdigest()
    link = D.d.chat({"mode": "ADD_EVIDENCE", "text": "A preprint says it fails in rural regions",
                     "url": "https://www.medrxiv.org/x", "target": "pioneer"})
    assert next(e for e in link["events"] if e["action"] == "source_registered")["result"]["source"]["usage"] == "CONTEXT"
    cat = D.d.chat({"mode": "ADD_EVIDENCE", "text": "my cat likes tuna", "target": "pioneer"})
    assert next(e for e in cat["events"] if e["action"] == "source_registered")["result"]["source"]["usage"] == "EXCLUDED"
    D.d.mystery(up["mystery"]["id"], "summon")
    D.to_bridge()
    events = D.finish("inconclusive")
    arc = events[-1].result["archive"]
    assert arc["check"]["complete"], arc["check"]["problems"]
    assert any(f"S-{up['intake']['id']}" in t["sources"] for t in arc["trace"])


def test_the_fetcher_connects_to_the_address_it_checked(monkeypatch):
    import http.server
    import socket

    class Page(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            kind = {"/page": "text/html", "/bin": "application/octet-stream"}.get(self.path)
            if self.path == "/moved":
                self.send_response(302)
                self.send_header("Location", "http://127.0.0.1/")
                self.end_headers()
                return
            body = (b"x" * 1_100_000) if self.path == "/big" else b"<title>ok</title><p>semaglutide</p>"
            self.send_response(200)
            self.send_header("Content-Type", kind or "text/plain")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    srv = http.server.HTTPServer(("127.0.0.1", 0), Page)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    port = srv.server_address[1]
    public = "93.184.216.34"
    monkeypatch.setattr(evidence, "_resolve", lambda host, p, t: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (public, p))])
    dialed, real = [], socket.create_connection

    def dial(addr, *a, **k):     # the pinned address is what gets dialled; the test then routes it to the local server
        dialed.append(addr[0])
        return real(("127.0.0.1", port), *a, **k)

    monkeypatch.setattr(evidence.socket, "create_connection", dial)
    f = evidence.Fetcher()
    try:
        ok = f(f"http://journal.example:{port}/page")
        assert ok["ok"] and "semaglutide" in ok["text"] and ok["address"] == public and len(ok["sha256"]) == 64
        assert dialed == [public]
        assert "redirects" in f(f"http://journal.example:{port}/moved")["error"]
        assert "does not read" in f(f"http://journal.example:{port}/bin")["error"]
        assert "1 MB" in f(f"http://journal.example:{port}/big")["error"]
        assert "user name" in f(f"http://me:pw@journal.example:{port}/page")["error"]
    finally:
        srv.shutdown()
    monkeypatch.setattr(evidence, "_resolve", lambda host, p, t: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.1.2.3", p))])
    assert "private" in f("http://rebound.example/page")["error"]


def test_an_unwatched_expedition_times_out(tmp_path):
    ledger = Ledger("t", tmp_path, model=QuestEvent)
    q = PepQuest("t", "GLP1_ADDICTION", ledger)
    d = Expedition(q, fetch=NO_NET)
    q.idle_limit = 0.3
    t = threading.Thread(target=q.run, daemon=True)
    t.start()
    t.join(30)
    assert not t.is_alive() and ledger.events[-1].action == "timeout"
    assert d.advanced == 0 and not any(e.action == "finale" for e in ledger.events)

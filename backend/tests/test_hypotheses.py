"""The Scribe: N hypothesis scrolls, words from Claude (or the script), evidence copied from the real database."""

import json

import duckdb

from app.arena.ledger import Ledger
from app.pep import hypotheses as H
from app.pep.campaign import PepQuest
from app.pep.campaigns import BY_LETTER, CAMPAIGNS
from app.pep.models import QuestEvent
from app.pep.world import World


def fake_db(path):
    con = duckdb.connect(str(path))
    con.execute("CREATE TABLE pep_papers (campaign VARCHAR, topic VARCHAR, title VARCHAR, pub_year INTEGER, "
                "design VARCHAR, species VARCHAR, authors VARCHAR, url VARCHAR)")
    con.execute("CREATE TABLE pep_queries (campaign VARCHAR, topic VARCHAR, source VARCHAR, hit_count INTEGER)")
    con.execute("CREATE TABLE pep_trials (campaign VARCHAR, topic VARCHAR, status VARCHAR, allocation VARCHAR)")
    con.execute("CREATE TABLE pep_faers (campaign VARCHAR, topic VARCHAR, drug_group VARCHAR, reactions VARCHAR, "
                "drug_and_reaction INTEGER, drug_total INTEGER, reaction_total INTEGER, all_reports INTEGER)")
    rows = [("B", "bpc157", f"Rat tendon {i}", 2020, "other", "animal", f"Lab{i % 2} A", "u") for i in range(6)]
    rows += [("B", "bpc157", "Human case", 2024, "case_report", "human", "Smith J", "u"),
             ("B", "bpc157", "Unclear", 2024, "other", "unknown", "Doe A", "u")]
    con.executemany("INSERT INTO pep_papers VALUES (?, ?, ?, ?, ?, ?, ?, ?)", rows)
    con.execute("INSERT INTO pep_queries VALUES ('B', 'bpc157', 'europepmc', 313)")
    con.executemany("INSERT INTO pep_trials VALUES ('B', 'tb500', ?, ?)",
                    [("COMPLETED", "RANDOMIZED"), ("COMPLETED", "NA"), ("RECRUITING", "RANDOMIZED")])
    con.close()
    return path


def test_scripted_scribe_forms_two_to_six_and_never_one(tmp_path):
    c = BY_LETTER["A"]
    for n in (1, 2, 3, 5, 6, 9):
        scrolls, info = H.form(c, n, db_path=tmp_path / "missing.duckdb", world=World(c))
        assert len(scrolls) == min(max(n, H.MIN_SCROLLS), H.MAX_SCROLLS) == info["count"]   # never a lone scroll
        assert len({s.key for s in scrolls}) == len(scrolls)
        assert len({H.study_key(s.question_key, s.archetype) for s in scrolls}) == len(scrolls)   # no duplicate study
        assert info["source"] == "script" and info["evidence"] == "simulated"
        assert all(s.hypothesis_id.startswith("H-") and s.question_key for s in scrolls)
    assert [s.claim for s in H.form(c, 3, db_path=tmp_path / "x")[0]] == [s.claim for s in c.scrolls]


def test_real_papers_and_trials_are_copied_into_the_scroll(tmp_path):
    db = fake_db(tmp_path / "ev.duckdb")
    ev = H.load_evidence("B", db)
    t = ev["topics"]["bpc157"]
    assert t["papers_found"] == 313 and t["unknown_species"] == 1
    assert t["species"] == {"human": 1, "rodent": 6, "in vitro": 0}
    assert ev["topics"]["tb500"]["completed_rcts"] == 1        # completed AND randomized only
    scrolls, info = H.form(BY_LETTER["B"], 2, db_path=db)
    s = scrolls[0]
    assert s.evidence_real and s.evidence_topic == "bpc157" and s.n_rct == 0
    papers = World(BY_LETTER["B"]).papers(s)
    assert len(papers) == 7 and sum(p["species"] == "rodent" for p in papers) == 6
    assert {p["lab"] for p in papers} == {"Lab0 A", "Lab1 A", "Smith J"}


GOOD = {"title": "The Gut Scroll", "claim": "BPC-157 cuts persistent pain versus physiotherapy.", "outcome": "pain",
        "direction": "lowers", "subgroup": "everyone", "topic": "bpc157", "archetype": "PIONEER",
        "origin": "cytoprotection reviews", "falsifier": "No less persistent pain than physiotherapy alone."}


def test_claude_writes_the_words_and_bad_entries_fall_back_with_a_reason(tmp_path):
    numbers = {**GOOD, "claim": "BPC-157 cuts pain by forty percent, p = 0.01."}
    unknown = {**GOOD, "outcome": "flying"}
    untyped = {k: v for k, v in GOOD.items() if k != "direction"}
    replies = [json.dumps({"hypotheses": [GOOD, numbers, unknown, untyped]})]
    scrolls, info = H.form(BY_LETTER["B"], 3, lambda system, user: replies[0], db_path=fake_db(tmp_path / "e.duckdb"),
                           world=World(BY_LETTER["B"]))
    assert info["source"] == "claude" and len(scrolls) == 3
    assert scrolls[0].title == "The Gut Scroll" and scrolls[0].archetype == "PIONEER" and scrolls[0].direction == -1
    assert scrolls[0].origin_mode == "SCRIBE_CLAUDE"
    reasons = [r["reason"] for r in info["rejected"]]
    assert "p-value" in reasons[0] and "flying" in reasons[1] and "direction" in reasons[2]
    assert scrolls[1].claim == BY_LETTER["B"].scrolls[0].claim     # the script fills the rejected slots
    assert {s.origin_mode for s in scrolls[1:]} <= {"HAND_WRITTEN", "SCRIBE_SCRIPT"}


def test_a_quest_with_formed_hypotheses_runs_to_the_end(tmp_path):
    led = Ledger("t", tmp_path, model=QuestEvent)
    q = PepQuest("t", CAMPAIGNS["GLP1_ADDICTION"].id, led, n_scrolls=5)
    q.run()
    rows = [json.loads(line) for line in next(tmp_path.glob("*.jsonl")).read_text(encoding="utf-8").splitlines()]
    acts = [r["action"] for r in rows]
    assert "error" not in acts and acts.index("hypotheses") < acts.index("recruit")
    assert acts.count("recruit") == 5 and len(q.agents) == 5


def test_each_quest_asks_the_scribe_for_something_new(tmp_path):
    H._RECENT.clear()
    db = fake_db(tmp_path / "v.duckdb")
    seen = []
    good = {**GOOD, "title": "BPC-157 speeds tendon healing"}

    def complete(system, user):
        seen.append((system, json.loads(user)))
        return json.dumps({"hypotheses": [good]})

    for _ in range(2):
        H.form(BY_LETTER["B"], 1, complete, db_path=db)
    (sys1, u1), (sys2, u2) = seen
    assert u1["already_written"] == [] and u2["already_written"] == ["BPC-157 speeds tendon healing"]
    assert "angles" in sys1 and len(u1["topics"]["bpc157"]["examples"]) == 6   # a sample of the 7 known-species papers
    H._RECENT.clear()

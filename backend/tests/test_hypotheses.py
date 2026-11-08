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


def test_scripted_scribe_forms_any_count_up_to_the_cap(tmp_path):
    c = BY_LETTER["A"]
    for n in (1, 3, 5, 6, 9):
        scrolls, info = H.form(c, n, db_path=tmp_path / "missing.duckdb")
        assert len(scrolls) == min(n, H.MAX_SCROLLS) == info["count"]
        assert len({s.key for s in scrolls}) == len(scrolls)
        assert info["source"] == "script" and info["evidence"] == "simulated"
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


def test_claude_writes_the_words_and_bad_entries_fall_back(tmp_path):
    good = {"title": "The Gut Scroll", "claim": "BPC-157 cuts persistent pain versus physiotherapy.",
            "outcome": "pain", "topic": "bpc157", "archetype": "PIONEER", "origin": "cytoprotection reviews"}
    numbers = {**good, "claim": "BPC-157 cuts pain by forty percent, p = 0.01."}
    unknown = {**good, "outcome": "flying"}
    replies = [json.dumps({"hypotheses": [good, numbers, unknown]})]
    scrolls, info = H.form(BY_LETTER["B"], 3, lambda system, user: replies[0], db_path=fake_db(tmp_path / "e.duckdb"))
    assert info["source"] == "claude" and len(scrolls) == 3
    assert scrolls[0].title == "The Gut Scroll" and scrolls[0].archetype == "PIONEER"
    assert all(not H._has_number(s.claim) for s in scrolls[:1])
    assert scrolls[1].claim == BY_LETTER["B"].scrolls[1].claim     # the script fills the rejected slots


def test_a_quest_with_formed_hypotheses_runs_to_the_end(tmp_path):
    led = Ledger("t", tmp_path, model=QuestEvent)
    q = PepQuest("t", CAMPAIGNS["GLP1_ADDICTION"].id, led, n_scrolls=5)
    q.run()
    rows = [json.loads(line) for line in next(tmp_path.glob("*.jsonl")).read_text().splitlines()]
    acts = [r["action"] for r in rows]
    assert "error" not in acts and acts.index("hypotheses") < acts.index("recruit")
    assert acts.count("recruit") == 5 and len(q.agents) == 5

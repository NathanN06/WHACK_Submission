"""Challenger Mode: one title per campaign track, defended on a fresh cohort every round, written once and atomically."""

import json

from app.arena.ledger import Ledger
from app.pep import champions
from app.pep.campaign import PepQuest
from app.pep.campaigns import BY_LETTER
from app.pep.models import QuestEvent


def play(tmp_path, letter, run_id, path):
    led = Ledger(run_id, tmp_path / "runs", model=QuestEvent)
    q = PepQuest(run_id, BY_LETTER[letter].id, led, challenger=True, champions_path=path)
    fin = q.run()
    rows = [json.loads(line) for line in (tmp_path / "runs" / f"{run_id}.jsonl").read_text().splitlines()]
    return q, fin, rows


def test_a_title_is_won_then_defended_by_a_frozen_claim_on_a_fresh_cohort(tmp_path):
    path = tmp_path / "champions.json"
    q1, fin1, rows1 = play(tmp_path, "A", "r1", path)
    up1 = fin1["challenger"]
    assert q1.seed == 1 and up1["round"] == 1 and up1["result"] == "NEW CHAMPION" and up1["applied"]
    assert [r["action"] for r in rows1].count("champion_update") == 1
    champ = champions.load(path)["tracks"]["A:alcohol"]["champion"]
    assert champ["claim_hash"] == champions.claim_hash(champ["spec"]) and champ["hid"] == "H-" + champ["claim_hash"][:8]

    q2, fin2, rows2 = play(tmp_path, "A", "r2", path)
    assert q2.seed == 2                                       # every round is a cohort nobody has seen
    inc = q2.agents["champion"].scroll
    assert champions.frozen_spec(q2.agents["champion"]) == champ["spec"]    # the words are carried in unchanged
    assert inc.champion["hid"] == champ["hid"]
    shapes = [(a.scroll.outcome, a.scroll.archetype) for a in q2.agents.values()]
    assert len(set(shapes)) == len(shapes)                    # no challenger shares the champion's structure
    roster = next(r for r in rows2 if r["action"] == "challenger_roster")["result"]
    assert roster["incumbent"]["hid"] == champ["hid"] and "champion" not in roster["challengers"]
    up2 = fin2["challenger"]
    assert up2["result"] == "CHAMPION DEFENDED" and up2["winner"] == "champion"
    track = champions.load(path)["tracks"]["A:alcohol"]
    assert track["rounds"] == 2 and track["revision"] == 2 and track["champion"]["defended"] == 1
    assert [h["result"] for h in track["history"]] == ["NEW CHAMPION", "CHAMPION DEFENDED"]
    assert not list(tmp_path.glob(".*.tmp"))                  # written with a temporary file, then os.replace
    shown = champions.public(path)["tracks"]["A:alcohol"]
    assert all("settled" not in h for h in shown["history"])


def test_settling_the_same_run_twice_writes_once(tmp_path):
    path = tmp_path / "champions.json"
    q, fin, _ = play(tmp_path, "A", "r1", path)
    before = path.read_text()
    again = champions.settle(q, fin, path)
    assert again["duplicate"] and again["result"] == fin["challenger"]["result"]
    assert path.read_text() == before


def test_a_round_settled_meanwhile_is_not_applied(tmp_path):
    path = tmp_path / "champions.json"
    led = Ledger("slow", tmp_path / "runs", model=QuestEvent)
    slow = PepQuest("slow", BY_LETTER["A"].id, led, challenger=True, champions_path=path)   # planned at revision 0
    play(tmp_path, "A", "fast", path)                                                      # settles revision 0 first
    fin = slow.run()
    assert fin["challenger"]["result"] == "NOT APPLIED" and not fin["challenger"]["applied"]
    assert fin["challenger"]["would_have_been"] in champions.RESULTS
    track = champions.load(path)["tracks"]["A:alcohol"]
    assert track["revision"] == 1 and [h["run_id"] for h in track["history"]] == ["fast"]


def test_nobody_eligible_leaves_the_title_vacant(tmp_path):
    path = tmp_path / "champions.json"
    _, fin, _ = play(tmp_path, "B", "b1", path)
    up = fin["challenger"]
    assert up["result"] == "NO ELIGIBLE CHAMPION" and up["winner"] is None
    assert all(not e["eligible"] and e["why"] for e in up["entries"])
    assert champions.load(path)["tracks"]["B:" + BY_LETTER["B"].outcomes[0].key]["champion"] is None


def test_an_unreadable_registry_is_never_overwritten(tmp_path):
    path = tmp_path / "champions.json"
    path.write_text("{not json")
    _, fin, _ = play(tmp_path, "A", "r1", path)
    assert fin["challenger"]["result"] == "NOT APPLIED" and path.read_text() == "{not json"

"""A live game should never sit silent while Claude thinks: decisions for a level are asked in parallel, the next
level's decisions are asked while the screen is still showing this one, and a stale prefetched plan is never used."""

import json
import threading
import time

from app.arena.ledger import Ledger
from app.pep import agents as AG
from app.pep.campaign import PepQuest
from app.pep.director import Expedition
from app.pep.models import QuestEvent

DELAY = 0.4


class SlowClaude:
    """Stands in for the API: takes DELAY seconds, answers validly, and records who asked about what, and when."""

    def __init__(self):
        self.calls, self.lock, self.running, self.peak = [], threading.Lock(), 0, 0

    def __call__(self, system, user):
        p = json.loads(user)
        with self.lock:
            self.running += 1
            self.peak = max(self.peak, self.running)
            self.calls.append((p["level"]["number"], p["scroll"]["id"], p["resources"]["hp"], time.time()))
        time.sleep(DELAY)
        with self.lock:
            self.running -= 1
        return json.dumps({"selected_ability_ids": [], "concern_code": "NONE", "decision_reason": "Nothing flagged.",
                           "expected_tradeoff": "", "next_research_action": "TEST", "cited_signals": [], "line": "Onward."})

    def at(self, level):
        return [c for c in self.calls if c[0] == level]


def quest(tmp_path, claude, **kw):
    return PepQuest("t", "GLP1_ADDICTION", Ledger("t", tmp_path, model=QuestEvent), AG.LLMHero(claude), **kw)


def test_a_levels_decisions_are_asked_in_parallel_and_logged_in_order(tmp_path):
    claude = SlowClaude()
    q = quest(tmp_path, claude)
    q.start()
    t0 = time.time()
    q.play_level(1)
    took = time.time() - t0
    assert claude.peak == 3 and took < 2 * DELAY            # three scrolls at once, not one after another
    rows = [e for e in q.ledger.events if e.action in ("planning", "decision")]
    assert rows[0].action == "planning" and [e.agent_id for e in rows[1:]] == ["hype", "pioneer", "preprint"]
    assert all(e.result["execution"]["execution_mode"] == "LIVE_CLAUDE" for e in rows[1:])


def test_the_next_level_is_planned_while_the_screen_still_shows_this_one(tmp_path):
    claude = SlowClaude()
    q = quest(tmp_path, claude)
    d = Expedition(q)                      # interactive: the quest waits for the screen after every level
    t = threading.Thread(target=q.run, daemon=True)
    t.start()
    try:
        deadline = time.time() + 20
        while time.time() < deadline and not any(e.action == "level_complete" for e in q.ledger.events):
            time.sleep(0.05)
        while time.time() < deadline and len(claude.at(2)) < 3:   # the screen has not advanced, yet Level II is asked
            time.sleep(0.05)
        assert len(claude.at(2)) == 3
        asked = len(claude.calls)
        d.advance(1)
        while time.time() < deadline and not any(e.action == "level_complete" and e.level == 2 for e in q.ledger.events):
            time.sleep(0.05)
        level2 = [e for e in q.ledger.events if e.level == 2]
        assert not any(e.action == "planning" for e in level2)        # nothing to wait for: the plans were ready
        assert len(claude.at(2)) == 3 and len(claude.calls) >= asked   # and Level II was asked exactly once
    finally:
        q.stop()
        t.join(timeout=10)


def test_a_prefetched_plan_is_asked_again_when_the_scroll_changed_meanwhile(tmp_path):
    claude = SlowClaude()
    q = quest(tmp_path, claude)
    q.start()
    q.play_level(1)
    q._prefetch(2)
    for fp, fut in q._prefetched[2].values():
        fut.result()
    q.agents["pioneer"].hp -= 10              # a Mystery Boss struck during the checkpoint
    q._choose_all(2, q._active())
    asked = [c[1] for c in claude.at(2)]
    assert asked.count("pioneer") == 2 and asked.count("hype") == 1 and asked.count("preprint") == 1
    stale, fresh = [c for c in claude.at(2) if c[1] == "pioneer"]
    assert fresh[2] == stale[2] - 10           # the new plan saw the scroll as it stands now


def test_the_skeptic_speaks_before_it_thinks(tmp_path):
    q = quest(tmp_path, SlowClaude())
    q.brain = AG.ScriptedHero()
    q.run()
    acts = [e.action for e in q.ledger.events]
    start = acts.index("skeptic_start")
    assert acts[start - 1] == "level_complete" and acts[start + 1] == "skeptic_challenge"

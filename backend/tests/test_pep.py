"""The Peptide & GLP-1 edition: the Judge's formulas, the damage rules, telemetry and campaign outcomes."""

import math

import numpy as np
import pytest

from app.arena.ledger import Ledger
from app.pep import judge as J
from app.pep import rules
from app.pep.agents import ScriptedHero, menu_for
from app.pep.campaign import PepQuest
from app.pep.campaigns import CAMPAIGNS
from app.pep.models import QuestEvent
from app.pep.world import World


# ---------- formulas ----------

def test_clamp_never_heals_and_never_exceeds_the_level_cap():
    assert J.clamp_hp(-50, 1.0, 1) == 0
    assert J.clamp_hp(500, 1.0, 1) == 20 and J.clamp_hp(500, 1.0, 4) == 60
    assert J.clamp_hp(30, 0.5, 1) == 15  # Exploratory Claim multiplier
    assert [rules.D_MAX[k] for k in (1, 2, 3, 4)] == [20, 30, 45, 60]


def test_level_formulas_match_the_spec():
    assert J.d_l1({"phi": 0.4, "n_eff": 15}) == pytest.approx({"affiliate": 6.0, "neff": 7.5})
    assert J.d_l1({"phi": 0.0, "n_eff": 60})["neff"] == 0
    l2 = J.d_l2({"tau": 0.5, "human": 3, "shift": 0.25}, species_guard=False, bias_detection=False)
    assert l2 == pytest.approx({"rodent": 11.0, "confound": 5.0})
    assert J.d_l2({"tau": 0.5, "human": 3, "shift": 0.25}, True, True) == pytest.approx({"rodent": 2.2, "confound": 0.0})
    assert J.d_l2({"tau": 1.0, "human": 0, "shift": 0.0}, True, False)["rodent"] == 22  # no human study to stand on
    assert J.d_l3({"p_corr": 0.2, "h_lab": 0.5, "n_rct": 0}) == {"sidak": 20.0, "hlab": 10.0, "rct": 25.0}
    assert J.d_chrono({"l_time": 1, "delta_purge": 0.4}) == pytest.approx(45.0)


def test_sidak_and_the_final_rule():
    assert J.sidak(0.01, 1) == pytest.approx(0.01)
    assert J.sidak(0.01, 21) == pytest.approx(1 - 0.99 ** 21)
    assert J.d_final({"ss_oos": 0.01, "p_dm": 0.01}) == (0.0, True)
    assert J.d_final({"ss_oos": 0.01, "p_dm": 0.3}) == (15.0, False)  # a gain that could be luck is no gain
    assert J.d_final({"ss_oos": -0.04, "p_dm": 0.9}) == (50.0, False)
    assert J.d_final({"ss_oos": 0.01, "p_dm": 0.01}, time_zero=False) == (15.0, False)  # immortal time: not trusted


def test_poisson_fit_recovers_a_rate_ratio():
    rng = np.random.default_rng(0)
    n = 20000
    x = (rng.random(n) < 0.5).astype(float)
    pt = rng.uniform(0.5, 2, n)
    y = rng.poisson(0.2 * pt * np.exp(math.log(0.6) * x))
    b, se = J.poisson_fit(x[:, None], y, pt)  # the intercept is added inside
    assert math.exp(b[1]) == pytest.approx(0.6, abs=0.05) and se[1] < 0.05


def test_composite_score_uses_the_spec_weights():
    s = J.composite_score(0.02, 100, 4, 4, 50, 50)
    assert s["total"] == pytest.approx(0.35 * 100 + 0.25 * 100 + 0.25 * 100 + 0.15 * 100)
    assert J.composite_score(None, 0, 0, 0, 0, 0)["total"] == 0
    assert sum(rules.SCORE_WEIGHTS.values()) == pytest.approx(1.0)


# ---------- the simulated world ----------

def test_worlds_are_deterministic_and_split_by_calendar_time():
    c = CAMPAIGNS["GLP1_ADDICTION"]
    a, b = World(c, seed=3), World(c, seed=3)
    assert np.array_equal(a.start, b.start) and np.array_equal(a.events["alcohol"][0], b.events["alcohol"][0])
    assert set(a.split) == {"train", "holdout", "vault2"}
    assert a.index[a.mask("train")].max() < a.index[a.mask("holdout")].min()


def test_immortal_time_flatters_the_drug_and_the_new_user_design_removes_it():
    c = CAMPAIGNS["BPC157_TENDON"]  # no true effect anywhere
    w = World(c)
    train = w.mask("train")
    ever = J.effect(w, "return", "ever", True, train)
    new = J.effect(w, "return", "new_user", True, train)
    assert ever["rr"] < 0.9 and abs(math.log(new["rr"])) < 0.1
    assert J.immortal_share(w, "return", "ever", train) > 0.05
    assert J.immortal_share(w, "return", "new_user", train) == 0


def test_the_hype_scroll_cannot_preregister(tmp_path):
    q = PepQuest("t", "GLP1_ADDICTION", Ledger("t", tmp_path, model=QuestEvent))
    q.start()
    hype = q.agents["hype"]
    assert "PREREGISTER" not in menu_for(hype, 3)
    assert "PREREGISTER" in menu_for(q.agents["pioneer"], 3)


# ---------- whole campaigns ----------

def run(cid: str, tmp_path) -> tuple[list[QuestEvent], dict]:
    ledger = Ledger(f"t-{cid}", tmp_path, model=QuestEvent)
    result = PepQuest(f"t-{cid}", cid, ledger, ScriptedHero(), seed=0).run()
    return ledger.events, result


def test_the_real_effect_is_validated_and_the_hype_shatters(tmp_path):
    events, result = run("GLP1_ADDICTION", tmp_path)
    champ = result["champion"]
    assert champ and champ["archetype"] == "PIONEER" and champ["verdict"] == "VALIDATED"
    assert champ["skill"]["ss_oos"] > rules.SS_MARGIN and champ["skill"]["p_dm"] < rules.ALPHA
    verdict = {r["archetype"]: r["verdict"] for r in result["ranking"]}
    assert verdict["PREPRINT"] == "SHATTERED"
    assert verdict["HYPE"] in ("SHATTERED", "NOT BETTER")  # never time-zero aligned, so it cannot validate
    assert result["brief"]["decision"].startswith("PRIORITISE")
    assert all(ev["cite"] for ev in result["brief"]["evidence"])
    assert any(e.action == "shatter" for e in events) and any(e.action == "benchmark" for e in events)


@pytest.mark.parametrize("cid", ["BPC157_TENDON", "LONGEVITY_STACK", "GLP1_NAION"])
def test_mirages_end_with_the_baseline_holding(cid, tmp_path):
    _, result = run(cid, tmp_path)
    assert result["baseline_holds"] and result["champion"] is None
    assert result["brief"]["decision"].startswith("BASELINE HOLDS")
    assert result["benchmark"]["verdict"] == "BASELINE"
    assert next(r for r in result["ranking"] if r["archetype"] == "HYPE")["verdict"] == "SHATTERED"


def test_every_encounter_carries_the_telemetry_record(tmp_path):
    events, result = run("GLP1_ADDICTION", tmp_path)
    tele = [e.encounter for e in events if e.encounter]
    assert tele and result["totals"]["encounters"] == len(tele)
    keys = {"encounterId", "campaignType", "level", "enemyName", "trapType", "scrollId", "scrollTitle",
            "heroAction", "biostatMetrics", "combatResolution"}
    for t in tele:
        assert set(t) == keys
        assert t["trapType"] == rules.TRAPS[t["level"]]
        cr = t["combatResolution"]
        assert set(cr) == {"rawDamage", "abilityMultiplier", "clampedHpDelta", "executedFormulaLatex",
                           "plainEnglishVerdict"}
        assert -rules.D_MAX[t["level"]] <= cr["clampedHpDelta"] <= max(rules.EUREKA_HEAL, rules.BIAS_HEAL)
    assert len({t["encounterId"] for t in tele}) == len(tele)


def test_hp_and_credits_follow_the_ledger(tmp_path):
    events, result = run("GLP1_NAION", tmp_path)
    for r in result["ranking"]:
        rows = [e for e in events if e.agent_id == r["id"] and e.hp is not None]
        assert rows[-1].hp == r["hp"]
        assert 0 <= r["hp"] <= rules.STARTING_HP
        assert r["spent"] == sum(e.cost or 0 for e in events if e.agent_id == r["id"] and e.action == "decision")
        assert r["spent"] <= rules.STARTING_CREDITS


def test_a_scroll_loses_exactly_its_formula_per_level(tmp_path):
    events, result = run("BPC157_TENDON", tmp_path)
    for r in result["ranking"]:
        hits = [e for e in events if e.agent_id == r["id"] and e.action == "result" and e.result.get("term")]
        for level, cap in rules.D_MAX.items():
            lost = -sum(min(0, e.hp_delta or 0) for e in hits if e.level == level and e.result["term"] != "final")
            assert lost <= cap


def test_the_hero_never_writes_numbers_only_choices(tmp_path):
    events, _ = run("LONGEVITY_STACK", tmp_path)
    for e in events:
        if e.actor == "agent":
            assert e.action == "decision" and e.hp_delta is None and e.verdict is None
            assert set(e.result) <= {"abilities", "source", "menu", "decision"}


# ---------- code-review regressions ----------

def test_a_scroll_with_no_effect_scores_exactly_zero():
    w = World(CAMPAIGNS["GLP1_ADDICTION"], seed=0)
    g = J.guardian(w, "alcohol", 0.0)
    assert g["ss_oos"] == pytest.approx(0.0, abs=1e-12) and g["matched_pairs"] > 0


def test_no_matched_pairs_means_no_skill_not_nan(monkeypatch):
    w = World(CAMPAIGNS["GLP1_ADDICTION"], seed=0)
    monkeypatch.setattr(J, "match", lambda *a, **k: [])
    g = J.guardian(w, "alcohol", -0.4)
    assert g["no_overlap"] and g["ss_oos"] == 0.0 and g["p_dm"] == 1.0
    assert J.d_final(g) == (15.0, False)


def test_ablation_measures_after_the_temporal_guard(tmp_path, monkeypatch):
    from app.pep.agents import Decision
    q = PepQuest("t", "GLP1_ADDICTION", Ledger("t", tmp_path, model=QuestEvent), ScriptedHero(), seed=0)
    q.start()
    a = next(iter(q.agents.values()))
    a.credits = 10_000
    seen = []
    monkeypatch.setattr(J, "ablation_keeps_drug", lambda w, st: seen.append(st.design) or (True, {"ss_oos": 0.01}))
    monkeypatch.setattr(q.brain, "choose", lambda *args: Decision(["ABLATION_STRIKE", "TEMPORAL_GUARD"], "both"))
    q.decide(a, 4)
    assert seen == ["new_user"] and a.cast[4] == ["ABLATION_STRIKE", "TEMPORAL_GUARD"]


def test_leaving_during_a_crash_still_records_the_stop(tmp_path, monkeypatch):
    q = PepQuest("t", "GLP1_ADDICTION", Ledger("t", tmp_path, model=QuestEvent), ScriptedHero(), seed=0)

    def crash():
        q.stop()
        raise ValueError("boom")

    monkeypatch.setattr(q, "start", crash)
    assert q.run() is None
    assert q.ledger.events[-1].action == "stopped"


def test_the_rodent_formula_shows_the_damage_applied(tmp_path):
    rats = [e.encounter["combatResolution"] for cid in CAMPAIGNS for e in run(cid, tmp_path)[0]
            if e.encounter and e.encounter["enemyName"].startswith("Rodent")]
    assert rats
    for cr in rats:
        assert float(cr["executedFormulaLatex"].rsplit("=", 1)[1]) == pytest.approx(cr["rawDamage"], abs=0.006)


def test_the_brief_only_claims_what_the_champion_did(tmp_path):
    from app.pep import report
    q = PepQuest("t", "GLP1_ADDICTION", Ledger("t", tmp_path, model=QuestEvent), ScriptedHero(), seed=0)
    q.run()
    champ = next(a for a in q.agents.values() if a.verdict == "VALIDATED")
    champ.st.design, champ.st.adjusted = "ever", False
    champ.m[3] = {**champ.m[3], "p_corr": 0.4}
    texts = " ".join(e["text"] for e in report.decision_brief(q, champ, [])["evidence"])
    assert "Not time-zero aligned" in texts and "Not adjusted" in texts and "Does not survive" in texts
    assert "with no immortal time" not in texts

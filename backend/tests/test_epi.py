"""The Epidemiology Edition: the Judge's formulas, the damage rules, telemetry and campaign outcomes."""

import math

import numpy as np
import pytest

from app.arena.ledger import Ledger
from app.epi import judge as J
from app.epi import rules
from app.epi.agents import ScriptedEpidemiologist, menu_for
from app.epi.campaign import EpiQuest
from app.epi.campaigns import CAMPAIGNS
from app.epi.models import QuestEvent
from app.epi.scenario import Scenario


# ---------- formulas ----------

def test_clamp_never_heals_and_never_exceeds_the_level_cap():
    assert J.clamp_hp(-50, 1.0, 1) == 0
    assert J.clamp_hp(500, 1.0, 1) == 20 and J.clamp_hp(500, 1.0, 4) == 60
    assert J.clamp_hp(40, 0.2, 2) == 8  # Fact Check style multiplier
    assert [rules.D_MAX[k] for k in (1, 2, 3, 4)] == [20, 30, 45, 60]


def test_n_min_matches_fisher_z():
    r = 0.3
    assert J.n_min(r) == pytest.approx((2.80 / math.atanh(r)) ** 2 + 3)
    assert J.n_min(0.6) < J.n_min(0.3) < J.n_min(0.1)
    assert J.n_min(0.0) == float("inf")


def test_partial_r_removes_a_shared_confounder():
    # X and Y correlate only through Z: rxy = rxz * ryz, so the partial correlation is zero.
    assert J.partial_r(0.48, 0.8, 0.6) == pytest.approx(0.0, abs=1e-12)
    assert J.partial_r(0.5, 0.0, 0.0) == pytest.approx(0.5)


def test_diebold_mariano_detects_a_real_gain_and_not_a_null_one():
    rng = np.random.default_rng(0)
    base = rng.normal(0, 2, 300)
    better = base * 0.5
    stat, p = J.diebold_mariano(base, better, 5)
    assert stat > 0 and p < 0.001
    _, p_null = J.diebold_mariano(base, rng.normal(0, 2, 300), 5)
    assert p_null > 0.01


def test_composite_score_uses_the_spec_weights():
    s = J.composite_score(0.30, 100, 4, 4, 50, 50)
    assert s["total"] == pytest.approx(0.35 * 100 + 0.25 * 100 + 0.25 * 100 + 0.15 * 100)
    assert J.composite_score(None, 0, 0, 0, 0, 0)["total"] == 0
    assert sum(rules.SCORE_WEIGHTS.values()) == pytest.approx(1.0)


# ---------- the simulated world ----------

def test_scenarios_are_deterministic_and_vintages_are_incomplete():
    c = CAMPAIGNS["WASTEWATER_FLU"]
    a, b = Scenario(c, seed=3), Scenario(c, seed=3)
    days = np.arange(100, 200)
    assert np.array_equal(a.target(0, days), b.target(0, days))
    s = next(iter(c.streams))
    assert np.all(a.completeness(s, 0) < a.completeness(s, 10))


def test_preregister_needs_a_lag_declared_in_advance(tmp_path):
    c = CAMPAIGNS["WASTEWATER_FLU"]
    q = EpiQuest("t", c.id, Ledger("t", tmp_path, model=QuestEvent))
    q.start()
    vex = next(x for x in q.agents.values() if x.archetype == "HYPE")
    imara = next(x for x in q.agents.values() if x.archetype == "PIONEER")
    assert "PREREGISTER" not in menu_for(vex, 3)
    assert "PREREGISTER" in menu_for(imara, 3)


# ---------- whole campaigns ----------

def run(cid: str, tmp_path) -> tuple[list[QuestEvent], dict]:
    ledger = Ledger(f"t-{cid}", tmp_path, model=QuestEvent)
    result = EpiQuest(f"t-{cid}", cid, ledger, ScriptedEpidemiologist(), seed=0).run()
    return ledger.events, result


@pytest.mark.parametrize("cid", ["WASTEWATER_FLU", "DIGITAL_RSV", "ENV_ASTHMA"])
def test_the_planted_signal_survives_and_the_hype_falls(cid, tmp_path):
    events, result = run(cid, tmp_path)
    champ = result["champion"]
    assert champ and champ["archetype"] == "PIONEER" and champ["verdict"] == "VALIDATED"
    assert champ["skill"]["ss_surge"] > 0 and champ["skill"]["p_dm"] < rules.ALPHA
    hype = next(r for r in result["ranking"] if r["archetype"] == "HYPE")
    assert hype["status"] != "active"
    assert result["brief"]["decision"].startswith("DEPLOY")
    assert all(ev["cite"] for ev in result["brief"]["evidence"])


def test_a_null_campaign_ends_with_the_baseline_holding(tmp_path):
    _, result = run("PHARMACO_EHR", tmp_path)
    assert result["baseline_holds"] and result["champion"] is None
    assert result["brief"]["decision"].startswith("BASELINE HOLDS")
    assert not any(r["verdict"] == "VALIDATED" for r in result["ranking"])


def test_every_encounter_carries_the_telemetry_record(tmp_path):
    events, result = run("WASTEWATER_FLU", tmp_path)
    tele = [e.encounter for e in events if e.encounter]
    assert tele and result["totals"]["encounters"] == len(tele)
    keys = {"encounterId", "campaignType", "level", "enemyName", "epiTrapType", "agentId", "agentAction",
            "biostatMetrics", "combatResolution"}
    for t in tele:
        assert set(t) == keys
        assert set(t["biostatMetrics"]) == {
            "sampleSizeN", "minRequiredN", "unadjustedEffect", "adjustedEffect", "confounderName",
            "candidateLagsSearchedK", "rawPValue", "sidakCorrectedPValue", "hindsightRmse",
            "vintageRealTimeRmse", "arBaselineRmse", "outOfSampleSurgeSkill"}
        cr = t["combatResolution"]
        assert set(cr) == {"rawDamage", "abilityMultiplier", "clampedHpDelta", "executedFormulaLatex",
                           "plainEnglishEpiVerdict"}
        assert -rules.D_MAX[t["level"]] <= cr["clampedHpDelta"] <= max(rules.EUREKA_HEAL, rules.BIAS_HEAL)  # heals are positive
    assert len({t["encounterId"] for t in tele}) == len(tele)


def test_hp_and_credits_follow_the_ledger(tmp_path):
    events, result = run("DIGITAL_RSV", tmp_path)
    for r in result["ranking"]:
        rows = [e for e in events if e.agent_id == r["id"] and e.hp is not None]
        assert rows[-1].hp == r["hp"]
        assert 0 <= r["hp"] <= rules.STARTING_HP
        assert r["spent"] == sum(e.cost or 0 for e in events if e.agent_id == r["id"] and e.action == "decision")
        assert r["spent"] <= rules.STARTING_CREDITS


def test_agents_never_write_numbers_only_choices(tmp_path):
    events, _ = run("ENV_ASTHMA", tmp_path)
    for e in events:
        if e.actor == "agent":
            assert e.action == "decision" and e.hp_delta is None and e.verdict is None
            assert set(e.result) <= {"abilities", "source", "menu", "decision"}

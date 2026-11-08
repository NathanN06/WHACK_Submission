"""The research-integrity upgrade: typed claims, blinded planning, scientific statuses apart from the game, the sealed
vault's budget, champions, provenance, execution traces and the truth-versus-luck benchmark.

Numbered comments refer to the acceptance list (C1 to C12) of the implementation brief.
"""

import dataclasses
import json

import duckdb
import numpy as np
import pytest
from pydantic import ValidationError

from app.arena.ledger import Ledger
from app.pep import agents as AG
from app.pep import bridge, provenance, rules
from app.pep import challenges as C
from app.pep import evaluate as E
from app.pep import hypotheses as H
from app.pep import judge as J
from app.pep import skeptic as SK
from app.pep import telemetry as T
from app.pep import textpolicy as TP
from app.pep.campaign import PepQuest
from app.pep.campaigns import BY_LETTER, CAMPAIGNS
from app.pep.models import QuestEvent
from app.pep.registry import ChampionStore, VaultRegistry
from app.pep.world import World


def quest(path, cid="GLP1_ADDICTION", run_id="t", **kw) -> PepQuest:
    return PepQuest(run_id, cid, Ledger(run_id, path, model=QuestEvent), **kw)


TYPED = {"title": "Semaglutide worsens alcohol relapse", "outcome": "alcohol", "subgroup": "everyone", "topic": "alcohol",
         "archetype": "PIONEER", "origin": "a contrarian reading of appetite studies",
         "claim": "Semaglutide raises the risk of alcohol relapse compared with DPP-4 inhibitors.", "direction": "raises",
         "falsifier": "An adjusted new-user analysis showing fewer relapses on semaglutide."}


# ---------- C1: typed claims; clinical names pass, invented statistics do not ----------

def test_clinical_names_and_a_typed_horizon_pass_but_invented_statistics_do_not():
    ok = "In adults with type 2 diabetes, GLP-1 drugs lower IL-6 driven alcohol relapse compared with DPP-4 inhibitors."
    assert TP.check_scribe(ok) is None
    h = H._Hypothesis(**{**TYPED, "claim": ok, "direction": "lowers", "origin": "IL-6 biology and Phase 3 trials"},
                      horizon_days=365)
    assert h.horizon_days == 365 and H.check(h, BY_LETTER["A"]) is None
    with pytest.raises(ValidationError):   # the only window the cohort follows is one year: anything else is untyped
        H._Hypothesis(**{**TYPED, "claim": ok}, horizon_days=180)
    for bad, kind in [("Semaglutide lowers relapse, p = 0.03.", "p-value"), ("Relapse falls with RR = 1.4.", "ratio"),
                      ("Semaglutide gives a 24.5% reduction in relapse.", "percentage")]:
        assert kind in TP.check_scribe(bad)
        assert "measured statistic" in H.check(H._Hypothesis(**{**TYPED, "claim": bad}), BY_LETTER["A"])
    assert "effect size" in TP.check_scribe("Semaglutide halves alcohol relapse.")
    assert TP.check_attributed("The adjusted rate ratio was 0.68.", [0.6754]) is None     # a correct rounding of a release
    assert TP.check_attributed("The adjusted rate ratio was 0.42.", [0.6754])              # an invented number


def test_subgroups_must_be_recorded_supported_and_named_consistently(monkeypatch):
    c, w = BY_LETTER["A"], World(BY_LETTER["A"])
    women = H._Hypothesis(**{**TYPED, "subgroup": "women", "direction": "lowers",
                             "claim": "In women, semaglutide lowers the risk of alcohol relapse compared with DPP-4 inhibitors."})
    men = H._Hypothesis(**{**women.model_dump(), "subgroup": "men", "claim": women.claim.replace("In women", "In men")})
    assert H.check(women, c, w) is None and H.check(men, c, w) is None          # distinct subgroup claims coexist
    assert "does not encode" in H.check(women.model_copy(update={"subgroup": "everyone"}), c, w)
    assert "not a variable" in H.check(women.model_copy(update={"subgroup": "left-handed"}), c, w)
    monkeypatch.setattr("app.pep.world.SUBGROUP_MIN_INITIATORS", 10 ** 9)
    assert "too sparse" in H.check(women, c, w)


def test_a_duplicate_study_is_rejected_with_its_reason(tmp_path):
    twin = {**TYPED, "title": "Semaglutide makes relapse worse"}
    _, info = H.form(BY_LETTER["A"], 3, lambda s, u: json.dumps({"hypotheses": [TYPED, twin]}),
                     db_path=tmp_path / "none.duckdb")
    assert [r["reason"] for r in info["rejected"]] == ["duplicate study: same outcome, subgroup, direction and archetype "
                                                       "as another scroll"]


# ---------- the direction bug: a claim is tested in the direction it states ----------

def test_a_claim_pointing_the_wrong_way_is_falsified_never_validated(tmp_path):
    lowers = {**TYPED, "title": "Semaglutide cuts alcohol relapse", "direction": "lowers",
              "claim": "Semaglutide lowers the risk of alcohol relapse compared with DPP-4 inhibitors.",
              "falsifier": "No fewer relapses on semaglutide."}
    q = quest(tmp_path, n_scrolls=2, scribe=lambda s, u: json.dumps({"hypotheses": [TYPED, lowers]}))
    r = q.run()
    rows = {row["id"]: row for row in r["ranking"]}
    assert rows["h1"]["direction"] == "raises" and rows["h1"]["verdict"] != "VALIDATED"
    assert rows["h1"]["science"]["status"] == "CONTRADICTED"
    assert rows["h2"]["science"]["status"] == "SUPPORTED_ON_SYNTHETIC_VALIDATION" and q.trial["scroll"] == "h2"
    assert J.d_final({"ss_oos": 0.03, "p_dm": 1e-6}, True, direction_ok=False)[1] is False


# ---------- C2, C3: blinded planning payloads ----------

def test_planning_telemetry_is_outcome_free_and_follows_the_strict_schema(tmp_path):
    q, q0 = quest(tmp_path / "a"), quest(tmp_path / "b", campaign_obj=E.campaign_for("A_NULL"))
    q.start()
    q0.start()
    for lv in (1, 2, 3, 4):
        for aid in ("hype", "pioneer", "preprint"):
            p = T.planning_payload(q, q.agents[aid], lv, AG.menu_for(q.agents[aid], lv))
            T.assert_blinded(p)
            assert set(p["telemetry"]) == set(T.TELEMETRY_SCHEMA) | {"data_quality_flags"}
            # same patients, different planted truth: identical telemetry, so no outcome leaks into it
            p0 = T.planning_payload(q0, q0.agents[aid], lv, AG.menu_for(q0.agents[aid], lv))
            assert p0["telemetry"] == p["telemetry"]
    with pytest.raises(T.LeakError):
        T.validate({**p["telemetry"], "covariate_imbalance_flag": "RR_0.68"})


def test_earlier_findings_reach_later_decisions_but_never_the_holdout_or_the_vault(tmp_path):
    seen = []

    class Spy(AG.ScriptedHero):
        def choose(self, agent, level, menu, payload=None):
            seen.append((agent.id, level, payload))
            return super().choose(agent, level, menu, payload)

    q = quest(tmp_path, hero=Spy())
    q.run()
    ids = {lv: {f["id"] for f in p["released_findings"]} for aid, lv, p in seen if aid == "pioneer"}
    assert ids[1] == set() and not any(i.startswith("L2") for i in ids[2])
    assert "L2.rate_ratio_adjusted" in ids[3] and not any(i.startswith(("L3", "L4")) for i in ids[3])
    assert "L3.p_corrected" in ids[4] and not any(i.startswith("L4") for i in ids[4])
    p3 = next(p for aid, lv, p in seen if aid == "pioneer" and lv == 3)
    adj = next(f for f in p3["released_findings"] if f["id"] == "L2.rate_ratio_adjusted")
    assert adj["value"] == pytest.approx(q.agents["pioneer"].m[2]["adjusted"]["rr"], rel=2e-3)
    assert adj["ref"] in {e.encounter["encounterId"] for e in q.ledger.events if e.encounter}
    for _, _, p in seen:
        T.assert_blinded(p)


def test_a_deliberate_leak_is_blocked_before_any_model_call(tmp_path, monkeypatch):
    calls = []
    q = quest(tmp_path, hero=AG.LLMHero(lambda s, u: calls.append(u) or "{}"))
    q.start()
    real = T.released
    monkeypatch.setattr(T, "released", lambda a, level: real(a, level) + [{"id": "L4.peek", "ss_oos": 0.03}])
    q.decide(q.agents["pioneer"], 2)
    row = q.ledger.events[-1]
    assert row.action == "decision" and row.result["execution"]["fallback_reason"] == "LEAK_BLOCKED"
    assert calls == [] and row.result["saw"] == {"blocked": True}


def test_the_careful_policy_and_a_mock_claude_change_their_plan_when_the_flags_change(tmp_path):
    q = quest(tmp_path)
    q.start()
    a = q.agents["pioneer"]
    menu = AG.menu_for(a, 2)
    p = T.planning_payload(q, a, 2, menu)
    calm = {**p, "telemetry": {**p["telemetry"], "covariate_imbalance_flag": "BALANCED", "evidence_species_flag": "MOSTLY_HUMAN"}}
    tilted = {**p, "telemetry": {**calm["telemetry"], "covariate_imbalance_flag": "HIGH_SMD_IMBALANCE"}}
    assert AG.evidence_policy(a, 2, menu, tilted).abilities == ["BIAS_DETECTION"]
    assert AG.evidence_policy(a, 2, menu, calm).abilities == []

    def mock(system, user):
        flag = json.loads(user)["telemetry"]["covariate_imbalance_flag"]
        picks = ["BIAS_DETECTION"] if flag == "HIGH_SMD_IMBALANCE" else []
        return json.dumps({"selected_ability_ids": picks, "concern_code": "CONFOUNDING" if picks else "NONE",
                           "decision_reason": "Following the covariate imbalance flag.", "expected_tradeoff": "credits",
                           "next_research_action": "TEST", "cited_signals": ["covariate_imbalance_flag"], "line": "So be it."})

    hero = AG.LLMHero(mock)
    d = hero.choose(a, 2, menu, tilted)
    assert d.abilities == ["BIAS_DETECTION"] and d.trace["execution_mode"] == "LIVE_CLAUDE" and d.source == "claude"
    assert hero.choose(a, 2, menu, calm).abilities == []


# ---------- C11: live / fallback provenance ----------

def _reply(**over):
    base = {"selected_ability_ids": [], "concern_code": "NONE", "decision_reason": "Nothing flagged.",
            "expected_tradeoff": "", "next_research_action": "TEST", "cited_signals": [], "line": "Onward."}
    return json.dumps({**base, **over})


@pytest.mark.parametrize("reply,reason", [
    (TimeoutError("slow"), "TIMEOUT"),
    ("this is not json", "MALFORMED_JSON"),
    ('{"selected_ability_ids": "nope"}', "SCHEMA_INVALID"),
    (_reply(selected_ability_ids=["NUKE"], cited_signals=["covariate_imbalance_flag"]), "UNSUPPORTED_ACTION"),
    (_reply(selected_ability_ids=["BIAS_DETECTION", "SPECIES_GUARD"], cited_signals=["covariate_imbalance_flag"]),
     "INSUFFICIENT_CREDITS"),
    (_reply(decision_reason="The effect is a rate ratio of 0.42.", concern_code="CONFOUNDING",
            cited_signals=["covariate_imbalance_flag"]), "UNSUPPORTED_MEASUREMENT"),
    (_reply(concern_code="CONFOUNDING", cited_signals=["the_vault"]), "UNSUPPORTED_CITATION"),
])
def test_every_kind_of_bad_reply_falls_back_to_the_script_and_says_why(tmp_path, reply, reason):
    def complete(system, user):
        if isinstance(reply, Exception):
            raise reply
        return reply

    q = quest(tmp_path)
    q.start()
    a = q.agents["pioneer"]
    a.credits = 20
    menu = AG.menu_for(a, 2)
    p = T.planning_payload(q, a, 2, menu)
    d = AG.LLMHero(complete).choose(a, 2, menu, p)
    assert d.trace["execution_mode"] == "SCRIPTED_FALLBACK" and d.trace["fallback_reason"] == reason
    assert d.source == "script" and d.abilities == AG.ScriptedHero().choose(a, 2, menu, p).abilities


def test_lessons_from_the_first_live_run_values_long_reasons_and_rule_constants(tmp_path):
    """The first live run rejected half of Claude's replies for reasons that were the validator's fault: it cited a
    flag's value instead of its name, wrote long reasons, and quoted a constant of the level's damage rule."""
    q = quest(tmp_path)
    q.start()
    a = q.agents["pioneer"]
    menu = AG.menu_for(a, 1)
    p = T.planning_payload(q, a, 1, menu)
    social = p["telemetry"]["social_signal_flag"]
    other = "AFFILIATE_HEAVY" if social == "ORGANIC" else "ORGANIC"
    ok = _reply(concern_code="SOCIAL_HYPE", cited_signals=[social, "immortal_time_risk_flag"],
                decision_reason="Full credit needs 30 independent stories. " + "The posts look organic, so I keep credits. " * 30)
    d = AG.LLMHero(lambda s, u: ok).choose(a, 1, menu, p)
    assert d.trace["execution_mode"] == "LIVE_CLAUDE"
    assert d.cited == ["social_signal_flag", "immortal_time_risk_flag"] and len(d.reason) <= AG.TEXT_LIMITS["decision_reason"]
    wrong = _reply(concern_code="SOCIAL_HYPE", cited_signals=[other])            # a value the payload does not hold
    d = AG.LLMHero(lambda s, u: wrong).choose(a, 1, menu, p)
    assert d.trace["fallback_reason"] == "UNSUPPORTED_CITATION" and d.trace["invalid_action_ids"] == [other]


def test_no_key_means_an_honestly_scripted_hero_and_fallback_replays_are_identical(tmp_path, monkeypatch):
    monkeypatch.setattr("app.llm.llm_available", lambda *a: False)
    assert isinstance(AG.make_hero(True), AG.ScriptedHero)

    def dead(system, user):
        raise ConnectionError("offline")

    runs = []
    for k in range(2):
        q = quest(tmp_path / str(k), hero=AG.LLMHero(dead))
        q.run()
        runs.append([e.model_dump(exclude={"ts"}) for e in q.ledger.events])
    assert runs[0] == runs[1]
    modes = {e["result"]["execution"]["execution_mode"] for e in runs[0] if e["action"] == "decision"}
    assert modes == {"SCRIPTED_FALLBACK"}


def test_the_same_seeded_scripted_quest_replays_byte_for_byte(tmp_path):
    rows = []
    for k in range(2):
        q = quest(tmp_path / str(k), seed=3)
        q.run()
        rows.append([e.model_dump_json(exclude={"ts"}) for e in q.ledger.events])
    assert rows[0] == rows[1]


# ---------- C4: abilities change the estimator; the ledger shows the real precision ----------

def test_abilities_change_the_estimator_and_record_the_precision_they_really_cost(tmp_path):
    q = quest(tmp_path)
    q.run()
    w, a = q.w, q.agents["pioneer"]
    train = w.mask("train")
    m2 = a.m[2]
    assert m2["precision"]["se_adjusted"] == pytest.approx(J.effect(w, "alcohol", "ever", True, train)["se"])
    ever, new = J.effect(w, "alcohol", "ever", True, train), J.effect(w, "alcohol", "new_user", True, train)
    assert new["exposed_pt"] < ever["exposed_pt"] and new["pt"] == pytest.approx(ever["pt"])   # no patient deleted
    carried = J.effect(w, "alcohol", "new_user", a.st.adjusted, train)   # the estimator the abilities chose
    assert a.st.design == "new_user" and a.m[4]["rr_current"] == pytest.approx(carried["rr"])
    chrono = next(e for e in q.ledger.events if e.action == "result" and e.agent_id == "pioneer" and e.enemy == "chronolock")
    assert chrono.result["numbers"]["rr_current"] == pytest.approx(carried["rr"], rel=1e-3)


# ---------- C5: preregistration is a lock, never retroactive ----------

def test_preregistration_after_the_search_is_refused_and_evolution_cannot_buy_it(tmp_path):
    q = quest(tmp_path)
    q.run()
    searched = [a for a in q.agents.values() if 3 in a.m]
    assert searched
    for a in searched:
        K = a.st.K
        assert "refused" in q.apply_ability(a, "PREREGISTER") and a.st.K == K
    for a in q.agents.values():
        assert all(w["fix"] != "PREREGISTER" for w in bridge.weaknesses(q, a))
    assert "PREREGISTER" not in bridge.FIX_FOR_FALLEN.values()


def test_a_claim_changed_after_its_lock_fails_the_final_audit(tmp_path):
    q = quest(tmp_path)
    q.start()
    for lv in (1, 2, 3, 4):
        q.play_level(lv)
    q.critique()
    a = q.agents["pioneer"]
    a.scroll = dataclasses.replace(a.scroll, claim=a.scroll.claim + " It also works in rats.")
    bridge.endgame(q)
    assert q.trial["scroll"] == "pioneer" and q.trial["outcome"] == "INVALID METHODOLOGY"
    assert any("changed after it was locked" in f for f in q.trial["failures"])
    assert q.science["scrolls"]["pioneer"]["status"] == "INVALID_ANALYSIS"


# ---------- C6: multiplicity ----------

def test_holm_on_hand_checkable_p_values():
    assert J.holm({"a": 0.01, "b": 0.04, "c": 0.03}) == pytest.approx({"a": 0.03, "c": 0.06, "b": 0.06})
    assert J.holm({"only": 0.04}) == {"only": 0.04}


def test_holm_controls_familywise_error_for_correlated_and_selected_claims():
    """Six claims whose test statistics are correlated (rho 0.6) under the null, the best one selected: the naive
    best-of-six inflates the error; Holm over the predeclared family keeps it at or below 5%."""
    from scipy import stats
    rng = np.random.default_rng(7)
    n, k, rho = 20000, 6, 0.6
    z = np.sqrt(rho) * rng.normal(size=(n, 1)) + np.sqrt(1 - rho) * rng.normal(size=(n, k))
    p = stats.norm.sf(z)
    naive = np.mean(p.min(axis=1) < rules.ALPHA)
    holm = np.mean([min(J.holm({str(j): p[i, j] for j in range(k)}).values()) < rules.ALPHA for i in range(n)])
    assert naive > 0.10 and holm <= 0.05 + 3 * np.sqrt(0.05 * 0.95 / n)


def test_the_holm_family_is_every_recruited_scroll_even_the_fallen(tmp_path):
    q = quest(tmp_path)
    r = q.run()
    fam = r["science"]["family"]
    assert fam["kind"] == "Holm" and fam["size"] == len(q.agents) == 3
    assert any(e.action == "analysis_plan" and e.result["holm_family"] == list(q.agents) for e in q.ledger.events)


# ---------- C7: repeated-seed truth-versus-luck evaluation ----------

def test_the_benchmark_covers_null_and_true_worlds_and_recomputes_from_its_logs(tmp_path):
    s = E.run([100, 101], ["A", "B", "D"], n_scrolls=6, reuse_seeds=1, out_dir=tmp_path, log=None)
    m = s["metrics"]
    assert m["worlds"] == {"total": 6, "null": 2, "with_true_effects": 4}
    assert m["sign_errors"] == 0 and m["familywise_error_null_worlds"]["k"] == 0
    assert m["power_by_estimand_valid_design"]["A:alcohol"]["k"] == 2
    saved = json.loads((tmp_path / "evaluation_summary.json").read_text(encoding="utf-8"))
    assert E.summarize(E.load(tmp_path / "runs.jsonl")) == saved["metrics"]
    worlds = [r for r in E.load(tmp_path / "runs.jsonl") if r["type"] == "world"]
    assert len({w["fingerprint"] for w in worlds}) == len(worlds)          # independent worlds
    assert s["live_vs_scripted"]["status"] == "PENDING"                    # no live run, so no gain is claimed
    assert {r["truth_class"] for r in E.load(tmp_path / "runs.jsonl") if r["type"] == "claim"} >= {"NULL", "TRUE_IMPORTANT", "OPPOSITE"}


def test_a_vault_success_after_a_holdout_failure_is_not_support():
    """Found by the benchmark (world B, seed 119, no true effect): a contrarian claim failed the holdout, the Bridge
    locked it as the most promising survivor, and the sealed vault passed by chance. One unreplicated success is
    not support, so it stays INCONCLUSIVE."""
    _, _, q = E.run_world("B", 119, 6)
    h6 = q.science["scrolls"]["h6"]
    assert q.trial["scroll"] == "h6" and q.trial["gain"] and h6["holm_p"] >= rules.ALPHA
    assert h6["status"] == "INCONCLUSIVE" and "unreplicated" in " ".join(h6["reasons"])
    assert q.science["best"] is None


# ---------- C8: the sealed vault's budget ----------

def test_reopening_a_vault_is_a_replay_never_a_new_confirmation(tmp_path):
    reg = VaultRegistry(tmp_path / "vaults.json")
    q1 = quest(tmp_path / "1", registry=reg)
    q1.run()
    assert q1.trial["vault_kind"] == "NEW_INDEPENDENT" and q1.trial["outcome"] == "VALIDATED DISCOVERY"
    q2 = quest(tmp_path / "2", registry=reg)
    q2.run()
    assert q2.cohort["quests_before"] == 1 and not q2.cohort["fresh"]
    assert q2.trial["vault_kind"] == "REPLAY" and q2.trial["outcome"] == "NO NEW INDEPENDENT CONFIRMATION"
    assert q2.trial["confirmation_label"] == "PRIOR VALIDATION - NO NEW INDEPENDENT CONFIRMATION"
    assert q2.science["scrolls"]["pioneer"]["status"] == "PROVISIONALLY_SUPPORTED"
    kinds = [e["kind"] for e in reg.cohort(q1.w.fingerprint())["evaluations"]]
    assert kinds == ["NEW_INDEPENDENT", "REPLAY"]
    assert reg.assign_seed("GLP1_ADDICTION", "x") == 1   # a live quest is given a cohort nobody used


# ---------- C9: champions and fair challengers ----------

def test_champions_persist_defend_on_fresh_cohorts_and_stay_in_their_own_campaign(tmp_path):
    store, reg = ChampionStore(tmp_path / "champions.json"), VaultRegistry(tmp_path / "vaults.json")
    q1 = quest(tmp_path / "1", run_id="q1", seed=1, n_scrolls=3, registry=reg, champions=store)
    q1.run()
    rec = store.get("GLP1_ADDICTION")
    assert q1.champion_result["outcome"] == "CROWNED"
    assert rec["status"] == "SUPPORTED_ON_SYNTHETIC_VALIDATION" and rec["confirmations"] == 1
    assert "Not clinical evidence" in rec["label"]
    q2 = quest(tmp_path / "2", run_id="q2", seed=2, n_scrolls=3, registry=reg, champions=store)
    q2.run()
    inc = q2.agents["h1"]
    assert inc.scroll.origin_mode == "INCUMBENT" and inc.scroll.hypothesis_id == rec["hypothesis"]["hypothesis_id"]
    assert len(q2.agents) == 3 and sum(a.scroll.origin_mode == "INCUMBENT" for a in q2.agents.values()) == 1
    assert inc.scroll.incumbent["confirmations"] == 1             # its history rides along as context...
    recruit = next(e for e in q2.ledger.events if e.action == "recruit" and e.agent_id == "h1")
    assert recruit.hp == rules.STARTING_HP                         # ...but it starts like any challenger: no head start
    assert q2.champion_result["outcome"] == "DEFENDED" and store.get("GLP1_ADDICTION")["confirmations"] == 2
    q3 = quest(tmp_path / "3", run_id="q3", cid="BPC157_TENDON", n_scrolls=2, registry=reg, champions=store)
    assert q3.incumbent is None
    q4 = quest(tmp_path / "4", run_id="q4", seed=1, n_scrolls=3, registry=reg, champions=store)   # an old cohort again
    q4.run()
    assert q4.trial["independent"] is False and store.get("GLP1_ADDICTION")["confirmations"] == 2


def test_a_champion_can_be_dethroned_but_its_provenance_is_kept():
    store = ChampionStore()
    row = {"id": "h1", "status": "PROVISIONALLY_SUPPORTED", "ss_oos": 0.02, "holm_p": 0.01, "trial_outcome": None,
           "confirmation_kind": None, "spec_sha256": None, "manifest_ids": ["PMID:1"],
           "hypothesis": {"hypothesis_id": "H-1", "title": "t", "claim": "c"}}
    store.settle("S", {"quest_id": "a", "seed": 1, "world": "w1", "scrolls": [row], "incumbent_id": None})
    out = store.settle("S", {"quest_id": "b", "seed": 2, "world": "w2", "incumbent_id": "h1",
                             "scrolls": [{**row, "status": "CONTRADICTED"}]})
    assert out["outcome"] == "DETHRONED" and store.get("S") is None
    assert store._read()["retired"]["S"][0]["hypothesis"]["hypothesis_id"] == "H-1"


# ---------- C10: provenance and honest labels ----------

def _evidence_db(path):
    con = duckdb.connect(str(path))
    con.execute("CREATE TABLE pep_papers (campaign VARCHAR, topic VARCHAR, title VARCHAR, pub_year INTEGER, design VARCHAR, "
                "species VARCHAR, authors VARCHAR, url VARCHAR, pmid VARCHAR, doi VARCHAR, source_id VARCHAR, journal VARCHAR)")
    con.execute("CREATE TABLE pep_queries (campaign VARCHAR, topic VARCHAR, source VARCHAR, query VARCHAR, hit_count INTEGER, "
                "stored INTEGER, fetched_at TIMESTAMP)")
    con.execute("CREATE TABLE pep_trials (campaign VARCHAR, topic VARCHAR, nct_id VARCHAR, title VARCHAR, status VARCHAR, "
                "allocation VARCHAR, has_results BOOLEAN, phases VARCHAR, enrollment INTEGER, url VARCHAR)")
    con.execute("CREATE TABLE pep_faers (campaign VARCHAR, topic VARCHAR, drug_group VARCHAR, reactions VARCHAR, "
                "drug_and_reaction INTEGER, drug_total INTEGER, reaction_total INTEGER, all_reports INTEGER, fetched_at TIMESTAMP)")
    for t in ("alcohol", "opioid", "nicotine"):
        con.executemany("INSERT INTO pep_papers VALUES ('A', ?, ?, 2024, 'rct', 'human', 'Smith J', ?, ?, NULL, ?, 'J')",
                        [(t, f"{t} paper {i}", f"https://europepmc.org/{t}{i}", f"9{i}{len(t)}", f"MED{i}") for i in range(4)])
        con.execute("INSERT INTO pep_queries VALUES ('A', ?, 'europepmc', 'q', 4, 4, now())", [t])
        con.execute("INSERT INTO pep_trials VALUES ('A', ?, ?, 'T', 'COMPLETED', 'RANDOMIZED', false, 'PHASE2', 40, 'u')",
                    [t, f"NCT0000{len(t)}"])
    con.execute("INSERT INTO pep_faers VALUES ('A', 'alcohol', 'glp1', 'alcohol', 3, 100, 50, 1000, now())")
    con.close()
    return path


def test_every_reported_number_traces_to_the_ledger_and_every_citation_is_a_stored_identifier(tmp_path, monkeypatch):
    db = _evidence_db(tmp_path / "ev.duckdb")
    monkeypatch.setattr(H, "DB_PATH", db)
    q = quest(tmp_path / "q", n_scrolls=4)
    r = q.run()
    seqs = {e.seq for e in q.ledger.events}
    for link in r["brief"]["provenance"]:
        assert link["ledger_seq"] in seqs and link["origin"] == "SIMULATED_COHORT"
        assert link["method_version"] == rules.ANALYSIS_VERSION and link["seed"] == q.seed
    con = duckdb.connect(str(db), read_only=True)
    stored = {f"PMID:{p}" for (p,) in con.execute("SELECT pmid FROM pep_papers").fetchall()}
    stored |= {f"NCT:{n}" for (n,) in con.execute("SELECT nct_id FROM pep_trials").fetchall()}
    con.close()
    items = [x for s in r["manifest"]["scrolls"].values() for x in s["items"]]
    real = [x for x in items if x["type"].startswith("REAL_")]
    assert real and all(x["id"] in stored for x in real)
    assert {x["type"] for x in items} >= {"SIMULATED_COHORT", "REAL_PUBLICATION_METADATA", "REAL_TRIAL_RECORD"}
    assert all(x["type"] == "REAL_PHARMACOVIGILANCE_REPORTS" and "not evidence" in x["relevance"]
               for x in r["manifest"]["campaign"])
    text = json.dumps(r).lower()
    assert "confirmed in real patients" not in text and "safety signal confirmed" not in text and "backs it" not in text


def test_the_skeptic_uses_registered_tests_changes_no_hp_and_falls_back_from_bad_proposals(tmp_path):
    q = quest(tmp_path)
    q.run()
    rows = [e for e in q.ledger.events if e.action == "skeptic_result"]
    assert rows and all(not e.hp_delta for e in rows) and all(e.result["test"] in C.TESTS for e in rows)
    bad = json.dumps({"challenges": [{"scroll_id": "pioneer", "challenge_type": "astrology", "reason": "stars",
                                      "suggested_allowlisted_test_id": "astrology"}]})
    picks, trace = SK.choose([q.agents["pioneer"]], lambda s, u: bad)
    assert trace["execution_mode"] == "SCRIPTED_FALLBACK" and picks[0]["source"] == "script"
    assert picks[0]["challenge_type"] in C.TESTS


# ---------- C12: the game and the science can disagree ----------

def test_the_game_winner_and_the_scientific_conclusion_can_disagree_without_error(tmp_path):
    women = {**TYPED, "title": "Semaglutide cuts alcohol relapse in women", "subgroup": "women", "direction": "lowers",
             "claim": "In women, semaglutide lowers the risk of alcohol relapse compared with DPP-4 inhibitors.",
             "falsifier": "No fewer relapses in women on semaglutide."}
    q = quest(tmp_path, n_scrolls=2, scribe=lambda s, u: json.dumps({"hypotheses": [TYPED, women]}))
    r = q.run()
    assert r["champion"]["id"] == "h2" and r["champion"]["verdict"] == "VALIDATED"   # it won the game...
    assert q.trial["outcome"] == "UNJUSTIFIED CONFIDENCE"                             # ...and failed the sealed vault
    assert r["science"]["best_supported"] is None and r["science"]["agree"] is False
    assert r["brief"]["decision"].startswith("BASELINE HOLDS")
    assert provenance.paper_id({"doi": "10.1/x"}) == "DOI:10.1/x"

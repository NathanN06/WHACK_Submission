import json

from app.arena import agents
from app.arena.models import Gladiator, GladiatorState

CATALOG = [
    {"name": "carbs", "day": 1, "description": "Carbohydrate in the meal, grams"},
    {"name": "fiber", "day": 2, "description": "Fibre in the meal, grams"},
    {"name": "fat", "day": 2, "description": "Fat in the meal, grams"},
]


def state_with_trial(**trial):
    s = GladiatorState(gladiator=Gladiator(id="G1", claim="fibre helps", add_features=["fiber"]))
    s.results["added_value"] = {"passed": True, **trial}
    return s


def test_scripted_lanista_proposes_todays_features():
    out = agents.ScriptedLanista().propose(2, CATALOG, [], k=5)
    assert [g.add_features for g in out] == [["fiber"], ["fat"]]


def test_scripted_lanista_reads_a_crowd_theory():
    g = agents.ScriptedLanista().theory("I reckon fibre flattens the spike", CATALOG)
    assert g.add_features == ["fiber"] and g.origin == "crowd"
    assert agents.ScriptedLanista().theory("pineapple on pizza", CATALOG) is None


def test_scripted_sceptic_sends_inquisitor_when_too_good():
    test, _ = agents.ScriptedSceptic().next_attack(state_with_trial(too_good=True),
                                                    ["shuffle_test", "leak_audit"], 30)
    assert test == "leak_audit"
    test, _ = agents.ScriptedSceptic().next_attack(state_with_trial(too_good=False),
                                                    ["shuffle_test", "leak_audit"], 30)
    assert test == "shuffle_test"


def fake_model(*replies):
    calls = []

    def complete(system, user):
        calls.append(json.loads(user))
        return replies[min(len(calls) - 1, len(replies) - 1)]

    complete.calls = calls
    return complete


def test_llm_lanista_parses_json_inside_prose():
    model = fake_model('Sure! {"gladiators": [{"claim": "Fat slows it", "add_features": ["fat"]}]}')
    out = agents.LLMLanista(model).propose(2, CATALOG, [], k=5)
    assert out[0].add_features == ["fat"] and out[0].claim == "Fat slows it"


def test_llm_retries_once_then_falls_back_to_script():
    model = fake_model("not json", "still not json")
    out = agents.LLMLanista(model).propose(2, CATALOG, [], k=5)
    assert len(model.calls) == 2 and "your_last_reply_was_invalid" in model.calls[1]
    assert [g.add_features for g in out] == [["fiber"], ["fat"]]  # scripted fallback


def test_llm_sceptic_cannot_pick_an_option_it_was_not_offered():
    model = fake_model('{"test": "final_boss", "line": "Straight to the boss!"}')
    test, _ = agents.LLMSceptic(model).next_attack(state_with_trial(), ["shuffle_test"], 30)
    assert test == "shuffle_test"


def test_api_errors_fall_back_to_script():
    def broken(system, user):
        raise ConnectionError("wifi died")
    back, _ = agents.LLMLanista(broken).decide(state_with_trial())
    assert back is True


def test_llm_reply_with_no_features_falls_back_instead_of_crashing():
    model = fake_model('{"gladiators": [{"claim": "nothing", "add_features": []}]}')
    out = agents.LLMLanista(model).propose(2, CATALOG, [], k=5)
    assert [g.add_features for g in out] == [["fiber"], ["fat"]]
    g = agents.LLMLanista(model).theory("I reckon fibre flattens the spike", CATALOG)
    assert g.add_features == ["fiber"]


def test_scripted_claims_read_like_real_hypotheses():
    out = agents.ScriptedLanista().propose(2, CATALOG, [], k=5)
    claims = [g.claim for g in out]
    assert all("changes the rise after a meal" not in c for c in claims)
    assert [g.expected_direction for g in out] == ["negative", "negative"]  # fibre and fat blunt the spike


def test_llm_agents_count_their_fallbacks():
    def broken(system, user):
        raise ConnectionError("no key")
    lanista = agents.LLMLanista(broken)
    lanista.propose(2, CATALOG, [], k=5)
    lanista.decide(state_with_trial())
    assert lanista.fallbacks == 2


def test_api_key_is_read_from_dotenv(tmp_path, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    (tmp_path / ".env").write_text('# secrets\nANTHROPIC_API_KEY="sk-test-123"\n')
    agents.load_env_key(tmp_path / ".env")
    import os
    assert os.environ["ANTHROPIC_API_KEY"] == "sk-test-123"


def test_roster_lanista_sends_exactly_the_hypotheses_you_wrote():
    roster = {2: [{"claim": "My fibre idea", "add_features": ["fiber"]}]}
    out = agents.RosterLanista(roster).propose(2, CATALOG, [], k=5)
    assert [(g.claim, g.add_features, g.origin) for g in out] == [("My fibre idea", ["fiber"], "researcher")]
    assert agents.RosterLanista(roster).propose(3, CATALOG, [], k=5) == []  # nothing ticked that day


def test_default_roster_is_the_scripted_proposals():
    days = agents.default_roster(CATALOG)
    assert [d["day"] for d in days] == [1, 2, 3]
    assert [h["add_features"] for h in days[1]["hypotheses"]] == [["fiber"], ["fat"]]
    assert days[1]["features"] == ["fiber", "fat"]  # unlocked that day

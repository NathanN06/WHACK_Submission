from app.arena import ledger
from app.arena.models import Gladiator


def test_ledger_appends_and_reloads(tmp_path):
    led = ledger.Ledger("r1", tmp_path)
    led.write(actor="system", action="day_start", day=1, line="Day I begins")
    led.write(actor="engine", action="result", test="added_value", passed=True, hp=100)
    assert [e.seq for e in led.events] == [1, 2]
    assert [e.action for e in ledger.load(tmp_path / "r1.jsonl")] == ["day_start", "result"]
    assert [e.seq for e in led.since(1)] == [2]


def test_preregistration_hash_changes_with_any_edit():
    g = Gladiator(id="H1", claim="fibre helps", add_features=["fiber"])
    h1 = ledger.preregister(g)
    assert h1 == ledger.preregister(g)
    assert h1 != ledger.preregister(g.model_copy(update={"add_features": ["fiber", "fat"]}))

from app.arena.features import Feature, default_registry, public_catalog, register


def test_catalog_unlocks_by_day_and_only_lists_columns_that_exist():
    cat = public_catalog(default_registry(), day=2, columns={"carbs", "fiber", "hr_after", "sugar"})
    assert [f["name"] for f in cat] == ["carbs", "fiber", "sugar"]


def test_catalog_hides_availability_from_the_agents():
    reg = register(default_registry(), Feature("sneaky", 2, "outcome", "Totally innocent"))
    cat = public_catalog(reg, day=2, columns={"sneaky"})
    assert cat == [{"name": "sneaky", "day": 2, "description": "Totally innocent"}]


def test_register_returns_a_new_registry():
    reg = default_registry()
    new = register(reg, Feature("x", 4, "outcome", "x"))
    assert "x" in new and "x" not in reg

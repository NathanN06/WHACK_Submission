import pandas as pd
import pytest

from app.arena import data


def test_hours_since_last_meal_is_per_person_and_in_order():
    df = pd.DataFrame({
        "participant_id": ["A", "A", "A", "B"],
        "meal_start": ["2026-01-01 12:00", "2026-01-01 08:00", "2026-01-01 18:30", "2026-01-01 09:00"],
    })
    out = data.add_derived(df)
    gap = out["hours_since_last_meal"]
    assert "meal_start" not in out.columns
    assert gap[0] == 4.0 and gap[2] == 6.5
    assert pd.isna(gap[1]) and pd.isna(gap[3])  # first meal of each person has no gap


def test_loader_against_a_tiny_database(tmp_path):
    # Mirrors the real whack.duckdb schema (see docs/schema.txt).
    duckdb = pytest.importorskip("duckdb")
    con = duckdb.connect(str(tmp_path / "t.duckdb"))
    con.execute("""CREATE TABLE meal_responses AS SELECT * FROM (VALUES
        (1, 'CGM-001', 'CGM-001', TIMESTAMP '2026-01-01 08:00', 8, 450.0, 60.0, 20.0, 10.0, 5.0, 12.0, 95.0, 40.0, 50.0, true),
        (2, 'CGM-001', 'CGM-001', TIMESTAMP '2026-01-01 13:00', 13, 225.0, 30.0, 10.0, 5.0, 2.0, 8.0, 90.0, 20.0, 40.0, true),
        (3, 'BUT-101001', 'BUT-101', TIMESTAMP '2026-01-01 09:00', 9, 330.0, 45.0, 15.0, 8.0, NULL, 9.0, 85.0, 30.0, 45.0, true),
        (4, 'CGM-001', 'CGM-001', TIMESTAMP '2026-01-01 19:00', 19, 80.0, 10.0, 5.0, 2.0, 1.0, 1.0, 99.0, 99.0, 60.0, false))
        t(meal_event_id, session_id, participant_id, meal_ts, hour_of_day, calories, carbs_g, protein_g,
          fat_g, fiber_g, sugar_g, baseline_mgdl, glucose_rise_mgdl, minutes_to_peak, clean)""")
    con.execute("""CREATE TABLE meal_events AS SELECT * FROM (VALUES
        (1, 'CGM-001', 'CGM-001', TIMESTAMP '2026-01-01 08:00', 450.0),
        (2, 'CGM-001', 'CGM-001', TIMESTAMP '2026-01-01 13:00', 225.0),
        (3, 'BUT-101001', 'BUT-101', TIMESTAMP '2026-01-01 09:00', 330.0),
        (4, 'CGM-001', 'CGM-001', TIMESTAMP '2026-01-01 19:00', 80.0))
        t(meal_event_id, session_id, participant_id, ts, calories)""")
    con.execute("""CREATE TABLE participants AS SELECT * FROM (VALUES
        ('CGM-001', 6.1), ('BUT-101', NULL)) t(participant_id, hba1c_pct)""")
    df = data.load_meals(con, "CGM-%")
    assert len(df) == 2  # the unclean meal is excluded
    assert set(data.REQUIRED) <= set(df.columns)
    assert df["hours_since_last_meal"].dropna().tolist() == [5.0]
    assert df["hba1c"].tolist() == [6.1, 6.1]

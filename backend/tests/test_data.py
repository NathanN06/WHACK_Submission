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


def test_the_libre_twin_rebuilds_each_meal_from_real_libre_scans(tmp_path):
    duckdb = pytest.importorskip("duckdb")
    con = duckdb.connect(str(tmp_path / "t.duckdb"))
    con.execute("""CREATE TABLE meal_responses AS SELECT * FROM (VALUES
        (1, 'CGM-001', 'CGM-001', TIMESTAMP '2026-01-01 08:00', true),
        (2, 'CGM-001', 'CGM-001', TIMESTAMP '2026-01-01 13:00', true))
        t(meal_event_id, session_id, participant_id, meal_ts, clean)""")
    scans = [("07:50", 100)] + [(f"{8 + m // 60:02d}:{m % 60:02d}", v)
                                for m, v in zip(range(0, 105, 15), [105, 130, 150, 140, 120, 110, 100])]
    scans += [("12:50", 90)] + [(f"{13 + m // 60:02d}:{m % 60:02d}", 40) for m in range(0, 105, 15)]  # at the floor
    rows = ", ".join(f"('CGM-001', TIMESTAMP '2026-01-01 {t}', 'libre', {v})" for t, v in scans)
    con.execute(f"CREATE TABLE glucose AS SELECT * FROM (VALUES {rows}) t(session_id, ts, sensor, glucose_mgdl)")
    dexcom = pd.DataFrame({"participant_id": ["CGM-001"] * 2, "meal_event_id": ["1", "2"], "rise": [70.0, 30.0],
                           "baseline_glucose": [110.0, 95.0], "time_to_peak": [35.0, 20.0], "carbs": [60.0, 30.0]})
    twin = data.libre_twin(con, dexcom)
    assert twin["meal_event_id"].tolist() == ["1"]  # meal 2 sits at the 40 mg/dL floor
    assert twin.iloc[0][["rise", "baseline_glucose", "time_to_peak"]].tolist() == [50.0, 100.0, 30.0]
    assert twin.iloc[0]["carbs"] == 60.0 and list(twin.columns) == list(dexcom.columns)

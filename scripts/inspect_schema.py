"""Print the columns and a few rows of every table the arena reads.

Run: .venv/bin/python scripts/inspect_schema.py
Then make SELECT in backend/app/arena/data.py match what you see.
"""

import duckdb

con = duckdb.connect("data/whack.duckdb", read_only=True)
for table in ["meal_responses", "meal_events", "participants", "glucose", "cgmacros_minute"]:
    print(f"\n===== {table}")
    try:
        print(con.sql(f"DESCRIBE {table}"))
        print(con.sql(f"SELECT * FROM {table} LIMIT 3"))
    except duckdb.Error as e:
        print(f"  (not available: {e})")

print("\nmeal_responses rows per dataset and sensor:")
cols = {r[0] for r in con.execute("DESCRIBE meal_responses").fetchall()}
group = "left(participant_id, 3)" + (", sensor" if "sensor" in cols else "")
print(con.sql(f"SELECT {group}, count(*) AS meals, count(DISTINCT participant_id) AS people "
              f"FROM meal_responses WHERE clean GROUP BY ALL ORDER BY ALL"))

"""Play one game from the command line and print the ledger as it is written.

  python scripts/run_arena.py --synthetic            # no database needed
  python scripts/run_arena.py                        # real data, scripted agents
  python scripts/run_arena.py --llm --emperor real   # Claude as Lanista and Sceptic
"""

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.arena.agents import make_agents  # noqa: E402
from app.arena.ledger import Ledger  # noqa: E402
from app.arena.orchestrator import Arena  # noqa: E402


def show(e) -> None:
    hp = "" if e.hp is None else f"hp={e.hp:<3}"
    print(f"{e.seq:>3} D{e.day} {e.actor:<8} {e.gladiator_id or '':<4} {hp:<7} "
          f"{e.verdict or '':<10} rep={e.reputation:<4} $={e.denarii:<3} {e.line or ''}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--llm", action="store_true", help="use Claude (needs ANTHROPIC_API_KEY)")
    ap.add_argument("--synthetic", action="store_true", help="use made-up meals, no database")
    ap.add_argument("--emperor", choices=["real", "fake"])
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--perm", type=int, default=500, help="shuffles per Shuffler test")
    args = ap.parse_args()

    if args.synthetic:
        sys.path.insert(0, str(ROOT / "backend"))
        from tests.fixtures import make_meals, make_sensor_pair
        train = make_meals(30, seed=args.seed)
        test = make_meals(20, seed=args.seed + 50, prefix="B")
        sensors = make_sensor_pair(train)
    else:
        from app.arena.data import load_all
        train, test, sensors = load_all(ROOT / "data" / "whack.duckdb")
        print(f"Loaded {train.participant_id.nunique()} CGMacros people, "
              f"{test.participant_id.nunique()} BUT CGM people, sensors: {list(sensors) or 'one'}")

    run_id = f"cli-s{args.seed}-{'llm' if args.llm else 'script'}"
    ledger = Ledger(run_id, ROOT / "data" / "runs", on_write=show)
    lanista, sceptic = make_agents(args.llm)
    Arena(run_id, train, test, sensors, lanista, sceptic, ledger, emperor=args.emperor,
          seed=args.seed, n_perm=args.perm).run()
    print(f"\nLedger saved to {ledger.path}")


if __name__ == "__main__":
    main()

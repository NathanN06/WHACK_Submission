"""Play one Hypothesis Gauntlet from the command line and print the ledger as it is written.

  python scripts/run_gauntlet.py --synthetic           # made-up meals, no database needed
  python scripts/run_gauntlet.py                       # real data (data/whack.duckdb), scripted agents
  python scripts/run_gauntlet.py --llm                 # Claude as Researcher and Skeptic
  python scripts/run_gauntlet.py --synthetic --out frontend/src/demo-gauntlet.jsonl
"""

import argparse
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.arena.ledger import Ledger  # noqa: E402
from app.gauntlet.agents import make_roles  # noqa: E402
from app.gauntlet.campaign import Gauntlet  # noqa: E402
from app.gauntlet.models import QuestEvent  # noqa: E402


def show(e) -> None:
    hp = "" if e.hp is None else f"hp={e.hp:<3} cr={e.credits:<3}"
    delta = "" if e.hp_delta is None else f"{e.hp_delta:+d}"
    print(f"{e.seq:>4} L{e.level} {e.actor:<10} {e.agent_id or '':<4} {hp:<14} {delta:<5} {e.line or ''}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--llm", action="store_true", help="use Claude (needs ANTHROPIC_API_KEY)")
    ap.add_argument("--synthetic", action="store_true", help="use made-up meals, no database")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--perm", type=int, default=200, help="shuffles per Chimera overfitting test")
    ap.add_argument("--heroes", type=int, default=8, help="hypotheses the Researcher sends in (plus 4 decoys)")
    ap.add_argument("--theory", action="append", default=[], help="your own hypothesis in words (repeatable)")
    ap.add_argument("--out", help="also copy the finished ledger here (e.g. the frontend demo)")
    args = ap.parse_args()

    if args.synthetic:
        from tests.fixtures import make_quest_world
        train, test, sensors = make_quest_world(args.seed)
    else:
        from app.arena.data import load_all
        train, test, sensors = load_all(ROOT / "data" / "whack.duckdb")

    run_id = f"quest-s{args.seed}-{'synthetic' if args.synthetic else 'real'}-{'llm' if args.llm else 'script'}"
    ledger = Ledger(run_id, ROOT / "data" / "quests", on_write=show, model=QuestEvent)
    researcher, skeptic = make_roles(args.llm)
    from app.main import quest_sources
    Gauntlet(run_id, train, test, sensors, researcher, skeptic, ledger, seed=args.seed,
             n_perm=args.perm, max_heroes=args.heroes, theories=args.theory,
             sources=quest_sources(train, test)).run()
    print(f"\nLedger saved to {ledger.path}")
    if args.out:
        shutil.copy(ledger.path, args.out)
        print(f"Copied to {args.out}")


if __name__ == "__main__":
    main()

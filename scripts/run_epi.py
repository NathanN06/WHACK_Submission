"""Run one Epidemiology Edition campaign from the command line and print its ledger.

    .venv/bin/python scripts/run_epi.py A                       # scripted agents
    .venv/bin/python scripts/run_epi.py all --out frontend/src/demo   # record the four demo campaigns
    .venv/bin/python scripts/run_epi.py B --llm                 # Claude plays the four agents (needs a key)
"""

import argparse
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.arena.ledger import Ledger  # noqa: E402
from app.epi.agents import make_epidemiologist  # noqa: E402
from app.epi.campaign import EpiQuest  # noqa: E402
from app.epi.campaigns import BY_LETTER, CAMPAIGNS  # noqa: E402
from app.epi.models import QuestEvent  # noqa: E402


def show(e: QuestEvent) -> None:
    who = f"{e.agent_id or '':8}"
    hp = f"hp={e.hp:<3}" if e.hp is not None else "      "
    d = f"{e.hp_delta:+4d}" if e.hp_delta else "    "
    print(f"{e.seq:4} L{e.level or 0} {e.action:15} {who} {hp} {d}  {e.line or ''}"[:200])


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("campaign", help="A, B, C, D, a campaign id, or all")
    ap.add_argument("--llm", action="store_true")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--out", help="also copy each ledger into this folder as demo-<letter>.jsonl")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()
    ids = list(CAMPAIGNS) if args.campaign == "all" else [
        BY_LETTER[args.campaign.upper()].id if args.campaign.upper() in BY_LETTER else args.campaign]
    for cid in ids:
        c = CAMPAIGNS[cid]
        run_id = f"epi-{c.letter}-s{args.seed}-{'llm' if args.llm else 'script'}"
        ledger = Ledger(run_id, ROOT / "data" / "quests", on_write=None if args.quiet else show, model=QuestEvent)
        result = EpiQuest(run_id, cid, ledger, make_epidemiologist(args.llm), seed=args.seed).run()
        print(f"\n[{c.letter}] {result['headline'] if result else 'no result'}")
        if result:
            for r in result["ranking"]:
                print(f"   {r['name']:6} {r['verdict']:10} hp={r['hp']:3} score={r['score']['total']:6.1f} "
                      f"traps {r['traps_falsified']}/{r['traps_faced']} spent={r['spent']}")
        if args.out:
            out = ROOT / args.out
            out.mkdir(parents=True, exist_ok=True)
            shutil.copy(ledger.path, out / f"demo-{c.letter}.jsonl")
            print(f"   copied to {out / f'demo-{c.letter}.jsonl'}")


if __name__ == "__main__":
    main()

"""Run one Peptide & GLP-1 campaign from the command line and print its ledger.

    .venv/bin/python scripts/run_pep.py A                       # scripted agents
    .venv/bin/python scripts/run_pep.py all --out frontend/src/demo   # record the four demo campaigns
    .venv/bin/python scripts/run_pep.py B --llm                 # Claude plays the Alchemist (needs a key)
"""

import argparse
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.arena.ledger import Ledger  # noqa: E402
from app.pep.agents import make_hero  # noqa: E402
from app.pep.campaign import PepQuest  # noqa: E402
from app.pep.campaigns import BY_LETTER, CAMPAIGNS  # noqa: E402
from app.pep.models import QuestEvent  # noqa: E402


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
        run_id = f"pep-{c.letter}-s{args.seed}-{'llm' if args.llm else 'script'}"
        ledger = Ledger(run_id, ROOT / "data" / "quests", on_write=None if args.quiet else show, model=QuestEvent)
        result = PepQuest(run_id, cid, ledger, make_hero(args.llm), seed=args.seed).run()
        print(f"\n[{c.letter}] {result['headline'] if result else 'no result'}")
        if result:
            print(f"   decision: {result['brief']['decision']}")
            for r in result["ranking"]:
                status = (r.get("science") or {}).get("status", "")
                print(f"   {r['name']:28} game {r['verdict']:10} science {status:34} hp={r['hp']:3} "
                      f"score={r['score']['total']:6.1f} traps {r['traps_falsified']}/{r['traps_faced']} spent={r['spent']}")
        if args.out:
            out = ROOT / args.out
            out.mkdir(parents=True, exist_ok=True)
            shutil.copy(ledger.path, out / f"demo-{c.letter}.jsonl")
            print(f"   copied to {out / f'demo-{c.letter}.jsonl'}")


if __name__ == "__main__":
    main()

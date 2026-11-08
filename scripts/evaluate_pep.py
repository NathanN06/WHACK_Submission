"""The truth-versus-luck benchmark of the Gauntlet: many independent seeded worlds, the whole pipeline, scored
against the planted truth only after each run (backend/app/pep/evaluate.py).

    .venv/bin/python scripts/evaluate_pep.py                          # 20 seeds x 6 scenarios, scripted hero
    .venv/bin/python scripts/evaluate_pep.py --seeds 5 --scenarios A,B
    .venv/bin/python scripts/evaluate_pep.py --out docs               # also copy evaluation_summary.json to docs/
    .venv/bin/python scripts/evaluate_pep.py --live                   # also a matched live-Claude run (needs a key)

Writes data/eval/<timestamp>/runs.jsonl (every claim, world and reuse check) and evaluation_summary.json.
"""

import argparse
import json
import shutil
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.pep import evaluate as E  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=20, help="independent worlds per scenario")
    ap.add_argument("--first-seed", type=int, default=100, help="seed 0 is the published demo's; start elsewhere")
    ap.add_argument("--scenarios", default=",".join(E.SCENARIOS), help="comma-separated: " + ", ".join(E.SCENARIOS))
    ap.add_argument("--scrolls", type=int, default=6)
    ap.add_argument("--reuse-seeds", type=int, default=2, help="worlds per scenario run twice to test vault reuse")
    ap.add_argument("--live", action="store_true", help="also run Claude as the hero on the same seeds")
    ap.add_argument("--out", help="also copy evaluation_summary.json into this folder (e.g. docs)")
    args = ap.parse_args()
    live = None
    if args.live:
        from app.pep.agents import make_hero
        live = make_hero(True)
        if getattr(live, "complete", None) is None:
            print("No ANTHROPIC_API_KEY: the live comparison is skipped and reported as PENDING.")
            live = None
    seeds = list(range(args.first_seed, args.first_seed + args.seeds))
    out = ROOT / "data" / "eval" / time.strftime("%Y%m%d-%H%M%S")
    t0 = time.time()
    summary = E.run(seeds, args.scenarios.split(","), args.scrolls, args.reuse_seeds, live, out)
    m = summary["metrics"]
    rate = lambda w: "n/a" if w["rate"] is None else f"{w['k']}/{w['n']} = {w['rate']:.3f} [{w['lo']:.3f}, {w['hi']:.3f}]"  # noqa: E731
    print(f"\n{m['worlds']['total']} worlds, {m['claims']} claims in {time.time() - t0:.0f}s -> {out}")
    print("  familywise error, null worlds     ", rate(m["familywise_error_null_worlds"]))
    print("  false confirmation, null worlds   ", rate(m["false_confirmation_null_worlds"]))
    print("  false support among false claims  ", rate(m["false_support_rate"]))
    print("  false discovery proportion        ", rate(m["false_discovery_proportion"]))
    print("  sign errors                       ", m["sign_errors"])
    print("  power, true claims, valid design  ", rate(m["power_true_claims_valid_design"]))
    print("  true claims wrongly contradicted  ", rate(m["true_claims_wrongly_contradicted"]))
    print("  reference 95% CI coverage         ", rate(m["reference_ci_coverage"]))
    print("  vault reuse blocked               ", rate(m["vault_reuse_blocked"]))
    for k, v in m["power_by_estimand_valid_design"].items():
        print(f"    power {k:28}", rate(v))
    for k, v in m["reference_ci_coverage_by_scenario"].items():
        print(f"    coverage {k:25}", rate(v))
    print("  live vs scripted:", json.dumps(summary["live_vs_scripted"]))
    if args.out:
        dest = ROOT / args.out
        dest.mkdir(parents=True, exist_ok=True)
        shutil.copy(out / "evaluation_summary.json", dest / "evaluation_summary.json")
        print(f"  summary copied to {dest / 'evaluation_summary.json'}")


if __name__ == "__main__":
    main()

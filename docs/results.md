# Arena results: official run

Run: `.venv/bin/python scripts/run_arena.py --perm 500 --seed 0` (scripted agents, **no Emperor**), full log in
[results-run.txt](results-run.txt). Only one seed was run. Every number below is copied from that ledger.

Discovery set: CGMacros, 45 people, 1,134 clean meals. Holdout: BUT CGM, 58 people, 1,311 clean meals.
Outcome: `glucose_rise_mgdl` (Dexcom peak minus baseline, 2 h). "Gain" = drop in held-out absolute error, mg/dL per meal,
averaged per person, with folds split by participant. The Day I baseline is "guess the average"; later days use carbs as the baseline.

## Headline: nothing survived people it had never seen

| Claim | Arena (CGMacros) | Champion of Brno (BUT CGM) | Verdict |
| --- | --- | --- | --- |
| Carbs beat guessing the average | +0.84 (CI +0.30 to +1.28), Shuffler p = 0.002 | +0.46 (CI −0.29 to +1.15) | FALLEN |
| Protein adds to carbs | +0.28 (CI +0.05 to +0.50), Shuffler p = 0.002 | −1.23 (CI −1.54 to −0.97) | FALLEN |
| HbA1c adds to carbs | +1.53 (CI +0.35 to +2.79), Shuffler p = 0.002 | BUT CGM has no HbA1c | UNTESTABLE |

The holdout is a different population (healthy, active Czech adults vs CGMacros' mix of healthy, prediabetic and
type 2 participants), so "fails to transfer" is the honest reading, not "carbs don't matter".

## What died in the arena

| Claim | Killed by | Numbers | Verdict |
| --- | --- | --- | --- |
| Fibre adds to carbs | The Trial | +0.08 (CI −0.04 to +0.25) | NO_EDGE |
| Fat adds to carbs | The Trial | +0.10 (CI −0.06 to +0.27) | NO_EDGE |
| Calories add to carbs | The Trial | +0.00 (CI −0.19 to +0.16) | NO_EDGE |
| Heart rate after the meal | The Trial | −0.13 (CI −0.35 to +0.05) | NO_EDGE |
| Hour of day | The Trial | +0.28 (CI −0.28 to +0.81), correlates alone | REDUNDANT |
| Hours since last meal | The Trial | +1.10 (CI −0.23 to +2.45), correlates alone | REDUNDANT |
| Sugar, steps after | — | logged for only 1 CGMacros person | UNTESTABLE |

## Decoys: 4 of 4 caught

| Decoy | What happened |
| --- | --- |
| Lucky charm (pure noise) | Died at the Trial: −0.03 (CI −0.07 to +0.01) |
| Moon phase (best of 100 noise columns) | Passed the Trial (+0.11, CI +0.02 to +0.20) **and** the Shuffler (p = 0.004), then fell at the Champion of Brno: −0.06 (CI −0.14 to +0.03). The garden of forking paths in one gladiator. |
| Meal intensity score (built from the outcome) | +24.44 at the Trial (too good to be true), killed by the Inquisitor as LEAKY |
| Carb load index (copy of carbs) | Died at the Trial: +0.04 (CI −0.12 to +0.21), REDUNDANT |

## Caveats

- One sensor only: `meal_responses` has no per-sensor rows, so the Twins never fought.
- Gains are small in absolute terms because the per-meal rise is noisy (mean 55 mg/dL); the CIs, not the point estimates, carry the verdicts.
- The Lanista finished with reputation 20: it backed four gladiators that fell at the holdout.
- The Census counts every claim the Trial judged (13 by Day IV), not only the ones that reached the Shuffler.

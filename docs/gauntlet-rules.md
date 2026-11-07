# Hypothesis Gauntlet: the rules

The gauntlet is a game view of a real analysis. Hypothesis agents (one claim each about what
changes the glucose rise after a meal) walk four levels of evidence. Every enemy is one
deterministic statistical check; every HP change is one row of the table below applied to
that check's result. The numbers live in `backend/app/gauntlet/rules.py`; this page explains
them. Nothing here is decided by an LLM.

## Roles

| Role | Who | What it does |
|---|---|---|
| Hypothesis agents | One per claim (8 by default) plus 4 hidden impostors | Walk the levels, pay credits, take damage |
| Researcher | Claude (or the scripted fallback) | Proposes the claims (reusing the arena's Lanista), decides whether to pay to defend an optional challenge, may revise a claim the raw data contradicts |
| Skeptic | Claude (or the scripted fallback) | Picks up to 2 optional challenges per agent per level |
| Statistical Judge | `campaign.py` + `checks.py` + the arena's `engine.py` | Runs every test, applies these rules, writes the ledger |

Claude only ever chooses among options and talks. Its replies are validated against a schema;
anything unusable falls back to the script, and the screen says so.

## Resources

- **HP: 100.** HP is research integrity inside the game, not a probability that the claim is true.
- **Research credits: 18.** The mandatory checks cost 12, so every agent can afford some optional
  ones but not all. Running out before a mandatory test ends the quest as UNPROVEN.
- **A passed check restores 5 HP** (never above 100), so a hypothesis can lose support and recover.
- **Conceding a challenge costs 5 HP** and no credits: the claim stays unverified.

## The encounters

Mandatory ("gate") checks always run. Optional ("challenge") checks are the Skeptic's choice.

| Level | Enemy | Kind | Credits | Test | HP if failed |
|---|---|---|---|---|---|
| 1 Rumour Dungeon | Slime of Misinformation | gate | 0 | At least 10 people have the data | leaves as UNTESTABLE |
| 1 | Rumour Goblin | gate | 1 | Raw correlation with the rise, people-bootstrap 95% CI, vs the claimed direction | −5 if unclear, −15 if contradicted |
| 1 | Anecdote Bat | challenge | 1 | Share of people whose own meals show the claimed direction (> 50%) | −10 |
| 1 | Echo Chamber Wisp | challenge | 1 | \|r\| with carbs below 0.9 | −20 |
| 2 Forgotten Archives | Preprint Mimic | gate | 2 | The arena's Trial: participant-split cross-validated error with vs without the evidence; CI must be above 0 | −30 |
| 2 | Small Sample Skeleton | challenge | 1 | More than half of people predicted better | −10 |
| 2 | Confounding Phantom | challenge | 1 | Raw sign survives adjusting for carbs | −10 |
| 2 | Citation Spider | challenge | 1 | Gain below 25% of baseline error (not too good to be true) | −10 |
| 3 Temple of Replication | Replication Sentinel | gate | 2 | Gain positive in at least 3 of 5 independent participant groups | −15 |
| 3 | Contradiction Wraith | challenge | 2 | Same sign on both glucose sensors (only when two exist) | −15 |
| 3 | Data Chimera: Overfitting | gate | 3 | The arena's Shuffler: permutation test, p < 0.05 | −30 |
| 3 | Data Chimera: Selection Bias | challenge | 1 | Gain still positive without the top 10% of contributors | −10 |
| 3 | Publication Bias Knight | gate | 0 | Benjamini-Hochberg across every claim tried in the run | −15 |
| 4 Citadel of Truth | Chronolock Guardian | gate | 0 | Every feature known at mealtime | −40 (and LOOK-AHEAD) |
| 4 | The Leakage Reaper | gate | 0 | No feature built from the outcome | −100 |
| 4 | The Bureaucratic Titan | gate | 1 | Recorded for at least 10 people in the independent dataset | leaves as UNTESTABLE |
| 4 | Guardian of False Discoveries | gate | 3 | Preregister (hash the claim), train on the discovery set, beat the baseline on never-seen people (CI above 0) | −50 |

Why these weights: the size of a hit tracks how much the failure undermines a claim. Hints
(an unclear raw link, an anecdote, a confound) cost 5–15. Failing the core tests of "adds
something" (Mimic) and "isn't luck" (Chimera) costs 30. Using the future costs 40, failing on
new people 50, and evidence built from the answer is fatal (100). Agents keep walking while
they have HP, so weak claims die from accumulated evidence rather than one roll of the dice.

## Verdicts

- **VALIDATED**: passed the Mimic, the Chimera's overfitting test, the Knight, the Chronolock, the Reaper and the Guardian.
- **UNSUPPORTED**: still standing, but at least one of those failed.
- **LOOK-AHEAD**: relied on information from after the meal. Disqualified however accurate.
- **UNTESTABLE / UNPROVEN / FALLEN**: no data to judge / out of credits / HP reached 0.

If no claim is validated the finale says the evidence is inconclusive rather than crowning anyone.

## Who is the best researcher

The scoring rule is fixed before any run (`rules.SCORE_COMPONENTS`, computed in `gauntlet/report.py`
from checks that already ran; nothing new is measured for the score):

| Component | Max | How it is earned |
|---|---|---|
| Scientific validity | 20 | Share of the soundness checks passed (Trial, echo, within-person, majority, confounding); untested optional ones count half |
| Out-of-sample performance | 25 | 25 if it beats the baseline on never-seen people (CI above 0); 8 if the gain is positive but uncertain |
| Response to falsification tests | 20 | 10 for beating scrambled data, 5 for replicating in 3 of 5 groups, 5 for surviving selection-bias/sensor checks |
| Handling of uncertainty | 10 | 10 if still significant after correcting for every claim tried (Benjamini-Hochberg) |
| Detection of misleading evidence | 5 | Raw direction not contradicted (or honestly revised), and not too good to be true |
| Avoidance of data leakage | 15 | 7.5 for mealtime-only information, 7.5 for no feature built from the outcome |
| Research efficiency | 5 | 5 x share of checks that were neither redundant nor conceded |
| HP bonus | 5 | 0.05 per HP left |

- **Leakage voids the evidence.** If the Chronolock or the Reaper wins, validity, out-of-sample,
  falsification and uncertainty all score 0: a result built on leaked information is not evidence.
- **HP cannot override evidence.** The champion is the highest-scoring *VALIDATED* agent. Agents
  are ranked by (validated first, score, tie-break), so no amount of HP or extra tests lets an
  unvalidated claim win.
- **Tie-break (predefined):** the most confident gain on unseen people, i.e. the lower end of the
  holdout's 95% CI.
- **Inconclusive:** if nothing is validated there is no champion, and the report says so.
- Every agent starts with the same HP (100) and credits (18) and faces the same encounters.

Credits are a gameplay and efficiency measure. They are not a multiple-testing correction:
that is the Publication Bias Knight's job.

## The record of every fight

Each result or concession event carries an `encounter` record: `encounter_id`, `level`, `agent_id`,
`hypothesis_id`, `evidence_source`, `evidence_version` (a fingerprint of the data), `enemy_type`,
`research_action`, `test_requested`, `numerical_result`, `methodological_verdict`, `hp_change`,
`explanation`, `timestamp`. The final report cites these ids, and the game's ledger view and
"Inspect numbers" button show them in full.

## Demo Mode

`frontend/src/demo-quest.jsonl` is a recorded quest on synthetic meals with planted, known effects
(regenerate with `scripts/run_gauntlet.py --synthetic --perm 200 --theory "..." --out frontend/src/demo-quest.jsonl`).
The HUD shows a DEMO MODE badge and the report carries a disclaimer: these are not real findings.

## Impostors

Four hidden agents are planted decoys from the arena: pure noise, the luckiest of 100 noise
columns, a copy of carbs, and a score built from the outcome. They look like ordinary agents
until the finale. A gauntlet that validates any of them is broken.

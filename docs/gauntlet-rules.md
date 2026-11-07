# Hypothesis Gauntlet: Computational Epidemiology Edition, the rules

Four AI epidemiologists try to predict hospital surges from outside signals (wastewater, searches,
syndromic visits, sales, satellites). They walk four levels of evidence. Every enemy is one
deterministic measurement by the **Statistical Judge**; every HP change is one rule below applied to
that measurement. The numbers live in `backend/app/epi/rules.py` and `backend/app/epi/judge.py`.
Nothing here is decided by an LLM.

**Every campaign is simulated.** Public health data is not reachable from the build environment, so
each campaign is a deterministic synthetic surveillance world (`backend/app/epi/scenario.py`) with
planted, known effects. The Decision Brief reveals the planted truth so you can check the Judge.

## The four campaigns

| | Campaign | Planted truth |
|---|---|---|
| A | Wastewater Bio-Surveillance | Wastewater RNA leads admissions by 7 days. Search and social streams are mostly news panic and season; lab counts are backfilled over ~3 weeks; OTC sales lead by 2 days, not 21. |
| B | Digital Syndromic Mirage | ED syndromic visits lead RSV admissions by 6 days but jump with news coverage (de-noising removes it). Raw search and social streams follow news and the school calendar. |
| C | Pharmacoepidemiology EHR Audit | Antiviral X does nothing. Its apparent benefit is confounding by indication and immortal-time bias. |
| D | Environmental Heatwave & PM2.5 Surge | PM2.5 drives asthma admissions 2 days later, more weakly in rural districts. Regulatory AQI is accurate but published days late. |

Each world has 900 days in five regions (a home city, two more cities, two rural counties).
Days 40 to 599 train; days 600 onwards are the unseen holdout.

## The four archetypes

| Agent | Archetype | Plays |
|---|---|---|
| Vex | The Hype Nowcaster | Searches every digital stream at every lag 1 to 21 (K ≈ 150), no autoregressive terms, never pays for caution |
| Imara | The Bio-Surveillance Pioneer | One mechanistic stream with a lag declared in advance; buys Bias Detection, Preregister, Replication Shield, Temporal Guard |
| Quill | The Preprint Opportunist | A small-cohort claim with a long lead; spends almost nothing |
| Ward | The Surveillance Skeptic | No outside signal: AR(4) on admissions plus a seasonal harmonic. The benchmark everyone must beat |

Agents only choose which abilities to cast. Scripted plans by default; with `ANTHROPIC_API_KEY` in
`.env`, Claude plays each archetype in character and returns a JSON choice, validated against the menu
and the agent's credits (anything invalid falls back to the script).

## Resources and the clamp

- **100 HP** (research integrity, not a probability) and **100 research credits** per agent.
- Every hit is `ΔHP = −round(clamp(D_raw × M, 0, D_max))`, where `M` is the ability multiplier and
  `D_max` caps each level: **I 20, II 30, III 45, IV 60** (cumulative per level).
- Heals: Bias Detection +5, Eureka (beating the baseline in a way unlikely to be luck) +10. HP never exceeds 100.

## The levels

| Level | Enemies (scouts measure, the rest deal damage) | Damage rule |
|---|---|---|
| I Rumour Dungeon | Slime (n and r), Echo Chamber Wisp (panic windows, news > mean + 2 sd), **Rumour Goblin** (FAAR), **Anecdote Bat** (power) | `12 × max(0, FAAR − 1) + 18 × ρ_n`, where FAAR = error in panic windows / error elsewhere and ρ_n = max(0, 1 − n / n_min), n_min = (2.80 / atanh\|r\|)² + 3 |
| II Forgotten Archives | Preprint Mimic (r_XY), Citation Spider (r_XZ, r_YZ), **Confounding Phantom** (ω), **Small Sample Skeleton** (adjusted p) | `22 × ω + 10 × I(p_adj > 0.05)`, ω = max(0, 1 − r²_XY·Z / r²_XY); p_adj is a Newey-West (lag 14) Wald test with the confounder in the model |
| III Temple of Replication | **Publication Bias Knight** (`min(20, 5 ln K)`), **Replication Sentinel** (Šidák `p_corr = 1 − (1 − p_raw)^K`), Contradiction Wraith, **Data Chimera** (G_spatial) | `25 × I(p_raw < .05 and p_corr > .05) + min(20, 5 ln K) + min(25, 20 × max(0, G))`, G = worst relative growth of normalized RMSE in the four held-out regions |
| IV Citadel of Truth | Bureaucratic Titan (vintage audit), Leakage Reaper (look-ahead lags), **Chronolock Guardian**, **Guardian of False Discoveries** | Chronolock: `35 × I(used unreleased data) + min(25, round(40 × max(0, δ_vintage)))`. Guardian: SS_surge = 1 − RMSE_agent / RMSE_AR(4) on surge-onset days (admissions up ≥ 15% on the week), one-sided Diebold-Mariano with the Harvey correction. Gain (SS > 0.05, p < .05): 0 damage and Eureka. Loss (SS < −0.05): `min(50, 25 + 150 × \|SS\|)`. Otherwise 15 |

The Skeptic is the benchmark, so it does not fight the Guardian.

## Abilities

| Ability | Level | Credits | Effect |
|---|---|---|---|
| Fact Check | I | 10 | Purges media-spike weeks: M = 0.20 for Rule 1 |
| Media De-Noising Filter | I | 20 | Regresses news volume out of each stream for every later level |
| Exploratory Claim | I | 5 | Declares the claim exploratory: M = 0.50 for Rule 1 |
| Bias Detection | II | 15 | Puts the confounder in the model: ω = 0, +5 HP |
| Preregister | III | 25 | Locks one declared lag: K = 1 (only for a lag declared before looking) |
| Replication Shield | III | 25 | Ridge shrinkage, penalty tuned by time-blocked CV in the home region |
| Temporal Guard | IV | 20 | Trains on vintages with a reporting-delay correction: no leakage penalty |
| Ablation Strike | IV | 15 | Drops every stream that does not lower validation error |

Exploratory Claim and Ablation Strike are our additions so the Preprint Opportunist and the Skeptic
have a signature move. Loot: the Raw Artefact (unfiltered digital streams), the Incubation Priors
Blueprint (passing the Small Sample Skeleton with a lag window inside the biologically plausible
range caps K at that range in level III), and the
Preregistered Lockbox.

## Verdicts, score and the brief

- **VALIDATED**: SS_surge > 0 and Diebold-Mariano p < 0.05. (Stricter than "SS > 0" on purpose:
  a gain that could be luck does not count.)
- **NOT BETTER**: survived but did not beat the baseline. **BASELINE**: the Skeptic. **FALLEN**: 0 HP.
- Composite score = 0.35 × Norm(SS) + 0.25 × HP + 0.25 × % traps falsified + 0.15 × efficiency,
  with Norm = 100 × clamp(SS / 0.30, 0, 1) and efficiency = min(100, 100 × ablation lift % / max(10, credits spent)).
- The champion is the highest-scoring VALIDATED agent. If none, the verdict is **Baseline Holds:
  inconclusive**.
- The Operational Public Health Decision Brief cites every claim to its encounter id (`E###`).

## Telemetry

Every fight writes one ledger row (`data/quests/*.jsonl`) carrying an `EpiEncounterTelemetry` record:
`encounterId, campaignType, level, enemyName, epiTrapType, agentId, agentAction`,
`biostatMetrics {sampleSizeN, minRequiredN, unadjustedEffect, adjustedEffect, confounderName,
candidateLagsSearchedK, rawPValue, sidakCorrectedPValue, hindsightRmse, vintageRealTimeRmse,
arBaselineRmse, outOfSampleSurgeSkill}` and `combatResolution {rawDamage, abilityMultiplier,
clampedHpDelta, executedFormulaLatex, plainEnglishEpiVerdict}`.

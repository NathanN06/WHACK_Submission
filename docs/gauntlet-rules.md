# Hypothesis Gauntlet: Peptide & GLP-1 Discovery, the rules

One hero, **the Alchemist-Epidemiologist**, carries **hypothesis scrolls** about peptides and GLP-1 drugs
(2 to 6 formed by the Scribe on the title screen; the recorded demos and the command line use three hand-written
ones) through four levels of evidence. Every enemy is one deterministic measurement by the
**Statistical Judge**; every HP change is one rule below applied to that measurement. The numbers live
in `backend/app/pep/rules.py` and `backend/app/pep/judge.py`. Nothing here is decided by an LLM.

**Every campaign's patients are simulated.** EHR data is never public, so each campaign is a deterministic
synthetic world (`backend/app/pep/world.py`) with planted, known effects: an EHR cohort across five sites (three
urban, two rural), a social corpus, and for the hand-written scrolls a simulated literature base and trial
registry. Scrolls formed by the Scribe copy their papers and completed-RCT counts from the real
`data/pep_evidence.duckdb` (Europe PMC, ClinicalTrials.gov) when it exists. The brief reveals the planted truth so
you can check the Judge. Nothing is a real finding or medical advice.

## The four campaigns

| | Campaign | Drug vs active comparator | Planted truth |
|---|---|---|---|
| A | The Craving Cure | Semaglutide / tirzepatide vs DPP-4 inhibitors | Alcohol relapse hazard ratio 0.65 in every site; opioid 0.88; smoking 1.0. Users are healthier and more often in therapy; immortal time inflates naive estimates. |
| B | The Wolverine Mirage | BPC-157 / TB-500 vs physiotherapy-only rehab | No effect (1.0). Users are fitter, rehab more, take testosterone; the literature is rodent work from one lab; no human trial. |
| C | The Longevity Stack | GHK-Cu / ipamorelin + CJC-1295 vs matched clinic non-users | No effect (1.0) on frailty, epigenetic age or skin. Testosterone use and training explain every naive benefit. |
| D | The Ozempic Blindness Scare | GLP-1 agonists vs SGLT2 inhibitors | NAION hazard ratio 1.5 on a 0.4% yearly base rate (not seven-fold); sicker diabetics get GLP-1s. Too rare to confirm in this cohort. |

Index dates span 1,800 days, split by calendar time: days 0 to 1,099 train, days 1,100 to 1,449 are the
vaulted Level IV holdout, and later days are a second vault opened once, by the Trial of Truth.

**Point-in-time training.** Training is what was knowable on day 1,100. Every training row's follow-up is cut at
the cutoff (`min(365, 1100 − index day)` days of person-time, events after the cutoff not counted), and the risk
models (propensity and comparator) are fit only on patients whose whole year ended by the cutoff. The Chronolock
Assassin checks both: no training row starts or ends after day 1,100.

## The hero, the scrolls and the Gatekeeper

| Scroll | Archetype | How it was found, and what the hero buys for it |
|---|---|---|
| Hype Scroll | HYPE | Social media. Searches every outcome and subgroup (K = 21), counts anyone who ever filled a prescription as treated from day 0, never pays for caution and may not Preregister |
| Mechanistic Scroll | PIONEER | A clinically framed, mechanistic claim. Buys Bias Detection, Preregister, Replication Shield, Temporal Guard (and Species Guard where the literature is mostly animal work) |
| Preprint Scroll | PREPRINT | A small clinic log or animal preprint. Calls itself exploratory and spends almost nothing |

The **Gatekeeper Skeptic, Warden of the Null**, is not a scroll. It speaks at every gate and sets the
benchmark in the Citadel: the matched active comparator with **no drug effect**.

The hero only chooses abilities for each scroll. Scripted plans by default; with `ANTHROPIC_API_KEY` in
`.env`, Claude plays the Alchemist and returns a JSON choice per scroll, validated against the menu and
that scroll's credits (anything invalid falls back to the script).

**The Scribe** (`hypotheses.py`) forms 2 to 6 scrolls when a quest asks for `scrolls: N`. It writes words only
(title, claim, origin, outcome, topic, archetype), never a number. With an API key, Claude writes them, shown a fresh
sample of the real papers, a few random angles and the titles it wrote lately, so quests do not repeat. No two scrolls share a structure (outcome and
archetype); Claude's duplicates and claims containing numbers are rejected and the script fills the slots, in the
order Mechanistic, Pilot (preprint), Viral (hype), each across the outcomes. Titles name the outcome: "The Pilot
Re-Injury Scroll".

## Resources and the clamp

- Each scroll has its own **100 HP** (research integrity) and **100 credits**. A scroll at 0 HP **shatters**.
- Every rule is applied once: `ΔHP = −round(clamp(D_raw × M, 0, D_max))`, cumulative within a level,
  with `D_max` **I 20, II 30, III 45, IV 60**. Level IV has two separate rules (Chronolock and Guardian).
- Heals: Bias Detection +5, Eureka (beating the benchmark in a way unlikely to be luck) +10. HP never exceeds 100.

## The levels

| Level | Enemies (scouts measure, the rest deal damage) | Damage rule |
|---|---|---|
| I Rumour Dungeon | Slime (posts per platform), Echo-Chamber Wisp (reposts), **Affiliate Siren**, **Anecdote Bat** | `15 × φ_affiliate + 15 × max(0, 1 − N_eff / 30)`; φ = sponsored posts / supporting posts, N_eff = independent stories |
| II Forgotten Archives | Preprint Mimic (naive rate ratio), Citation Spider (confounder balance), **Rodent-Model Chimera**, **Healthy-User Phantom** | `22 × τ_rodent + 20 × min(1, \|β_naive − β_adj\| / \|β_naive\|)`; Poisson rate ratios with a person-time offset, adjusted for age, sex, severity, healthy-user score, testosterone, therapy and site |
| III Temple of Replication | **Publication Bias Knight** (Šidák `1 − (1 − p_raw)^K`), **Citation Island Sentinel** (H_lab), Contradiction Wraith (per-site effects), **The Data Chimera** | `20 × I(p_corr > .05) + 20 × H_lab + 25 × I(N_RCT = 0)`; H_lab = sum of squared lab shares |
| IV Citadel of Truth | Bureaucratic Titan (immortal-time audit), **Chronolock Guardian**, **Guardian of False Discoveries** | Chronolock: `35 × L_time + 25 × Δ_purge`. Guardian: SS_oos = 1 − Loss_scroll / Loss_benchmark (Brier) on 1:1 propensity-matched new users in the vault, paired one-sided loss test. Gain (SS > 0.002, p < .05) on a new-user, time-zero design: 0 and Eureka; the same gain with immortal time still in the design is not trusted (15). Loss (SS < −0.002): `min(50, 25 + 25 × \|SS\| / 0.02)`. Otherwise 15 |

## Abilities

| Ability | Level | Credits | Effect |
|---|---|---|---|
| De-Noise Filter | I | 15 | Strips affiliate-coded posts and collapses reposts before Rule 1 |
| Exploratory Claim | I | 5 | M = 0.50 for Rule 1 |
| Species Guard | II | 15 | M = 0.20 on the species term, if any human study supports the claim |
| Bias Detection | II | 15 | Adjusts for measured confounders: confounding term 0, +5 HP, adjusted estimate carried forward |
| Preregister | III | 25 | One outcome, one population: K = 1 |
| Replication Shield | III | 25 | Re-runs the analysis in every EHR site; replicating sites count as independent labs |
| Temporal Guard | IV | 20 | New-user, time-zero design: time before the first fill stays unexposed |
| Ablation Strike | IV | 15 | Drops the drug term if it does not lower loss on the last quarter of the training years |

## Verdicts, score and the brief

- **VALIDATED**: SS_oos > 0.002 and paired p < 0.05, on a new-user, time-zero design. **NOT BETTER**: survived without that.
  **SHATTERED**: 0 HP. **BASELINE**: the Gatekeeper's benchmark.
- Composite score = 0.35 × Norm(SS) + 0.25 × HP + 0.25 × % traps falsified + 0.15 × efficiency,
  Norm = 100 × clamp(SS / 0.02, 0, 1), efficiency = min(100, 100 × lift % / max(1, credits spent / 10)).
- **One champion per outcome track.** Scrolls about different outcomes answer different questions, so they are
  never ranked against each other. Each outcome's champion is its highest-scoring VALIDATED scroll; the brief's
  champion is the primary outcome's, else the first outcome (in campaign order) that has one. If none:
  **Baseline Holds**.
- The Research Decision Brief cites every claim to its encounter id (`E###`). A validated benefit
  becomes "prioritise a confirmatory randomised trial"; a validated harm becomes a safety signal. The decision
  also states each question's scientific status, so "the baseline holds for prediction" is never read as "the drug
  does nothing".

## Scientific status: prediction and causation are judged separately

The verdict asks whether a scroll **predicts** unseen patients better than the comparator. The Guardian also asks
whether the drug **changes the risk** at all, on the same 1:1 matched holdout patients: the matched risk ratio,
standardised to the comparator model's expected risks (`RR = (O_t/E_t) / (O_c/E_c)`, which removes the imbalance
left inside the caliper). The 95% interval is exact conditional (Clopper-Pearson on the treated share of events)
when the comparator risk is below 5% or an arm has fewer than 5 events, and a Wald log-RR interval otherwise. The
smallest effect of interest (`rules.SESOI`) is RR 0.80 for a claimed benefit and 1.25 for a claimed harm.

| Status | When |
|---|---|
| SUPPORTED | The interval excludes 1 in the claimed direction (flagged if it also excludes the effect of interest) |
| REFUTED | The interval excludes the smallest effect of interest |
| INCONCLUSIVE | The interval includes both no effect and an effect that would matter |
| NOT ASSESSED | No matched users and comparators with events |

Every status also reports the detectable effect: the smallest risk ratio these patients would find with 80% power.

## Telemetry

Every fight writes one ledger row (`data/quests/*.jsonl`) carrying a `PepEncounterTelemetry` record:
`encounterId, campaignType, level, enemyName, trapType, scrollId, scrollTitle, heroAction`,
`biostatMetrics {affiliateSkew, effectiveSources, rodentShare, naiveRateRatio, adjustedRateRatio,
confoundingShift, testsSearchedK, rawPValue, sidakCorrectedPValue, labConcentration, completedHumanRcts,
immortalTimeShare, purgeShift, outOfSampleSkill, pairedLossPValue, design}` and
`combatResolution {rawDamage, abilityMultiplier, clampedHpDelta, executedFormulaLatex, plainEnglishVerdict}`,
and the Archivist's trace: `methodId`, `sourceIds` and `rulesetVersion` (`rules.RULESET_VERSION`, bumped on any
rule change).

## The Archivist's Ledger: every number traces to a method and its sources

`backend/app/pep/sources.py` registers, at the start of every quest, each source a number can come from:

| Type | What it is |
|---|---|
| SIMULATED | The cohort's partitions (`S-TRAIN`, `S-HOLDOUT`, `S-VAULT2`), the social corpus, simulated literature |
| REAL_METADATA | Papers and completed-RCT counts copied from `data/pep_evidence.duckdb` (`S-LIT-<scroll>`, `S-RCT-<scroll>`) |
| USER_UPLOADED | A file the Director attached, with its SHA-256 |
| DIRECTOR_STATEMENT | A link or a claim the Director typed: kept, never treated as fact |
| DERIVED | Computed by the Judge from other sources |
| PRIOR_ROUND | A champion's frozen claim from an earlier Challenger round |

Each source may be read by a test (NUMERIC_TEST), shown as context only (CONTEXT), or EXCLUDED. Every encounter
names its method (`sources.METHODS`, such as `M-L4-GUARDIAN`) and the sources it read. The first ledger row
publishes a SHA-256 of each cohort partition before anything is measured. The finale writes a manifest (run id,
seed, ruleset, generator, fingerprints, sources, methods, the trace of every encounter, the trial) with its own
SHA-256, and checks it is complete: every encounter names a known method and only registered sources, and every
citation in the brief points at a traced encounter. The brief's **Archivist's Ledger** tab shows it and downloads
the manifest as JSON.

## The Research Director's console (CHALLENGE THE HERO)

In a live campaign (server running, **Begin**) the user is the Research Director. The quest pauses after each
level until the screen has shown it, so the Director can stop the expedition at any point with **Challenge the
Hero** (or the `C` key). Code: `backend/app/pep/director.py`, `evidence.py`, `challenges.py`; screen:
`frontend/src/pep-director.js`.

| Mode | What happens |
|---|---|
| Boss chips | Seven chips, one per Mystery Boss below: one click names the registered test and summons it on the selected scroll. |
| Ask | The hero explains its choices and the Judge's numbers from the ledger. Never creates an enemy. |
| Challenge / Summon | The QuestionRouter maps the text to one registered challenge. If it maps, a Mystery Encounter is offered (summon now, save for later, explain, cancel). If not, it is kept as an unresolved challenge. |
| Add evidence | Intake, verification, classification (below). A relevant, testable weakness becomes a Mystery Encounter; a valid CSV opens a Secret Research Level. |
| New hypothesis | A named confounder becomes a Confounder Shapeshifter; another campaign outcome must first survive the Probability Phantom; anything else is an unresolved quest. |

**Evidence verification.** Each submission is recorded (claim, link or file, time, research question, target
scroll, level, source type) and registered with the Archivist, then checked: can it be retrieved (http/https only,
no user name or password in the link, the host resolved once and every address public, the connection pinned to the
address that was checked, no redirects, text, HTML, CSV, Markdown or JSON only, 1 MB, 3 s for the whole fetch), who published it and when (HTML meta tags, read by regular expression, never rendered or run), does the
page contain the claim, is it relevant to the campaign. Classes: VERIFIED AND TESTABLE, VERIFIED BUT NOT DIRECTLY
TESTABLE, UNVERIFIED, IRRELEVANT, INVALID OR INCOMPATIBLE DATA, REQUIRES ADDITIONAL EVIDENCE. Social media ranks below
preprints, below journals, registries and agencies. A verified source does not make its claim true, and an
unverified one is kept with that label: the hero never adopts a reported result, it only tests the weakness the
claim points at, on its own data. PDFs are not opened. CSVs need 0/1 `treated` and `event` columns. **Network note:**
the build container blocks most outbound hosts, so links normally end UNVERIFIED there.

**Mystery Bosses** (one registered test each, training cohort only; the vaults raise an error if touched):

| Boss | Question | Test | Survives if |
|---|---|---|---|
| Seasonal Wraith | Does it vanish after season? | Rate ratio adjusted for index-date quarter, per quarter | adjusted p < .05 in the claimed direction and season moves it < 50% |
| Chronolock Assassin | Future information? | Immortal-time audit, purged estimate, split order | exposure starts at the first fill and training precedes the holdout |
| Regional Hydra | Does it generalise? | Per-site rate ratios, Cochran's Q, rural sites pooled | Q p >= .05 and the rural pool holds (p < .05) |
| Probability Phantom | Could it be chance? | 199 label shuffles in the new-user cohort, Sidak over the scroll's K | p_corr < .05 |
| Replication Revenant | Independent evaluation? | Re-estimate on the last quarter of the training years alone | that slice holds (p < .05) |
| Redundancy Golem | Added value beyond the baseline? | Ablation on a validation slice | SS > 0 |
| Confounder Shapeshifter | Another variable? | Adjust for the named (or every) confounder | adjusted p < .05; an unmeasured variable ends Unresolved |

HP (research integrity, `rules.MYSTERY_HP`): survived +3, fallen −10, fallen through leakage −15, unresolved 0.
**No farming:** a test is identified by its target, boss, outcome, options and the scroll's design as it stands.
Summoning the identical test again is a REPEAT: it is not run, and changes 0 HP. A boss family that already
rewarded a scroll earns it nothing more (survived again, 0). The ledger counts how many tests looked at each
scroll's training data.
A Secret Research Level (from a CSV) has two measuring obstacles (Schema Golem, Fisher's exact test) and the
Replication Revenant: a heterogeneity z-test between the new data's risk ratio and the hero's training estimate.

## The Bridge of Judgment, Evolution and the Trial of Truth

After Level IV the hero reviews every scroll, failed test, weakness, leak, unresolved encounter, remaining credit and
the size of the sealed vault (`backend/app/pep/bridge.py`). Weaknesses carry a severity (`rules.WEAKNESSES`);
challenges the Director raised weigh one more. The policy: **Evolve** if a focused expedition the credits can pay for
(5 base + ability costs + 10 per re-test) fixes weaknesses weighing at least 3; else **Cross** if the claim beat the
comparator on a time-zero design and no severe or Director-exposed weakness remains; else **Inconclusive**. The
Director chooses; disabled options say why.

**Evolution** (once): V1 is saved in full, V2 pays its credits, applies the fixes (+3 HP each), re-measures each
level, re-fights the Director's open challenges, and re-checks the holdout as exploratory only. Then the hero
returns to the bridge.

**Trial of Truth**: the claim is locked (sha256 of the specification), then the second vault (index day >= 1450),
never read before, scores it against the comparator exactly as the Guardian does. Outcomes (`rules.TRIAL_HP`):
VALIDATED DISCOVERY (asserted and gained, +10), JUSTIFIED UNCERTAINTY (qualified findings, 0, whatever the vault
says), UNJUSTIFIED CONFIDENCE (asserted, no gain, −60), INVALID METHODOLOGY (asserted with immortal time, claim
rejected, HP to 0). Honest uncertainty is never punished; HP never decides validity. Without a Director (CLI, the
recorded demos) the hero follows its own recommendation.

## Challenger Mode: a title defended on fresh patients

Each campaign's primary question is a title track (`A:alcohol`), kept in `data/champions.json` (`champions.py`).
One Challenger round is one quest on a fresh simulated cohort (the round number is the seed). The reigning
champion is carried in with its words frozen and hashed; the Scribe forms challengers that differ from it in
outcome or archetype. To win, a scroll must be on the track's question, standing, time-zero, VALIDATED, with
scientific status SUPPORTED or INCONCLUSIVE, and not rejected at the Trial of Truth. A challenger takes the title
only by beating the incumbent (SUPPORTED beats INCONCLUSIVE, else holdout skill by more than 0.002); a tie keeps
it. Results: NEW CHAMPION, CHAMPION DEFENDED, TIE - INCUMBENT RETAINED, NO ELIGIBLE CHAMPION, NOT APPLIED (another
round settled the track meanwhile). The registry is written atomically, once per run, and only if its revision is
unchanged. `GET /api/champions` lists every track.

## Lifecycle

At most four live expeditions run at once; a fifth is refused (HTTP 429) until one ends. An expedition nobody polls
or acts on for 120 seconds stops itself and writes a `timeout` row. Replays cost nothing and are not counted.

## Simulated or not built

Everything is still a simulated world. External links are fetched for real but are mostly blocked in the build
container. The hero's chat replies are deterministic templates over the ledger (no language model writes them).
Cursed Affixes are not built.

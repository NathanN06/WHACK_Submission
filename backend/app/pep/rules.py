"""Every rule of the Peptide & GLP-1 edition, fixed before any run. The Judge reads these; nothing else.

Damage follows the universal clamping equation, applied once per rule:
    dHP = -round( clamp( D_raw x M_ability, 0, Dmax(level) ) )
Within a level each enemy deals one term of that level's formula; the running total is clamped, so the
HP a scroll loses across the level equals the formula exactly. Level 4 has two separate rules: the
Chronolock (immortal time) and the Guardian (out-of-sample skill against the active comparator).
"""

STARTING_HP = 100
STARTING_CREDITS = 100
D_MAX = {1: 20, 2: 30, 3: 45, 4: 60}

ALPHA = 0.05
N_EFF_FULL = 30             # 30 independent anecdotes earn full credit in Rule 1
SS_MARGIN = 0.002           # |SS| within 0.2% of the comparator's holdout loss counts as "no better"
SS_REF = 0.02               # Norm(SS) = 100 x clamp(SS / 0.02, 0, 1): a 2% cut in per-patient Brier loss earns full marks
CALIPER = 0.05              # propensity-score matching caliper (on the probability scale)
FOLLOW_UP = 365             # days of follow-up after the index date
BIAS_HEAL = 5
EUREKA_HEAL = 10
VALIDATION_SLICE = 0.25     # Ablation Strike decides on the last quarter of the training period

TRAPS = {1: "AFFILIATE_ECHO_HYPE", 2: "SPECIES_GAP_CONFOUNDING", 3: "RCT_VOID_P_HACKING", 4: "IMMORTAL_TIME_HOLDOUT"}

LEVELS = {
    1: {"name": "The Rumour Dungeon", "evidence": "YouTube transcripts, Quora answers, Reddit (r/Peptides, r/Ozempic)",
        "trap": "Affiliate skew and echo chambers: sponsored codes and reposts make a handful of stories look like a movement.",
        "rule": "D_L1 = 15 x phi_affiliate + 15 x max(0, 1 - N_eff / 30)"},
    2: {"name": "The Forgotten Archives", "evidence": "PubMed / Europe PMC preprints, animal studies, open-label clinic logs",
        "trap": "Species gap and confounding: rat tendons are not human tendons, and peptide users are not average patients.",
        "rule": "D_L2 = 22 x tau_rodent + 20 x min(1, |beta_naive - beta_adj| / |beta_naive|)"},
    3: {"name": "The Temple of Replication", "evidence": "ClinicalTrials.gov registry and multi-site EHR subgroup replication",
        "trap": "The RCT void and p-hacking: no completed human trial, one lab citing itself, and the best of many subgroups.",
        "rule": "D_L3 = 20 x I(p_corr > 0.05) + 20 x H_lab + 25 x I(N_RCT = 0)"},
    4: {"name": "The Citadel of Truth", "evidence": "OpenFDA FAERS and a vaulted, point-in-time active-comparator EHR holdout",
        "trap": "Immortal time and the holdout: counting the wait before the first prescription as treated time flatters any drug.",
        "rule": "D_chrono = 35 x L_time + 25 x Delta_purge; SS_oos = 1 - Loss_peptide / Loss_comparator"},
}

# Abilities: what a scroll can buy with its own 100 credits.
ABILITIES = {
    "DENOISE": {"name": "De-Noise Filter", "cost": 15, "level": 1,
                "effect": "Strips affiliate-coded posts and collapses reposts before Rule 1 is measured.",
                "tradeoff": "Counts fewer posts: if most stories were sponsored, the independent-story count can fall."},
    "EXPLORATORY_CLAIM": {"name": "Exploratory Claim", "cost": 5, "level": 1,
                          "effect": "Declares the claim exploratory: cheap, weak cover, M = 0.50 for Rule 1.",
                          "tradeoff": "Changes no estimate: it only weakens what the scroll asserts about the rumours."},
    "SPECIES_GUARD": {"name": "Species Guard", "cost": 15, "level": 2,
                      "effect": "Counts human evidence only: M = 0.20 on the species term, if any human study supports the claim.",
                      "tradeoff": "Worthless when no human study exists; the cohort estimate is unchanged."},
    "BIAS_DETECTION": {"name": "Bias Detection", "cost": 15, "level": 2,
                       "effect": "Adjusts for the measured confounders before the Phantom strikes: confounding term 0, +5 HP, and the adjusted estimate is carried forward.",
                       "tradeoff": "Removes measured confounding only (never unmeasured); the interval can widen or narrow, "
                                   "and the Judge logs by how much."},
    "PREREGISTER": {"name": "Preregister", "cost": 25, "level": 3,
                    "effect": "Locks one outcome and population before testing: K = 1, so p_corr = p_raw.",
                    "tradeoff": "Only before Level III's analysis: tests the declared outcome and subgroup alone, so no "
                                "search penalty but no chance to find another effect. Worthless if K is already 1."},
    "REPLICATION_SHIELD": {"name": "Replication Shield", "cost": 25, "level": 3,
                           "effect": "Re-runs the adjusted analysis in every EHR site; sites that replicate count as independent labs in H_lab.",
                           "tradeoff": "Per-site estimates are noisy: a real but small effect may replicate in few sites."},
    "TEMPORAL_GUARD": {"name": "Temporal Guard", "cost": 20, "level": 4,
                       "effect": "New-user, time-zero design: person-time before the first prescription stays unexposed.",
                       "tradeoff": "Removes immortal time; exposed person-time shrinks to after the first fill. "
                                   "Without it no gain is trusted."},
    "ABLATION_STRIKE": {"name": "Ablation Strike", "cost": 15, "level": 4,
                        "effect": "Drops the drug term if it does not lower loss on a validation slice of the training years.",
                        "tradeoff": "Guards against overfitting, but a small real effect can be dropped, and a dropped "
                                    "term can never win."},
}
M_ABILITY = {"EXPLORATORY_CLAIM": ("L1", 0.50)}
SPECIES_GUARD_M = 0.20

ENEMIES = {
    1: [
        {"key": "slime", "name": "Slime of Misinformation", "term": None, "test": "Corpus scrape: posts per platform supporting the claim",
         "attack": "Ten thousand views can't be wrong. Can they?"},
        {"key": "wisp", "name": "Echo-Chamber Wisp", "term": None, "test": "Repost graph: independent stories vs copies",
         "attack": "Everyone is saying it. Doesn't that make it true?"},
        {"key": "siren", "name": "Affiliate Siren", "term": "affiliate", "test": "Affiliate skew phi = sponsored posts / supporting posts",
         "attack": "Use my code for 15% off. It changed my life."},
        {"key": "bat", "name": "Anecdote Bat", "term": "neff", "test": "Effective sources: max(0, 1 - N_eff / 30)",
         "attack": "It worked for me and my gym buddy. Good enough?"},
    ],
    2: [
        {"key": "mimic", "name": "Preprint Mimic", "term": None, "test": "Naive effect in the training cohort (log rate ratio)",
         "attack": "The preprint says it works. Peer review is a formality."},
        {"key": "spider", "name": "Citation Spider", "term": None, "test": "Who uses it: confounder balance between users and comparators",
         "attack": "Every paper cites the same rats. Are you sure it's your drug?"},
        {"key": "rat", "name": "Rodent-Model Chimera", "term": "rodent", "test": "Species gap tau = non-human supporting studies / supporting studies",
         "attack": "It healed a rat's Achilles in a week. Humans are just big rats."},
        {"key": "phantom", "name": "Healthy-User Phantom", "term": "confound", "test": "Confounding shift |beta_naive - beta_adj| / |beta_naive|",
         "attack": "People who buy peptides also train, diet and take testosterone. Was it the peptide?"},
    ],
    3: [
        {"key": "knight", "name": "Publication Bias Knight", "term": "sidak", "test": "Sidak p_corr = 1 - (1 - p_raw)^K over subgroups and outcomes searched",
         "attack": "Somewhere in all those subgroups, one is significant."},
        {"key": "sentinel", "name": "Citation Island Sentinel", "term": "hlab", "test": "Lab concentration H_lab = sum of squared lab shares",
         "attack": "One lab, forty papers, all citing each other. Is that replication?"},
        {"key": "wraith", "name": "Contradiction Wraith", "term": None, "test": "Effect in each EHR site",
         "attack": "The other hospitals tell a different story."},
        {"key": "chimera", "name": "The Data Chimera", "term": "rct", "test": "Completed human RCTs in the registry: 25 x I(N_RCT = 0)", "boss": True,
         "attack": "Show me one completed human trial. Just one."},
    ],
    4: [
        {"key": "titan", "name": "The Bureaucratic Titan", "term": None, "test": "Exposure-definition audit: unexposed waiting time counted as treated",
         "attack": "When did they actually fill the first prescription?"},
        {"key": "chronolock", "name": "Chronolock Guardian", "term": "chrono", "test": "Immortal-time purge: 35 x L_time + 25 x Delta_purge", "boss": True,
         "attack": "Count the time before the first dose as untreated, then tell me your effect."},
        {"key": "guardian", "name": "Guardian of False Discoveries", "term": "final", "test": "Out-of-sample skill vs the matched active comparator, paired loss test", "boss": True,
         "attack": "Predict patients you have never seen better than the comparator does."},
    ],
}
RULE_OF = {"affiliate": "L1", "neff": "L1", "rodent": "L2", "confound": "L2", "sidak": "L3", "hlab": "L3",
           "rct": "L3", "chrono": "L4A", "final": "L4B"}
RULE_LEVEL = {"L1": 1, "L2": 2, "L3": 3, "L4A": 4, "L4B": 4}

TRAP_LABELS = {"affiliate": "Affiliate skew", "neff": "Too few independent stories", "rodent": "Species gap",
               "confound": "Confounding", "sidak": "Significance from search", "hlab": "Citation island",
               "rct": "No completed human RCT", "chrono": "Immortal time", "final": "No out-of-sample skill"}

SCORE_WEIGHTS = {"skill": 0.35, "hp": 0.25, "traps": 0.25, "efficiency": 0.15}
SCORE_RULES = {
    "skill": "0.35 x Norm(SS_oos), Norm = 100 x clamp(SS / 0.02, 0, 1)",
    "hp": "0.25 x HP_final",
    "traps": "0.25 x 100 x traps falsified / traps faced",
    "efficiency": "0.15 x min(100, 100 x holdout lift % / max(1, credits spent / 10))",
}

VERDICTS = {
    "VALIDATED": "Predicted unseen, matched patients better than the active comparator, and the gain is unlikely to be luck (paired loss test p < 0.05).",
    "NOT BETTER": "Survived, but did not predict unseen patients better than the active comparator.",
    "BASELINE": "The Gatekeeper's benchmark: the matched active comparator with no drug effect.",
    "SHATTERED": "The scroll's research integrity reached 0 HP.",
    "WITHDRAWN": "The hero stopped testing the scroll after its exploratory results, before the Guardian.",
}


# ---------- The Research Director's console: Mystery Bosses, the Bridge of Judgment, the Trial of Truth ----------
# HP is research integrity, not the probability that a claim is true. These rules reward honest, meaningful
# extra tests and punish asserting a claim the evidence does not support. Fixed before any run.

MYSTERY_D_MAX = 15          # a Mystery Boss never takes more than this from a scroll
MYSTERY_HP = {
    "SURVIVED": +3,         # ran a meaningful additional test and the claim held: a modest reward
    "FALLEN": -10,          # the test exposed a real weakness the scroll had not guarded against
    "FALLEN_LEAKAGE": -15,  # the weakness was future information (the gravest methodological flaw)
    "UNRESOLVED": 0,        # no valid test could be run: nothing is decided, nothing is lost
}
MYSTERY_TEST_COST = 10      # credits a focused re-test costs during the Evolution Trial
PERMUTATIONS = 199          # label shuffles for the Probability Phantom
SECRET_MIN_ROWS = 40        # a user dataset smaller than this cannot open a Secret Research Level
UPLOAD_MAX_BYTES = 1_000_000
UPLOAD_MAX_ROWS = 20_000

# Each weakness the hero can find in the claim it would submit: how serious it is, and what fixes it.
WEAKNESSES = {
    "leakage": {"label": "Possible leakage: immortal time (future information) in the exposure definition",
                "severity": 3, "fix": "TEMPORAL_GUARD"},
    "confounding": {"label": "Measured confounders not adjusted for", "severity": 2, "fix": "BIAS_DETECTION"},
    "search": {"label": "Significance may come from searching many outcomes and subgroups", "severity": 2,
               "fix": "PREREGISTER"},
    "generalisation": {"label": "The effect has not replicated in most sites", "severity": 1, "fix": "REPLICATION_SHIELD"},
    "no_rct": {"label": "No completed human randomised trial", "severity": 1, "fix": None},
    "holdout": {"label": "Did not beat the comparator on the vaulted holdout", "severity": 2, "fix": None},
}
USER_RAISED_BONUS = 1       # an unresolved challenge the Research Director raised weighs one point more
EVOLVE_THRESHOLD = 3        # evolve only if the fixable weaknesses the credits can pay for weigh at least this
EVOLUTION_BASE_COST = 5     # the focused second expedition itself
EVOLUTION_FIX_HEAL = 3      # each weakness V2 genuinely fixes: a modest reward

# ---------- The scientific verdict (science.py): separate from HP, credits and the game result ----------
# A scroll can win the game and still be scientifically unproven, and the reverse. These rules decide the
# scientific status of every claim from measurements already in the ledger. Fixed before any run.

ANALYSIS_VERSION = "pep-judge-2.2"   # bumped whenever an estimator or a status rule changes
MIE_RR = 0.90                        # minimal important effect: a 10% relative change in the one-year event rate
HETEROGENEITY_ALPHA = 0.10           # sites disagree (Cochran's Q p below this): the reference pools with random effects
STATUS_ORDER = ["SUPPORTED_ON_SYNTHETIC_VALIDATION", "PROVISIONALLY_SUPPORTED", "INCONCLUSIVE", "CONTRADICTED",
                "INVALID_ANALYSIS"]
STATUSES = {
    "SUPPORTED_ON_SYNTHETIC_VALIDATION": "Beat the comparator on the holdout and again on an independent, never-opened "
                                         "sealed vault, on a valid design, in the claimed direction. Synthetic data only.",
    "PROVISIONALLY_SUPPORTED": "Beat the comparator on the holdout in the claimed direction on a valid design, after Holm "
                               "correction across every scroll of the quest. Not yet independently confirmed.",
    "INCONCLUSIVE": "Neither supported nor contradicted: the evidence is too weak or too imprecise either way. "
                    "Not significant is not evidence of no effect.",
    "CONTRADICTED": "The Judge's reference analysis rules out the claim: an effect the opposite way, or a confidence "
                    "interval that excludes any important effect (a 10% change) in the claimed direction.",
    "INVALID_ANALYSIS": "The scroll's own analysis had a predefined validity failure (immortal time), so whatever it "
                        "measured cannot support the claim.",
}
MULTIPLICITY_FAMILIES = {
    "within_scroll_search": "Sidak over the K outcome-and-subgroup combinations a scroll's search opens (Level III). "
                            "Valid for these positively correlated subgroup tests.",
    "across_scrolls": "Holm over every scroll recruited this quest, fixed at recruitment: a scroll that shatters, is "
                      "withdrawn or carries an invalid design stays in the family with p = 1.",
    "sealed_vault": "One locked claim per quest, tested once on a never-opened vault: no family, alpha = 0.05.",
    "challenges": "Mystery Bosses and Skeptic challenges are exploratory robustness checks on the training years; they "
                  "never raise a scientific status.",
}

# ---------- The hero's pre-decision telemetry (telemetry.py): design facts only, never an outcome ----------
SMD_IMBALANCE = 0.10        # |standardized mean difference| above this on any confounder: imbalanced
SITE_DOMINANCE = 0.50       # one site holding more than half of the new users: single-site dominance
SIZE_TIERS = (300, 2000)    # new users in the training years: below 300 SMALL_N, below 2000 MEDIUM_N, else LARGE_N
SPONSORED_HEAVY = 0.25      # share of supporting posts carrying an affiliate code or sponsorship
CONCERNS = ["CONFOUNDING", "IMMORTAL_TIME", "MULTIPLICITY", "SPECIES_GAP", "SOCIAL_HYPE", "SITE_CLUSTERING",
            "CITATION_ISLAND", "SMALL_SAMPLE", "NONE"]
NEXT_ACTIONS = ["TEST", "REPLICATE", "REVISE", "STOP"]

# ---------- The sealed vault's budget (registry.py) ----------
VAULT_CONFIRMATIONS = 1     # each synthetic cohort's sealed vault confirms at most one claim, once

TRIAL_HP = {
    "VALIDATED DISCOVERY": +10,
    "JUSTIFIED UNCERTAINTY": 0,
    "NO NEW INDEPENDENT CONFIRMATION": 0,
    "UNJUSTIFIED CONFIDENCE": -60,
    "INVALID METHODOLOGY": -100,
}
TRIAL_OUTCOMES = {
    "VALIDATED DISCOVERY": "The locked claim beat the comparator on the protected vault, on a valid design, in the claimed direction. The hero crosses.",
    "JUSTIFIED UNCERTAINTY": "The hero presented qualified findings and did not assert more than the evidence allows. The hero crosses with a qualified report.",
    "NO NEW INDEPENDENT CONFIRMATION": "The claim held, but on a sealed vault that had already been opened for this cohort: a reused vault can "
                                       "refute a claim, never confirm it again. The hero crosses; the confirmation count does not change.",
    "UNJUSTIFIED CONFIDENCE": "The hero asserted a claim the protected vault does not support. The bridge cracks beneath it.",
    "INVALID METHODOLOGY": "The final audit found a predefined validity failure in the asserted claim. The bridge collapses and the claim is rejected.",
}

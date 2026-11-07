"""Every rule of the Epidemiology Edition, fixed before any run. The Judge reads these; nothing else.

Damage follows the spec's universal clamping equation, applied once per rule:
    dHP = -round( clamp( D_raw x M_ability, 0, Dmax(level) ) )
Within a level, each enemy deals one term of that level's formula; the running total is clamped,
so the HP an agent loses across the level equals the formula exactly.
"""

STARTING_HP = 100
STARTING_CREDITS = 100
D_MAX = {1: 20, 2: 30, 3: 45, 4: 60}
EPS = 1e-9

# thresholds and constants used by the formulas
PANIC_SIGMAS = 2.0          # a panic window: media volume above mean + 2 sd
Z_POWER = 2.80              # z(alpha/2 = .025) + z(beta = .20): 1.96 + 0.84
ALPHA = 0.05
HAC_LAG = 14                # Newey-West lag for daily series (two weeks)
AR_ORDER = 4
SURGE_GROWTH = 1.15         # a surge-onset day: admissions up at least 15% on a week earlier
SS_MARGIN = 0.05            # |SS| <= 5% counts as "no better than the baseline"
SS_REF = 0.30               # Norm(SS) = 100 x clamp(SS / 0.30, 0, 1): a 30% error cut earns full marks
BIAS_HEAL = 5
EUREKA_HEAL = 10
VALIDATION_SLICE = 0.2      # Ablation Strike prunes on the last 20% of the training period

TRAPS = {1: "MEDIA_PANIC_NOISE", 2: "SEASONAL_CONFOUNDING", 3: "LAG_DREDGING_OVERFIT", 4: "VINTAGE_BACKFILL_LEAK"}

LEVELS = {
    1: {"name": "The Rumour Dungeon", "evidence": "Forums, social symptom trends, raw search spikes, pharmacy chatter",
        "trap": "Exogenous panic and small-n clusters: media coverage spikes searches while transmission is flat.",
        "rule": "D_L1 = 12 x max(0, FAAR - 1) + 18 x rho_n"},
    2: {"name": "The Forgotten Archives", "evidence": "Preprints, single-centre cohorts, unadjusted environmental data",
        "trap": "Seasonal and demographic confounding: winter, school terms and dilution create spurious links.",
        "rule": "D_L2 = 22 x omega_spurious + 10 x I(p_adj > 0.05)"},
    3: {"name": "The Temple of Replication", "evidence": "Multi-region surveillance networks and replications",
        "trap": "Lag-dredging and spatial overfitting: search enough lags and one fits; urban fits fail rural.",
        "rule": "D_L3 = 25 x I(p_raw < .05 and p_corr > .05) + min(20, 5 ln K) + min(25, 20 x max(0, G_spatial))"},
    4: {"name": "The Citadel of Truth", "evidence": "Official registries as they stood on each decision day (vintages)",
        "trap": "Backfill leakage and baseline failure: finalized numbers were not known in real time.",
        "rule": "D_chrono = 35 x I_unreleased + min(25, round(40 x max(0, delta_vintage))); D_final by surge skill"},
}

# Abilities: costs and effects (spec sections 3 and 6). Two are this build's bindings of the
# spec's archetype abilities, marked "binding".
ABILITIES = {
    "FACT_CHECK": {"name": "Fact Check", "cost": 10, "level": 1,
                   "effect": "Purges media-spike weeks and flags small-n claims as exploratory: M = 0.20 for Rule 1."},
    "MEDIA_DENOISE": {"name": "Media De-Noising Filter", "cost": 20, "level": 1,
                      "effect": "Regresses news volume out of the signal, turning it into a media-adjusted index for every later level."},
    "EXPLORATORY_CLAIM": {"name": "Exploratory Claim", "cost": 5, "level": 1, "binding": True,
                          "effect": "Declares the claim exploratory: cheap, weak cover, M = 0.50 for Rule 1."},
    "BIAS_DETECTION": {"name": "Bias Detection", "cost": 15, "level": 2,
                       "effect": "Puts the confounder Z in the model before the attack: omega = 0 and +5 HP for rigour."},
    "PREREGISTER": {"name": "Preregister", "cost": 25, "level": 3,
                    "effect": "Locks one biologically grounded lag before testing: K = 1, so p_corr = p_raw."},
    "REPLICATION_SHIELD": {"name": "Replication Shield", "cost": 25, "level": 3,
                           "effect": "Shrinks the signal's weights (ridge, tuned by time-blocked CV in the home region) so they transfer."},
    "TEMPORAL_GUARD": {"name": "Temporal Guard", "cost": 20, "level": 4,
                       "effect": "Point-in-time masking plus a reporting-delay nowcast: trains on vintages, no 35 HP leak penalty."},
    "ABLATION_STRIKE": {"name": "Ablation Strike", "cost": 15, "level": 4, "binding": True,
                        "effect": "Drops every signal that does not lower error on a validation slice of the training period."},
}
M_ABILITY = {"FACT_CHECK": 0.20, "EXPLORATORY_CLAIM": 0.50}

# The enemies, in the order they attack. "term" names the slice of the level formula an enemy deals;
# scouts (term None) run the measurements the formula needs and deal no damage.
ENEMIES = {
    1: [
        {"key": "slime", "name": "Slime of Misinformation", "term": None, "test": "Signal extraction and effective sample size",
         "attack": "Half the posts are bots. How much real evidence is in there?"},
        {"key": "wisp", "name": "Echo Chamber Wisp", "term": None, "test": "Media panic-window detector (M_t > mean + 2 sd)",
         "attack": "Everyone is talking about it. Doesn't that make it true?"},
        {"key": "goblin", "name": "Rumour Goblin", "term": "faar", "test": "False Alarm Amplification Ratio",
         "attack": "A celebrity caught it! Searches are exploding!"},
        {"key": "bat", "name": "Anecdote Bat", "term": "rho_n", "test": "Power: n against n_min = (2.80 / atanh|r|)^2 + 3",
         "attack": "It worked for a clinic of twenty-eight. Good enough?"},
    ],
    2: [
        {"key": "mimic", "name": "Preprint Mimic", "term": None, "test": "Unadjusted effect r_XY",
         "attack": "The preprint says it works. Peer review is a formality."},
        {"key": "spider", "name": "Citation Spider", "term": None, "test": "Links to the confounder: r_XZ and r_YZ",
         "attack": "Every paper cites the same winter. Are you sure it's your signal?"},
        {"key": "phantom", "name": "Confounding Phantom", "term": "omega", "test": "Partial correlation and spurious fraction omega",
         "attack": "Take away the season and what is left of your effect?"},
        {"key": "skeleton", "name": "Small Sample Skeleton", "term": "p_adj", "test": "Adjusted effect, autocorrelation-corrected p-value",
         "attack": "Day-to-day data repeats itself. How many independent days do you really have?"},
    ],
    3: [
        {"key": "knight", "name": "Publication Bias Knight", "term": "ln_k", "test": "Search-space penalty min(20, 5 ln K)",
         "attack": "How many lags and streams did you try before this one?"},
        {"key": "sentinel", "name": "Replication Sentinel", "term": "sidak", "test": "Sidak correction p_corr = 1 - (1 - p_raw)^K",
         "attack": "Is it still significant once every try is counted?"},
        {"key": "wraith", "name": "Contradiction Wraith", "term": None, "test": "Error in each held-out region",
         "attack": "The other regions tell a different story."},
        {"key": "chimera", "name": "The Data Chimera", "term": "g_spatial", "test": "Cross-site generalization drop G_spatial", "boss": True,
         "attack": "Your city fit means nothing in the counties. Show me."},
    ],
    4: [
        {"key": "titan", "name": "The Bureaucratic Titan", "term": None, "test": "Point-in-time vintage archive audit",
         "attack": "The official numbers were revised for three weeks. Which ones did you use?"},
        {"key": "reaper", "name": "The Leakage Reaper", "term": None, "test": "Look-ahead audit: lag against forecast horizon",
         "attack": "Did your model read a number that did not exist yet?"},
        {"key": "chronolock", "name": "Chronolock Guardian", "term": "chrono", "test": "Vintage reporting-delay penalty", "boss": True,
         "attack": "Forecast as you would have on the day, with the data as it stood."},
        {"key": "guardian", "name": "Guardian of False Discoveries", "term": "final", "test": "Surge-onset skill vs AR(4), Diebold-Mariano", "boss": True,
         "attack": "Beat the hospital-only baseline when the surge begins. On data you have never seen."},
    ],
}
# Within a level the terms share one clamp, except Level 4 where the two bosses are separate rules.
RULE_OF = {"faar": "L1", "rho_n": "L1", "omega": "L2", "p_adj": "L2", "ln_k": "L3", "sidak": "L3",
           "g_spatial": "L3", "chrono": "L4A", "final": "L4B"}
RULE_LEVEL = {"L1": 1, "L2": 2, "L3": 3, "L4A": 4, "L4B": 4}

# The traps an agent can falsify (Rule 5's Traps_Falsified / Total_Traps): one per damage term.
TRAP_LABELS = {"faar": "Media panic", "rho_n": "Underpowered sample", "omega": "Confounding",
               "p_adj": "Effect gone after adjustment", "ln_k": "Lag dredging", "sidak": "Significance from search",
               "g_spatial": "Spatial overfitting", "chrono": "Vintage leakage", "final": "No surge-onset skill"}

# Rule 5: the composite score, fixed in advance.
SCORE_WEIGHTS = {"skill": 0.35, "hp": 0.25, "traps": 0.25, "efficiency": 0.15}
SCORE_RULES = {
    "skill": "0.35 x Norm(SS_surge), Norm = 100 x clamp(SS / 0.30, 0, 1)",
    "hp": "0.25 x HP_final",
    "traps": "0.25 x 100 x traps falsified / traps faced",
    "efficiency": "0.15 x min(100, 100 x ablation lift % / max(10, credits spent))",
}

VERDICTS = {
    "VALIDATED": "Beat the AR(4) baseline at surge onset on unseen, real-time data, and the gain is unlikely to be luck (Diebold-Mariano p < 0.05).",
    "NOT BETTER": "Survived, but did not beat the hospital-only baseline on unseen real-time data.",
    "BASELINE": "The benchmark itself: AR(4) plus a seasonal harmonic on admissions alone.",
    "FALLEN": "Research integrity reached 0 HP.",
}

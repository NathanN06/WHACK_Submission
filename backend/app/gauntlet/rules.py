"""Every rule of the Hypothesis Gauntlet, fixed before any run.

HP is a game abstraction for "research integrity", not a probability. Each HP change
comes from one row of ENCOUNTERS below and one deterministic test result, so the same
data and seed always give the same damage. docs/gauntlet-rules.md explains the weighting.
"""

STARTING_HP = 100
STARTING_CREDITS = 18  # mandatory checks cost 12 in total, so every agent must skip a few optional ones
PASS_HEAL = 5          # a passed check restores a little HP (never above STARTING_HP)
CONCEDE_DAMAGE = 5     # declining an optional challenge: the claim stays unverified
SKEPTIC_CHALLENGES_PER_LEVEL = 2
REVISE_COST = 1        # the Researcher may flip a claim's direction after the Rumour Goblin

# Thresholds used by the checks (see checks.py).
MIN_PEOPLE = 10            # fewer people than this and a claim cannot be judged
ECHO_CORR = 0.9            # |r| with the baseline at or above this: the claim just repeats it
MAJORITY = 0.5             # share of people that must agree / benefit
FOLDS_NEEDED = 3           # of 5 independent participant groups that must replicate
TRIM_SHARE = 0.1           # selection-bias check drops this share of top contributors

ABILITIES = {
    "fact_check": "Fact Check",
    "bias_detection": "Bias Detection",
    "replication_shield": "Replication Shield",
    "ablation_strike": "Ablation Strike",
    "temporal_guard": "Temporal Guard",
    "preregister": "Preregister",
}

LEVELS = {
    1: {"name": "The Rumour Dungeon", "evidence": "Popular claims and folk wisdom",
        "blurb": "Every claim starts as a rumour. Popular is not the same as true."},
    2: {"name": "The Forgotten Archives", "evidence": "Preliminary analysis of the discovery data",
        "blurb": "A first study of the evidence. Does the claim add anything at all?"},
    3: {"name": "The Temple of Replication", "evidence": "Independent groups, shuffles and the count of every try",
        "blurb": "A real effect replicates. A lucky one dissolves under scrutiny."},
    4: {"name": "The Citadel of Truth", "evidence": "An independent population never seen before",
        "blurb": "Locked claims meet people the agents have never seen."},
}

# One row per enemy. kind: "gate" (the Statistical Judge always runs it) or
# "challenge" (the Skeptic may send it; the agent pays to defend or concedes).
# damage: HP lost on a failed check. Tests with a severity split use damage_severe
# when the evidence points the wrong way, not merely "not enough".
ENCOUNTERS = {
    # ---- Level 1: The Rumour Dungeon ----
    "slime": {"weakness": "Unmeasurable claims", "level": 1, "name": "Slime of Misinformation", "kind": "gate", "cost": 0,
              "ability": "fact_check", "test": "coverage", "damage": 0,
              "attack": "Nobody ever measured that. You can't check it, so believe it!"},
    "goblin": {"weakness": "Public rumour noise", "level": 1, "name": "Rumour Goblin", "kind": "gate", "cost": 1,
               "ability": "fact_check", "test": "raw_direction", "damage": 5, "damage_severe": 15,
               "attack": "Everyone online says it's true. Popularity is proof!"},
    "bat": {"weakness": "Anecdotal evidence", "level": 1, "name": "Anecdote Bat", "kind": "challenge", "cost": 1,
            "ability": "bias_detection", "test": "within_person", "damage": 10,
            "attack": "It worked for my cousin, so it works for everyone!"},
    "wisp": {"weakness": "Echo of known evidence", "level": 1, "name": "Echo Chamber Wisp", "kind": "challenge", "cost": 1,
             "ability": "fact_check", "test": "echo", "damage": 20,
             "attack": "Your claim is just carbs, repeated back to you in a new costume."},
    # ---- Level 2: The Forgotten Archives ----
    "mimic": {"weakness": "No added predictive value", "level": 2, "name": "Preprint Mimic", "kind": "gate", "cost": 2,
              "ability": "ablation_strike", "test": "added_value", "damage": 30,
              "attack": "This promising preprint says your claim improves predictions. Trust it!"},
    "skeleton": {"weakness": "Small, uneven samples", "level": 2, "name": "Small Sample Skeleton", "kind": "challenge", "cost": 1,
                 "ability": "bias_detection", "test": "majority_benefit", "damage": 10,
                 "attack": "Your average is carried by a handful of people."},
    "phantom": {"weakness": "Confounding", "level": 2, "name": "Confounding Phantom", "kind": "challenge", "cost": 1,
                "ability": "bias_detection", "test": "confounding", "damage": 10,
                "attack": "Your effect is really something else hiding behind it."},
    "spider": {"weakness": "Too good to be true", "level": 2, "name": "Citation Spider", "kind": "challenge", "cost": 1,
               "ability": "fact_check", "test": "too_good", "damage": 10,
               "attack": "A result this strong cites itself. Too good to be true?"},
    # ---- Level 3: The Temple of Replication ----
    "sentinel": {"weakness": "Failed replication", "level": 3, "name": "Replication Sentinel", "kind": "gate", "cost": 2,
                 "ability": "replication_shield", "test": "fold_replication", "damage": 15,
                 "attack": "Show me it works in groups of people you did not fit it on."},
    "wraith": {"weakness": "Conflicting measurements", "level": 3, "name": "Contradiction Wraith", "kind": "challenge", "cost": 2,
               "ability": "replication_shield", "test": "sensor_check", "damage": 15,
               "attack": "A second glucose sensor tells a different story."},
    "chimera_overfit": {"weakness": "Overfitting (could be luck)", "level": 3, "name": "The Data Chimera", "head": "Overfitting", "kind": "gate",
                        "cost": 3, "ability": "replication_shield", "test": "shuffle_test", "damage": 30,
                        "attack": "OVERFITTING! Scrambled data could have done just as well."},
    "chimera_selection": {"weakness": "Selection bias", "level": 3, "name": "The Data Chimera", "head": "Selection Bias",
                          "kind": "challenge", "cost": 1, "ability": "bias_detection",
                          "test": "trimmed_gain", "damage": 10,
                          "attack": "SELECTION BIAS! Remove your best cases and it vanishes."},
    "knight": {"weakness": "Publication bias (many tries)", "level": 3, "name": "Publication Bias Knight", "kind": "gate", "cost": 0,
               "ability": "preregister", "test": "penalty", "damage": 15,
               "attack": "You tried many claims and only report the winners."},
    # ---- Level 4: The Citadel of Truth ----
    "chronolock": {"weakness": "Future-data leakage", "level": 4, "name": "Chronolock Guardian", "kind": "gate", "cost": 0,
                   "ability": "temporal_guard", "test": "temporal", "damage": 40,
                   "attack": "Was this information known when the meal was eaten?"},
    "reaper": {"weakness": "Outcome leakage", "level": 4, "name": "The Leakage Reaper", "kind": "gate", "cost": 0,
               "ability": "temporal_guard", "test": "leak_audit", "damage": 100,
               "attack": "Your evidence is built from the very outcome it predicts."},
    "titan": {"weakness": "Missing from independent records", "level": 4, "name": "The Bureaucratic Titan", "kind": "gate", "cost": 1,
              "ability": "fact_check", "test": "provenance", "damage": 0,
              "attack": "The official records say what they say. Is it even recorded there?"},
    "guardian": {"weakness": "Fails on unseen people", "level": 4, "name": "Guardian of False Discoveries", "kind": "gate", "cost": 3,
                 "ability": "ablation_strike", "test": "final_boss", "damage": 50,
                 "attack": "Predict people you have never seen, better than the baseline."},
}

LEVEL_ORDER = {
    1: ["slime", "goblin", "bat", "wisp"],
    2: ["mimic", "skeleton", "phantom", "spider"],
    3: ["sentinel", "wraith", "chimera_overfit", "chimera_selection"],  # the Knight runs level-wide after
    4: ["chronolock", "reaper", "titan", "guardian"],
}

# The checks a claim must pass to be called a validated discovery.
VALIDATION = ("added_value", "shuffle_test", "penalty", "temporal", "leak_audit", "final_boss")

# The winning rule (spec section 9): an auditable score out of 100, from test results only.
# Every agent faces the same tests, data and credit budget. HP adds a small narrative bonus
# but can never outweigh evidence, and only a VALIDATED claim can be champion.
SCORE_COMPONENTS = {
    "validity": {"max": 20, "label": "Scientific validity",
                 "rule": "Share of the soundness checks passed (Trial, echo, within-person, majority, confounding); untested optional ones count half"},
    "out_of_sample": {"max": 25, "label": "Out-of-sample performance",
                      "rule": "25 if it beats the baseline on never-seen people (CI above 0); 8 if the gain is positive but uncertain; else 0"},
    "falsification": {"max": 20, "label": "Response to falsification tests",
                      "rule": "10 for beating scrambled data, 5 for replicating in 3 of 5 groups, 5 for surviving selection-bias/sensor checks"},
    "uncertainty": {"max": 10, "label": "Handling of uncertainty",
                    "rule": "10 if still significant after correcting for every claim tried (Benjamini-Hochberg)"},
    "misleading": {"max": 5, "label": "Detection of misleading evidence",
                   "rule": "5 if the raw direction was not contradicted (or was revised) and the result was not too good to be true"},
    "leakage": {"max": 15, "label": "Avoidance of data leakage",
                "rule": "7.5 for using only mealtime information, 7.5 for no feature built from the outcome"},
    "efficiency": {"max": 5, "label": "Research efficiency",
                   "rule": "5 x share of checks that were neither redundant nor conceded"},
}
HP_BONUS = 0.05  # up to +5 for HP left: narrative, never decisive

VERDICTS = {
    "VALIDATED": "Survived every level and replicated on unseen people.",
    "UNSUPPORTED": "Still standing, but the evidence does not back the claim.",
    "UNPROVEN": "Ran out of research credits before the decisive test.",
    "UNTESTABLE": "The data cannot judge this claim either way.",
    "LOOK-AHEAD": "Relied on information from after the meal. Disqualified.",
    "FALLEN": "Research integrity reached zero.",
}

DEFAULT_QUESTION = "What changes how much a person's blood sugar rises after a meal?"

# Characters. Hypotheses get a class from what kind of evidence they lean on.
CLASS_BY_FEATURE = {
    "carbs": "Alchemist", "fiber": "Herbalist", "protein": "Alchemist", "fat": "Alchemist",
    "sugar": "Alchemist", "calories": "Alchemist", "baseline_glucose": "Seer",
    "hour_of_day": "Chronomancer", "hours_since_last_meal": "Chronomancer",
    "steps_after": "Ranger", "hr_after": "Ranger", "hba1c": "Cleric",
    "lucky_charm": "Bard", "moon_phase": "Astrologer", "meal_intensity_score": "Seer",
    "carb_load_index": "Alchemist",
}
NAMES = ["Ilsa", "Bram", "Corin", "Dagny", "Edda", "Fenn", "Garrick", "Hale", "Iver", "Juno",
         "Kael", "Lira", "Mott", "Nyx", "Orrin", "Pell", "Quill", "Rhea", "Sorrel", "Tamsin"]

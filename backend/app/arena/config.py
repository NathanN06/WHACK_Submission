"""Every rule and number the arena uses, fixed before any run."""

STARTING_HP = 100
STARTING_REPUTATION = 100
STARTING_DENARII = 60

# What each opponent costs the Lanista to send in.
COST = {
    "added_value": 1,
    "leak_audit": 0,
    "shuffle_test": 3,
    "penalty": 0,
    "sensor_check": 2,
    "final_boss": 5,
}

# Damage a gladiator takes when it loses to that opponent.
DAMAGE = {
    "added_value": 100,
    "leak_audit": 100,
    "shuffle_test": 100,
    "penalty": 100,
    "sensor_check": 50,
    "final_boss": 100,
}

REPUTATION_LOSS_ON_DEATH = 20
REPUTATION_GAIN_ON_CHAMPION = 15

ALPHA = 0.05
N_SPLITS = 5
N_BOOT = 1000
N_PERM = 500  # smallest p = 1/501; the Census needs room to multiply it by every claim tried
MIN_PARTICIPANTS = 10
REDUNDANT_CORR = 0.15  # standalone |r| at or above this, but no added value -> REDUNDANT
TOO_GOOD_GAIN_SHARE = 0.25  # gain above 25% of baseline error looks too good to be true

# Display names for the UI and the narration.
OPPONENTS = {
    "added_value": "The Trial",
    "leak_audit": "The Inquisitor",
    "shuffle_test": "The Shuffler",
    "penalty": "The Census",
    "sensor_check": "The Twins",
    "final_boss": "The Champion of Brno",
}

DAY_NAMES = {
    1: "Day I: The Baseline",
    2: "Day II: The Macros",
    3: "Day III: The Lifestyle",
    4: "Day IV: The Decoy Games",
    5: "Day V: The Champion",
}

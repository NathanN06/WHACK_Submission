"""The simulated evidence worlds of the Peptide & GLP-1 edition.

Each campaign is a deterministic, synthetic world with planted, known effects:
  * an EHR cohort across five sites (patients, confounders, prescription fills, outcome events),
  * a social corpus per scroll (YouTube, Quora, Reddit posts, with affiliate codes and reposts),
  * a literature base per scroll (species, design, lab of each supporting paper),
  * a trial registry per scroll (completed human RCTs).
Nothing here is real data or a real finding. The truth each world was built with is revealed in the brief.

The cohort is split by calendar time: training years, the vaulted Level 4 holdout, and a second
vault kept unexposed for a later validation run.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from . import rules

DAYS = 1800                 # five years of index dates
TRAIN_END = 1100            # index day < 1100: training years
HOLDOUT_END = 1450          # 1100 <= index < 1450: the vaulted Level 4 holdout; later: a second, unexposed vault

SITES = [("North Metro Health", False), ("River Valley Medical", False), ("Coastal Clinic Network", False),
         ("Prairie Rural Health", True), ("Mountain Rural Health", True)]
SUBGROUPS = ["everyone", "under 50", "50 and over", "women", "men", "higher severity", "lower severity"]


@dataclass
class Outcome:
    key: str
    label: str
    base_rate: float        # one-year risk among comparators, before confounders
    beta: float             # true log hazard ratio once the drug has started (the planted truth)


@dataclass
class Corpus:
    posts: int              # supporting posts scraped
    affiliate: float        # share carrying an affiliate code or sponsorship
    stories: int            # independent original stories; the rest are reposts of them
    platforms: tuple = (0.45, 0.2, 0.35)        # YouTube, Quora, Reddit shares
    affiliate_story_share: float = 0.0          # share of the original stories that are themselves sponsored


@dataclass
class Literature:
    human: int = 0
    rodent: int = 0
    in_vitro: int = 0
    labs: tuple = (1.0,)                        # share of papers from each lab
    records: list | None = None                 # REAL papers (hypotheses.py): species and lab of each, used as they are


@dataclass
class Scroll:
    """One hypothesis the hero carries (or the Gatekeeper's baseline)."""
    key: str
    archetype: str          # HYPE | PIONEER | PREPRINT | SKEPTIC
    title: str              # the scroll's short name
    claim: str
    outcome: str = ""       # the outcome key it claims
    outcomes_searched: int = 1
    subgroups_searched: int = 1
    design: str = "ever"    # "ever": exposed from the index date if ever filled (immortal time); "new_user": time-zero aligned
    corpus: Corpus | None = None
    literature: Literature | None = None
    n_rct: int = 0
    plan: dict = field(default_factory=dict)
    origin: str = ""        # where the scroll was found
    evidence_topic: str = ""    # the real evidence topic its papers and trials come from (hypotheses.py)
    evidence_real: bool = False


@dataclass
class Campaign:
    id: str
    letter: str
    title: str
    question: str
    drug: str
    comparator: str
    population: str
    outcomes: list
    scrolls: list
    truth: str
    gatekeeper: dict
    n: int = 14000
    uptake: float = -0.2                        # intercept of the treatment-assignment model
    confounding: dict = field(default_factory=dict)   # covariate -> log-odds of getting the peptide
    risk: dict = field(default_factory=dict)          # covariate -> log hazard of the outcome
    start_mean: float = 60.0                    # mean days from index to the first peptide fill
    site_beta: tuple = (0, 0, 0, 0, 0)          # extra log hazard ratio per site (heterogeneity)
    effect_direction: int = -1                  # -1: the claim is a reduction, +1: an increase


COVARIATES = ["age10", "female", "severity", "healthy", "trt", "therapy"]
COVARIATE_LABELS = {"age10": "Age (per 10 years)", "female": "Female", "severity": "Baseline severity",
                    "healthy": "Healthy-user score (gym, diet, screening)", "trt": "Testosterone co-use",
                    "therapy": "Behavioural coaching / therapy"}


class World:
    """Generates and holds one campaign's synthetic data. Deterministic for a (campaign, seed)."""

    def __init__(self, c: Campaign, seed: int = 0):
        self.c, self.seed = c, seed
        rng = np.random.default_rng(1000 + seed * 7 + ord(c.letter))
        n = c.n
        self.site = rng.integers(0, len(SITES), n)
        self.index = rng.integers(0, DAYS, n)
        age = rng.normal(52, 12, n).clip(18, 90)
        self.X = {
            "age10": (age - 52) / 10,
            "female": (rng.random(n) < 0.45).astype(float),
            "severity": rng.normal(0, 1, n),
            "healthy": rng.normal(0, 1, n),
        }
        self.X["trt"] = (rng.random(n) < _sig(-2.0 + 0.9 * self.X["healthy"] - 1.5 * self.X["female"])).astype(float)
        self.X["therapy"] = (rng.random(n) < _sig(-1.2 + 0.4 * self.X["healthy"])).astype(float)
        self.age = age
        lo = c.uptake + sum(c.confounding.get(k, 0.0) * self.X[k] for k in COVARIATES)
        self.peptide = rng.random(n) < _sig(lo)                       # intends to start the peptide
        self.start = np.where(self.peptide, rng.exponential(c.start_mean, n), np.inf)
        self.nausea = (rng.random(n) < np.where(self.peptide, 0.30, 0.08)).astype(float)
        # outcome events: before the first fill at the comparator hazard, after it at hazard x exp(beta)
        lin = sum(c.risk.get(k, 0.0) * self.X[k] for k in COVARIATES)
        self.events = {}
        for o in c.outcomes:
            h = -np.log(1 - o.base_rate) / rules.FOLLOW_UP * np.exp(lin - np.mean(lin))
            beta = o.beta + np.asarray(c.site_beta)[self.site]
            e_pre = rng.exponential(1 / h)
            e_post = rng.exponential(1 / (h * np.exp(beta)))
            self.events[o.key] = (e_pre, e_post)
        self.split = np.where(self.index < TRAIN_END, "train", np.where(self.index < HOLDOUT_END, "holdout", "vault2"))

    # ---------- designs ----------

    def rows(self, outcome: str, design: str, mask: np.ndarray) -> dict:
        """Person-time rows for a Poisson model over the year after the index date.

        "ever": anyone who fills the peptide before their first event counts as exposed from day 0,
        so the waiting time before the fill (when they could not yet have been treated) is credited to the drug.
        "new_user": person-time is split at the first fill; before it the patient is unexposed.
        """
        e_pre, e_post = self.events[outcome]
        S, T = self.start[mask], rules.FOLLOW_UP
        first = np.where(e_pre[mask] < S, e_pre[mask], S + e_post[mask])
        event = first < T
        end = np.minimum(first, T)
        idx = np.nonzero(mask)[0]
        if design == "ever":
            exposed = (S < end).astype(float)
            return {"i": idx, "exposed": exposed, "pt": end, "event": event.astype(float)}
        started = S < end
        pre_pt = np.where(started, S, end)
        post_pt = np.where(started, end - S, 0.0)
        pre_event = event & ~started
        post_event = event & started
        keep = started
        return {"i": np.concatenate([idx, idx[keep]]), "exposed": np.concatenate([np.zeros(len(idx)), np.ones(keep.sum())]),
                "pt": np.concatenate([pre_pt, post_pt[keep]]),
                "event": np.concatenate([pre_event, post_event[keep]]).astype(float)}

    def new_user(self, outcome: str, mask: np.ndarray) -> dict:
        """The active-comparator new-user cohort: initiators followed from their first fill, comparators from the index date."""
        e_pre, e_post = self.events[outcome]
        T = rules.FOLLOW_UP
        init = mask & (self.start < 180)
        comp = mask & ~self.peptide
        i = np.concatenate([np.nonzero(init)[0], np.nonzero(comp)[0]])
        treated = np.concatenate([np.ones(init.sum()), np.zeros(comp.sum())])
        y = np.concatenate([e_post[init] < T, e_pre[comp] < T]).astype(float)
        return {"i": i, "treated": treated, "y": y}

    def covariates(self, i: np.ndarray, sites: bool = True) -> np.ndarray:
        cols = [self.X[k][i] for k in COVARIATES]
        if sites:
            cols += [(self.site[i] == s).astype(float) for s in range(1, len(SITES))]
        return np.column_stack(cols)

    def subgroup(self, name: str) -> np.ndarray:
        X = self.X
        return {"everyone": np.ones(self.c.n, bool), "under 50": self.age < 50, "50 and over": self.age >= 50,
                "women": X["female"] == 1, "men": X["female"] == 0, "higher severity": X["severity"] > 0,
                "lower severity": X["severity"] <= 0}[name]

    def mask(self, split: str) -> np.ndarray:
        return self.split == split

    # ---------- the other sources ----------

    def corpus(self, s: Scroll, denoised: bool = False) -> list[dict]:
        """Synthetic posts supporting the scroll: platform, story cluster, affiliate flag."""
        if s.corpus is None:
            return []
        c = s.corpus
        rng = np.random.default_rng(31 + self.seed + hash_key(s.key))
        stories = np.arange(c.stories)
        sponsored_story = rng.random(c.stories) < c.affiliate_story_share
        cluster = np.concatenate([stories, rng.choice(stories, max(0, c.posts - c.stories))])
        # reposts of sponsored stories carry the code; organic stories still attract some sponsored reposts
        aff = np.where(sponsored_story[cluster], True, rng.random(len(cluster)) < c.affiliate)
        platform = rng.choice(3, len(cluster), p=np.asarray(c.platforms) / sum(c.platforms))
        repost = np.zeros(len(cluster), bool)
        repost[c.stories:] = True
        posts = [{"cluster": int(k), "affiliate": bool(a), "platform": ["YouTube", "Quora", "Reddit"][p], "repost": bool(r)}
                 for k, a, p, r in zip(cluster, aff, platform, repost)]
        if denoised:
            posts = [p for p in posts if not p["affiliate"] and not p["repost"]]
        return posts

    def papers(self, s: Scroll) -> list[dict]:
        if s.literature is None:
            return []
        L = s.literature
        if L.records is not None:
            return [{"species": r["species"], "lab": r["lab"]} for r in L.records]
        rng = np.random.default_rng(57 + self.seed + hash_key(s.key))
        species = ["human"] * L.human + ["rodent"] * L.rodent + ["in vitro"] * L.in_vitro
        labs = rng.choice(len(L.labs), len(species), p=np.asarray(L.labs) / sum(L.labs))
        return [{"species": sp, "lab": f"Lab {int(lab) + 1}"} for sp, lab in zip(species, labs)]


def hash_key(key: str) -> int:
    return sum((i + 1) * ord(ch) for i, ch in enumerate(key)) % 9973


def _sig(x):
    return 1 / (1 + np.exp(-x))

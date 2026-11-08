"""The Archivist's Ledger: every source a number can come from and every method that measures one.

A quest registers its sources once, at the start, and adds each piece of evidence the Research Director brings.
Every encounter then names the method that measured it and the sources that method read, so any number in the
brief traces back: encounter (E###) -> method -> sources. The finale writes the whole trace into a manifest and
checks it is complete.

Source types (what a source is):
  SIMULATED           the synthetic cohort or social corpus (world.py): fingerprinted, never real
  REAL_METADATA       real records copied from data/pep_evidence.duckdb (Europe PMC papers, ClinicalTrials.gov counts)
  USER_UPLOADED       a file the Research Director attached (its SHA-256 recorded)
  DIRECTOR_STATEMENT  a link or a claim the Director typed: kept, never treated as fact
  DERIVED             computed by the Judge from other sources
  PRIOR_ROUND         a champion's frozen claim carried over from an earlier Challenger round
Usage (what a source may do): NUMERIC_TEST (a test reads its numbers), CONTEXT (shown, never measured), EXCLUDED.
"""

from __future__ import annotations

import hashlib
import json

from .world import Literature

TYPES = ("SIMULATED", "REAL_METADATA", "USER_UPLOADED", "DIRECTOR_STATEMENT", "DERIVED", "PRIOR_ROUND")
USAGE = ("NUMERIC_TEST", "CONTEXT", "EXCLUDED")

# Every method a number on screen can come from. The id is what an encounter cites.
METHODS = {
    "M-L1-CORPUS": "Corpus scrape of the simulated social posts: counts by platform, affiliate share, independent stories.",
    "M-L2-SPECIES": "Species of the papers behind the scroll: non-human share of the supporting studies.",
    "M-L2-POISSON": "Poisson rate ratio with a person-time offset, naive and adjusted for measured confounders and site; "
                    "training years only, follow-up censored at the training cutoff.",
    "M-L2-BALANCE": "Standardized mean differences of each confounder between users and comparators (training years).",
    "M-L3-SIDAK": "Best of K outcome and subgroup tests (Poisson rate ratios), Sidak-corrected: p_corr = 1 - (1 - p)^K.",
    "M-L3-HLAB": "Lab concentration: sum of squared shares of the evidence by lab (replicating sites count as labs).",
    "M-L3-SITES": "Per-site Poisson rate ratio in each of the five EHR sites (training years).",
    "M-L3-RCT": "Completed randomized human trials in the registry for the scroll's evidence topic.",
    "M-L4-IMMORTAL": "Exposure-definition audit: share of the 'treated' person-time that came before the first fill.",
    "M-L4-PURGE": "Immortal-time purge: the rate ratio as carried vs in a new-user, time-zero design.",
    "M-L4-GUARDIAN": "Brier skill of the scroll's effect vs the comparator's risk model on 1:1 propensity-matched new users "
                     "of the vaulted holdout, paired one-sided t-test; the matched risk ratio (standardized to the "
                     "comparator model) with an exact conditional or Wald 95% interval gives the scientific status.",
    "M-MYSTERY-SEASONAL": "Season-adjusted rate ratio (quarter of the index date) and the effect in each quarter.",
    "M-MYSTERY-CHRONOLOCK": "Leakage audit: immortal time in the exposure definition, and every training row ending by the cutoff.",
    "M-MYSTERY-REGIONAL": "Per-site rate ratios, Cochran's Q heterogeneity test, and the rural sites pooled.",
    "M-MYSTERY-CHANCE": "Permutation test of the one-year risk difference in the new-user cohort, Sidak-corrected.",
    "M-MYSTERY-REPLICATION": "Rate ratio on the earlier training years and, separately, on the last quarter of them.",
    "M-MYSTERY-REDUNDANCY": "Ablation on a later slice of the training years: skill vs the no-drug-effect baseline.",
    "M-MYSTERY-CONFOUNDER": "Rate ratio adjusted for the named (or every measured) confounder.",
    "M-MYSTERY-SECRET": "Schema audit, Fisher's exact test and a heterogeneity z-test of a user dataset against the hero.",
    "M-TRIAL": "The locked specification scored once on matched new users of the second vault (Trial of Truth).",
    "M-REPEAT": "Not measured: the identical test on the unchanged scroll already ran.",
}

# Which method each enemy uses, and which kinds of source it reads ("lit" and "rct" are the scroll's own).
ENEMY_TRACE = {
    "slime": ("M-L1-CORPUS", ["corpus"]), "wisp": ("M-L1-CORPUS", ["corpus"]),
    "siren": ("M-L1-CORPUS", ["corpus"]), "bat": ("M-L1-CORPUS", ["corpus"]),
    "mimic": ("M-L2-POISSON", ["train"]), "spider": ("M-L2-BALANCE", ["train"]),
    "rat": ("M-L2-SPECIES", ["lit"]), "phantom": ("M-L2-POISSON", ["train"]),
    "knight": ("M-L3-SIDAK", ["train"]), "sentinel": ("M-L3-HLAB", ["lit", "train"]),
    "wraith": ("M-L3-SITES", ["train"]), "chimera": ("M-L3-RCT", ["rct"]),
    "titan": ("M-L4-IMMORTAL", ["train"]), "chronolock": ("M-L4-PURGE", ["train"]),
    "guardian": ("M-L4-GUARDIAN", ["train", "holdout"]),
}


class Registry:
    """The sources of one quest. Ids are stable within it: S-TRAIN, S-LIT-<scroll>, S-X01 and so on."""

    def __init__(self) -> None:
        self.items: dict[str, dict] = {}

    def add(self, sid: str, type_: str, label: str, usage: str, **meta) -> dict:
        assert type_ in TYPES and usage in USAGE, (type_, usage)
        rec = {"id": sid, "type": type_, "label": label, "usage": usage, **{k: v for k, v in meta.items() if v is not None}}
        self.items[sid] = rec
        return rec

    def public(self) -> list[dict]:
        return [dict(v) for v in self.items.values()]

    def ids_for(self, kinds: list[str], scroll_id: str | None) -> list[str]:
        out = []
        for k in kinds:
            sid = {"corpus": "S-CORPUS", "train": "S-TRAIN", "holdout": "S-HOLDOUT", "vault2": "S-VAULT2",
                   "lit": f"S-LIT-{scroll_id}", "rct": f"S-RCT-{scroll_id}"}[k]
            if sid in self.items:
                out.append(sid)
        return out


def register_world(reg: Registry, q) -> None:
    """The simulated cohort's partitions, the social corpus, and each scroll's papers and trial registry."""
    w, c = q.w, q.c
    n = {k: int((w.split == k).sum()) for k in ("train", "holdout", "vault2")}
    seed = {"campaign": c.id, "seed": q.seed}
    reg.add("S-TRAIN", "SIMULATED", f"Simulated EHR cohort, training years (index day < 1100): {n['train']} patients",
            "NUMERIC_TEST", sha256=w.fingerprints["train"], rows=n["train"], **seed)
    reg.add("S-HOLDOUT", "SIMULATED", f"Simulated EHR cohort, vaulted Level IV holdout (index days 1100 to 1449): "
            f"{n['holdout']} patients", "NUMERIC_TEST", sha256=w.fingerprints["holdout"], rows=n["holdout"], **seed)
    reg.add("S-VAULT2", "SIMULATED", f"Simulated EHR cohort, second vault (index day >= 1450), sealed until the Trial of "
            f"Truth: {n['vault2']} patients", "NUMERIC_TEST", sha256=w.fingerprints["vault2"], rows=n["vault2"],
            sealed=True, **seed)
    reg.add("S-CORPUS", "SIMULATED", "Simulated social corpus (YouTube, Quora, Reddit posts per scroll)", "NUMERIC_TEST", **seed)
    for a in q.agents.values():
        add_scroll(reg, a)


def add_scroll(reg: Registry, a) -> None:
    s = a.scroll
    recs = s.literature.records
    if s.evidence_real:
        reg.add(f"S-LIT-{a.id}", "REAL_METADATA", f"Europe PMC papers on {s.evidence_topic} ({len(recs)} with a known "
                f"species), copied from data/pep_evidence.duckdb", "NUMERIC_TEST", scroll=a.id, topic=s.evidence_topic,
                records=len(recs), sha256=digest([[r.get("title"), r.get("year"), r.get("species"), r.get("lab")] for r in recs]))
        reg.add(f"S-RCT-{a.id}", "REAL_METADATA", f"ClinicalTrials.gov: completed randomized trials on {s.evidence_topic} "
                f"({s.n_rct})", "NUMERIC_TEST", scroll=a.id, topic=s.evidence_topic, count=s.n_rct)
    else:
        lit = s.literature or Literature()
        reg.add(f"S-LIT-{a.id}", "SIMULATED", f"Simulated literature for {a.name} ({lit.human} human, {lit.rodent} rodent, "
                f"{lit.in_vitro} in vitro papers)", "NUMERIC_TEST", scroll=a.id)
        reg.add(f"S-RCT-{a.id}", "SIMULATED", f"Simulated trial registry for {a.name} ({s.n_rct} completed RCTs)",
                "NUMERIC_TEST", scroll=a.id, count=s.n_rct)
    if s.champion:
        reg.add(f"S-PRIOR-{s.champion['hid']}", "PRIOR_ROUND", f"Frozen claim of the reigning champion {s.champion['hid']} "
                f"(won round {s.champion.get('round')})", "CONTEXT", scroll=a.id, claim_sha256=s.champion.get("claim_hash"))


def add_intake(reg: Registry, rec: dict) -> dict:
    """A piece of evidence the Director brought: what it is, and whether any test may read its numbers."""
    cls = rec["classification"]
    if cls in ("IRRELEVANT", "INVALID OR INCOMPATIBLE DATA"):
        usage = "EXCLUDED"
    elif rec.get("_data") and cls == "VERIFIED AND TESTABLE":
        usage = "NUMERIC_TEST"
    else:
        usage = "CONTEXT"
    kind = "USER_UPLOADED" if rec["kind"] == "file" else "DIRECTOR_STATEMENT"
    label = {"file": f"Uploaded file {rec.get('filename')}", "url": f"Link {rec.get('url')}",
             "text": "The Director's statement"}[rec["kind"]] + f": {cls.lower()}"
    return reg.add(f"S-{rec['id']}", kind, label[:200], usage, intake=rec["id"], sha256=rec.get("sha256"),
                   url=rec.get("url"), classification=cls)


def digest(obj) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, default=str).encode()).hexdigest()


def trace(events) -> list[dict]:
    """Every encounter in the ledger with the method and sources it cites."""
    out = []
    for e in events:
        enc = e.encounter if hasattr(e, "encounter") else e.get("encounter")
        if not enc:
            continue
        out.append({"encounter": enc.get("encounterId"), "level": enc.get("level"), "scroll": enc.get("scrollId"),
                    "enemy": enc.get("enemyName"), "method": enc.get("methodId"), "sources": enc.get("sourceIds") or []})
    return out


def validate(rows: list[dict], reg: Registry, cites: list[str | None]) -> dict:
    """The trace is complete when every encounter names a known method and only registered sources, and every
    citation in the brief points at a traced encounter."""
    problems = []
    known = {r["encounter"] for r in rows}
    for r in rows:
        if r["method"] not in METHODS:
            problems.append(f"{r['encounter']}: unknown method {r['method']!r}")
        if not r["sources"] and r["method"] != "M-REPEAT":
            problems.append(f"{r['encounter']}: no source named")
        for sid in r["sources"]:
            if sid not in reg.items:
                problems.append(f"{r['encounter']}: unregistered source {sid}")
    for c in cites:
        if c and c not in known:
            problems.append(f"the brief cites {c}, which is not a traced encounter")
    return {"complete": not problems, "problems": problems[:20], "encounters": len(rows)}

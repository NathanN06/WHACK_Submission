"""What the hero may see before it decides: blinded structural telemetry and the Judge's already-released findings.

The planning payload is built from an explicit allowlist, field by field, never by copying a measurement dict:
  * telemetry: design flags computed WITHOUT any outcome (covariate balance between exposure groups, where the
    new users are, how long until the first fill, the scroll's own search plan, paper and post metadata);
  * released findings: what the Judge already measured for this scroll in EARLIER levels, on the training years
    only, each with the encounter id that holds it in the ledger.
It never contains the holdout or the sealed vault, a planted truth, a Guardian or Trial number, or anything
measured in the current or a later level. `assert_blinded` re-checks every payload before it leaves the engine.
"""

from __future__ import annotations

import math

from . import judge as J
from . import rules

PROMPT_VERSION = "alchemist-3"

TELEMETRY_SCHEMA = {
    "covariate_imbalance_flag": ("HIGH_SMD_IMBALANCE", "BALANCED", "UNKNOWN"),
    "site_concentration_flag": ("SINGLE_SITE_DOMINANCE", "DISTRIBUTED", "UNKNOWN"),
    "immortal_time_risk_flag": ("EXPOSURE_LAG_DETECTED", "ALIGNED_TIME_ZERO", "UNKNOWN"),
    "multiple_testing_burden": ("HIGH_SEARCH_MULTIPLICITY", "SINGLE_HYPOTHESIS", "UNKNOWN"),
    "estimated_cohort_size_tier": ("SMALL_N", "MEDIUM_N", "LARGE_N", "UNKNOWN"),
    "evidence_species_flag": ("MOSTLY_NON_HUMAN", "MOSTLY_HUMAN", "NO_HUMAN_EVIDENCE", "UNKNOWN"),
    "lab_concentration_flag": ("SINGLE_LAB_DOMINANCE", "DISTRIBUTED", "UNKNOWN"),
    "social_signal_flag": ("AFFILIATE_HEAVY", "ORGANIC", "UNKNOWN"),
}
DATA_QUALITY_FLAGS = ("LOW_SUBGROUP_SUPPORT", "FEW_PAPERS", "NO_SOCIAL_CORPUS")

# Field names that must never reach a planning payload, at any depth: holdout, vault and Trial results,
# Guardian skill, the planted truth, and the Judge's damage bookkeeping.
FORBIDDEN = ("ss_oos", "p_dm", "dm_stat", "loss_scroll", "loss_comparator", "lift_pct", "matched_pairs", "holdout",
             "vault", "truth", "planted", "beta_true", "base_rate", "trial", "guardian", "eureka", "observed",
             "predicted", "beta_used", "immortal_share", "delta_purge", "rr_purged", "hp_delta", "raw")


class LeakError(RuntimeError):
    """A planning payload carried something the hero must not see. The engine never sends it."""


# ---------------------------------------------------------------- telemetry

def flags(raw: dict) -> dict:
    """Map the Judge's outcome-free diagnostics to the approved flag vocabulary."""
    smd, top, lag = raw["max_abs_smd"], raw["top_site_share"], raw["median_days_to_first_fill"]
    n, papers, human = raw["initiators"], raw["papers"], raw["human_papers"]
    small, medium = rules.SIZE_TIERS
    t = {
        "covariate_imbalance_flag": "UNKNOWN" if smd is None else
                                    "HIGH_SMD_IMBALANCE" if smd > rules.SMD_IMBALANCE else "BALANCED",
        "site_concentration_flag": "UNKNOWN" if top is None else
                                   "SINGLE_SITE_DOMINANCE" if top > rules.SITE_DOMINANCE else "DISTRIBUTED",
        "immortal_time_risk_flag": "ALIGNED_TIME_ZERO" if raw["design"] == "new_user" else
                                   "UNKNOWN" if lag is None else
                                   "EXPOSURE_LAG_DETECTED" if lag > 0 else "ALIGNED_TIME_ZERO",
        "multiple_testing_burden": "HIGH_SEARCH_MULTIPLICITY" if raw["search_k"] > 1 else "SINGLE_HYPOTHESIS",
        "estimated_cohort_size_tier": "SMALL_N" if n < small else "MEDIUM_N" if n < medium else "LARGE_N",
        "evidence_species_flag": "UNKNOWN" if not papers else "NO_HUMAN_EVIDENCE" if human == 0 else
                                 "MOSTLY_HUMAN" if human / papers >= 0.5 else "MOSTLY_NON_HUMAN",
        "lab_concentration_flag": "UNKNOWN" if raw["top_lab_share"] is None else
                                  "SINGLE_LAB_DOMINANCE" if raw["top_lab_share"] > 0.5 else "DISTRIBUTED",
        "social_signal_flag": "UNKNOWN" if raw["sponsored_share"] is None else
                              "AFFILIATE_HEAVY" if raw["sponsored_share"] > rules.SPONSORED_HEAVY else "ORGANIC",
    }
    quality = []
    if n < 2 * small:
        quality.append("LOW_SUBGROUP_SUPPORT")
    if papers < 3:
        quality.append("FEW_PAPERS")
    if raw["sponsored_share"] is None:
        quality.append("NO_SOCIAL_CORPUS")
    t["data_quality_flags"] = quality
    validate(t)
    return t


def validate(t: dict) -> None:
    """The strict telemetry schema: exactly these keys, and only these values."""
    keys = set(TELEMETRY_SCHEMA) | {"data_quality_flags"}
    if set(t) != keys:
        raise LeakError(f"telemetry keys {sorted(set(t) ^ keys)} are outside the approved schema")
    for k, allowed in TELEMETRY_SCHEMA.items():
        if t[k] not in allowed:
            raise LeakError(f"telemetry {k} = {t[k]!r} is not an approved value")
    if not set(t["data_quality_flags"]) <= set(DATA_QUALITY_FLAGS):
        raise LeakError("unapproved data-quality flag")


def raw_diagnostics(w, s, st) -> dict:
    raw = J.structural_telemetry(w, s, st)
    labs: dict = {}
    for p in w.papers(s):
        labs[p["lab"]] = labs.get(p["lab"], 0) + 1
    raw["top_lab_share"] = (max(labs.values()) / sum(labs.values())) if labs else None
    return raw


# ---------------------------------------------------------------- released findings

def _sig(x) -> float | None:
    if x is None:
        return None
    v = float(x)
    return float(f"{v:.3g}") if math.isfinite(v) else None


def released(a, level: int) -> list[dict]:
    """The Judge's findings for this scroll from levels BEFORE `level`, training years only, with their ledger ids.

    Level IV (the vaulted holdout) is never released to planning: it is measured after the last decision."""
    out = []
    m1, m2, m3 = (a.m.get(k) for k in (1, 2, 3))
    if level > 1 and m1:
        out += [{"id": "L1.affiliate_skew", "value": _sig(m1["phi"]), "ref": a.encounters.get("affiliate"),
                 "meaning": "share of supporting posts carrying a sponsorship code"},
                {"id": "L1.independent_stories", "value": m1["n_eff"], "ref": a.encounters.get("neff"),
                 "meaning": "independent original stories behind the posts"}]
    if level > 2 and m2:
        nv, ad = m2["naive"], m2["adjusted"]
        out += [{"id": "L2.rate_ratio_naive", "value": _sig(nv["rr"]), "ci": [_sig(math.exp(nv["beta"] - 1.96 * nv["se"])),
                 _sig(math.exp(nv["beta"] + 1.96 * nv["se"]))], "ref": a.encounters.get("confound"),
                 "meaning": "training-years rate ratio, unadjusted, the scroll's design and subgroup"},
                {"id": "L2.rate_ratio_adjusted", "value": _sig(ad["rr"]), "ci": [_sig(math.exp(ad["beta"] - 1.96 * ad["se"])),
                 _sig(math.exp(ad["beta"] + 1.96 * ad["se"]))], "ref": a.encounters.get("confound"),
                 "meaning": "the same, adjusted for every measured confounder and site"},
                {"id": "L2.confounding_shift", "value": _sig(m2["shift"]), "ref": a.encounters.get("confound"),
                 "meaning": "how far adjustment moved the log rate ratio, as a share of it"},
                {"id": "L2.non_human_share", "value": _sig(m2["tau"]), "ref": a.encounters.get("rodent"),
                 "meaning": "share of supporting papers that are animal or in vitro"}]
    if level > 3 and m3:
        out += [{"id": "L3.search_k", "value": m3["K"], "ref": a.encounters.get("sidak"),
                 "meaning": "outcome-and-subgroup combinations searched"},
                {"id": "L3.p_corrected", "value": _sig(m3["p_corr"]), "ref": a.encounters.get("sidak"),
                 "meaning": "Sidak-corrected p of the best combination searched"},
                {"id": "L3.sites_replicating", "value": len(m3["replicating"]), "ref": a.encounters.get("hlab"),
                 "meaning": f"EHR sites (of {len(m3['sites'])}) where the effect alone reached p < 0.05 in the claimed direction"},
                {"id": "L3.site_heterogeneity_p", "value": _sig(m3["heterogeneity"]["p"]), "ref": a.encounters.get("hlab"),
                 "meaning": "Cochran's Q p across sites (small: the sites disagree)"},
                {"id": "L3.completed_rcts", "value": m3["n_rct"], "ref": a.encounters.get("rct"),
                 "meaning": "completed randomized trials registered on this topic (results not assessed)"}]
    return out


# ---------------------------------------------------------------- the payload

def planning_payload(q, a, level: int, menu: dict) -> dict:
    """Everything the hero may see before choosing abilities for one scroll at one level."""
    c, s, st = q.c, a.scroll, a.st
    o = next(x for x in c.outcomes if x.key == st.outcome)
    tele = flags(raw_diagnostics(q.w, s, st))
    later = {k: {"cost": v["cost"], "level": v["level"]} for k, v in rules.ABILITIES.items() if v["level"] > level}
    payload = {
        "prompt_version": PROMPT_VERSION,
        "campaign": {"question": c.question, "drug": c.drug, "comparator": c.comparator, "population": c.population},
        "scroll": {"id": a.id, "title": s.title, "claim": s.claim, "outcome": o.label, "subgroup": st.subgroup,
                   "direction": "lowers the event" if st.direction < 0 else "raises the event",
                   "archetype": s.archetype, "found_in": s.origin, "search_k": st.K, "design": st.design},
        "level": {"number": level, "name": rules.LEVELS[level]["name"], "trap": rules.LEVELS[level]["trap"],
                  "damage_rule": rules.LEVELS[level]["rule"]},
        "resources": {"hp": a.hp, "credits": a.credits},
        "menu": {k: {"name": v["name"], "cost": v["cost"], "effect": v["effect"], "tradeoff": v["tradeoff"]}
                 for k, v in menu.items()},
        "later_abilities": later,
        "telemetry": tele,
        "released_findings": released(a, level),
        "concern_codes": rules.CONCERNS,
        "next_actions": rules.NEXT_ACTIONS,
    }
    assert_blinded(payload)
    return payload


def signal_ids(payload: dict) -> set[str]:
    """What a decision may cite: a telemetry flag name or a released finding id."""
    return set(TELEMETRY_SCHEMA) | {"data_quality_flags"} | {f["id"] for f in payload.get("released_findings", [])}


def resolve_citations(cited: list[str], payload: dict) -> tuple[list[str], list[str]]:
    """(citations as signal ids, citations that point at nothing the payload holds).

    A flag's VALUE counts as citing that flag only if the payload really holds that value: citing
    "EXPOSURE_LAG_DETECTED" means immortal_time_risk_flag when that is its value, and is rejected when it is not."""
    known = signal_ids(payload)
    tele = payload.get("telemetry", {})
    by_value = {v: k for k, v in tele.items() if isinstance(v, str)}
    by_value.update({q: "data_quality_flags" for q in tele.get("data_quality_flags", [])})
    out, unknown = [], []
    for c in cited:
        if c in known:
            out.append(c)
        elif c in by_value:
            out.append(by_value[c])
        else:
            unknown.append(c)
    return list(dict.fromkeys(out)), unknown


def assert_blinded(payload, path: str = "") -> None:
    """Refuse any payload with a forbidden field anywhere in it (keys are checked at every depth)."""
    if isinstance(payload, dict):
        for k, v in payload.items():
            low = str(k).lower()
            if any(f == low or low.startswith(f + "_") or low.endswith("_" + f) for f in FORBIDDEN):
                raise LeakError(f"forbidden field {path + '/' + str(k)!r} in a planning payload")
            assert_blinded(v, path + "/" + str(k))
    elif isinstance(payload, (list, tuple)):
        for i, v in enumerate(payload):
            assert_blinded(v, f"{path}[{i}]")


def public(payload: dict) -> dict:
    """What the ledger records of what the hero saw: the flags and the ids of the findings, never their numbers."""
    return {"prompt_version": payload["prompt_version"], "telemetry": payload["telemetry"],
            "released": [{"id": f["id"], "ref": f.get("ref")} for f in payload["released_findings"]]}

"""The scientific verdict on every claim, kept apart from the game: HP, credits, battles won and persona never decide it.

The rules (rules.STATUSES, fixed before any run) are applied in this order to numbers the Judge already measured:
  1. INVALID_ANALYSIS      the scroll reached the Citadel on a design with immortal time, or the Trial of Truth found
                           a predefined validity failure in its locked claim;
  2. SUPPORTED_ON_SYNTHETIC_VALIDATION
                           it passed rule 3 on the holdout AND the locked claim then beat the comparator again on a
                           never-opened sealed vault (an independent confirmation), in the claimed direction. A vault
                           success alone, after a holdout failure, is one unreplicated success: INCONCLUSIVE;
  3. PROVISIONALLY_SUPPORTED
                           it beat the comparator on the holdout (skill > margin), in the claimed direction, on a
                           time-zero design, with a Holm-adjusted p < 0.05 across every scroll of the quest, and the
                           sealed vault did not then fail it;
  4. CONTRADICTED          the Judge's reference analysis (new-user, adjusted, the claim's subgroup, training years)
                           has a 95% interval that excludes any important effect in the claimed direction
                           (rules.MIE_RR), including any interval wholly on the opposite side;
  5. INCONCLUSIVE          everything else: too weak or too imprecise to say. Not significant is not "no effect".
A shattered or withdrawn scroll can still be CONTRADICTED or INCONCLUSIVE: its claim was not adequately tested.
"""

from __future__ import annotations

import math

from . import judge as J
from . import rules


def guardian_p(a) -> float:
    """The scroll's p-value in the across-scrolls Holm family: its Guardian test if it is a valid, claimed-direction
    gain candidate, else 1 (it stays in the family: dropping it later would shrink the correction after the fact)."""
    m4 = a.m.get(4)
    if not m4 or a.st.design != "new_user" or m4.get("no_overlap") or not m4.get("direction_ok"):
        return 1.0
    return float(m4["p_dm"])


def contradiction(ref: dict, direction: int) -> str | None:
    """Does the reference interval rule the claim out? 'opposite', 'no important effect', or None."""
    delta = -math.log(rules.MIE_RR)        # the smallest important effect, on the log scale
    lo, hi = sorted((direction * ref["beta_lo"], direction * ref["beta_hi"]))
    if hi < 0:
        return "opposite"
    if hi < delta:
        return "no important effect"
    return None


def evaluate(q) -> dict:
    """Scientific status of every scroll. Returns {"scrolls": {id: row}, "family": ..., "best": id or None}."""
    t = q.trial or {}
    family = {a.id: guardian_p(a) for a in q.agents.values()}
    adjusted = J.holm(family)
    out = {}
    for a in q.agents.values():
        ref = J.reference_estimate(q.w, a.st.outcome, a.st.subgroup)
        why = contradiction(ref, a.st.direction)
        m4 = a.m.get(4) or {}
        holm_p = adjusted[a.id]
        provisional = (holm_p < rules.ALPHA and family[a.id] < 1.0 and (m4.get("ss_oos") or 0) > rules.SS_MARGIN)
        tried = t.get("evaluated") and t.get("scroll") == a.id
        reasons = []
        if 4 in a.m and a.st.design != "new_user":
            status = "INVALID_ANALYSIS"
            reasons.append("Reached the Citadel counting the wait before the first fill as treated time (immortal time).")
        elif tried and t.get("failures"):
            status = "INVALID_ANALYSIS"
            reasons += list(t["failures"])
        elif tried and t.get("gain") and t.get("independent") and provisional:
            status = "SUPPORTED_ON_SYNTHETIC_VALIDATION"
            reasons.append(f"Beat the comparator on the holdout (Holm-adjusted p {holm_p:.3g}) and again on a never-opened "
                           "sealed vault, in the claimed direction.")
        elif provisional and not (tried and not t.get("gain")):
            status = "PROVISIONALLY_SUPPORTED"
            reasons.append(f"Beat the comparator on the holdout; Holm-adjusted p {holm_p:.3g} across {len(family)} scrolls.")
            if tried and t.get("gain"):
                reasons.append(t.get("confirmation_label", "The vault result is not an independent confirmation."))
        elif why:
            status = "CONTRADICTED"
            reasons.append("The reference analysis rules out " + ("any effect in the claimed direction."
                           if why == "opposite" else f"an important effect (at least {round(100 * (1 - rules.MIE_RR))}%) "
                                                     "in the claimed direction."))
        else:
            status = "INCONCLUSIVE"
            if tried and t.get("gain"):
                reasons.append("The sealed vault showed a gain, but the claim had not first beaten the comparator on the "
                               "holdout: one unreplicated success is not support.")
            elif tried and not t.get("gain"):
                reasons.append("Did not beat the comparator on the sealed vault.")
            elif a.status == "withdrawn":
                reasons.append("Withdrawn by the hero before the Guardian.")
            elif a.status == "shattered":
                reasons.append("Shattered before its claim could be tested properly.")
            elif not provisional and family[a.id] < 1.0:
                reasons.append(f"Its holdout gain does not survive Holm across {len(family)} scrolls (adjusted p {holm_p:.3g}).")
            else:
                reasons.append("No valid gain over the comparator, and too imprecise to rule the claim out.")
        if why and status != "CONTRADICTED":
            reasons.append("Note: the reference analysis excludes an important effect in the claimed direction.")
        out[a.id] = {"id": a.id, "status": status, "reasons": reasons, "contradiction": why, "holm_p": holm_p,
                     "guardian_p": family[a.id], "family_size": len(family), "reference": ref,
                     "ss_oos": m4.get("ss_oos"), "direction": a.st.direction, "subgroup": a.st.subgroup,
                     "trial_outcome": t.get("outcome") if tried else None,
                     "confirmation_kind": t.get("vault_kind") if tried else None,
                     "spec_sha256": t.get("sha256") if tried else None, "game_status": a.status}
    order = {s: i for i, s in enumerate(rules.STATUS_ORDER)}
    best = min(out.values(), key=lambda r: (order[r["status"]], -(r["ss_oos"] if r["ss_oos"] is not None else -9), r["id"]))
    return {"scrolls": out, "family": {"kind": "Holm", "size": len(family), "alpha": rules.ALPHA,
                                       "members": list(family)},
            "best": best["id"] if best["status"] in ("SUPPORTED_ON_SYNTHETIC_VALIDATION", "PROVISIONALLY_SUPPORTED") else None,
            "best_status": best["status"], "mie_rr": rules.MIE_RR, "analysis_version": rules.ANALYSIS_VERSION}

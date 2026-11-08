"""Research state that outlives one quest: which synthetic cohorts and sealed vaults were used, and the champions.

VaultRegistry: one record per synthetic cohort (a campaign and a seed: World.fingerprint()). Live quests are each
given a cohort no quest has used (a fresh seed: new simulated patients from the same population, so a genuinely
unseen holdout and vault). The first Trial of Truth on a cohort is its one independent confirmation
(rules.VAULT_CONFIRMATIONS). A later evaluation on the same cohort is a REPLAY (the same locked spec) or a REUSE
(another spec): it may still refute a claim, it never confirms one, and it never adds an independent confirmation.
Each opening is written BEFORE the vault is read, so a crash mid-evaluation still counts as an opening.

ChampionStore: per research subject (a campaign: one drug, one comparator, one population), the best-supported claim
so far, with its immutable content, lineage, results, cohort fingerprints and source manifest. It changes only by the
predeclared rule in ChampionStore.settle(); historical HP is never a head start, and a synthetic champion is never
labelled clinically proven.

Both are JSON files written atomically (a temporary file, then a rename) under a lock; `path=None` keeps them in memory
(tests, the benchmark).
"""

from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path

from . import rules

_LOCKS: dict[str, threading.Lock] = {}
_GUARD = threading.Lock()
SUPPORTED = ("SUPPORTED_ON_SYNTHETIC_VALIDATION", "PROVISIONALLY_SUPPORTED")
CHAMPION_LABEL = "Best-supported claim in a simulated cohort. Not clinical evidence and not medical advice."


def _lock(path: Path | None) -> threading.Lock:
    key = str(path) if path else "memory"
    with _GUARD:
        return _LOCKS.setdefault(key, threading.Lock())


class _Store:
    def __init__(self, path: str | os.PathLike | None, empty: dict):
        self.path = Path(path) if path else None
        self._empty = empty
        self._mem = json.loads(json.dumps(empty))
        self.lock = _lock(self.path)

    def _read(self) -> dict:
        if self.path is None:
            return self._mem
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return json.loads(json.dumps(self._empty))

    def _write(self, data: dict) -> None:
        if self.path is None:
            self._mem = data
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(f".{os.getpid()}.{threading.get_ident()}.tmp")
        tmp.write_text(json.dumps(data, indent=1, sort_keys=True), encoding="utf-8")
        os.replace(tmp, self.path)   # atomic: readers see the old file or the new one, never half of one


class VaultRegistry(_Store):
    def __init__(self, path=None):
        super().__init__(path, {"cohorts": {}, "assigned": {}})

    def assign_seed(self, campaign_id: str, quest_id: str, first: int = 1) -> int:
        """A cohort no quest has used for this campaign. Seed 0 is the recorded demo's, published in the repository."""
        with self.lock:
            data = self._read()
            used = set(data["assigned"].get(campaign_id, [])) | {
                c["seed"] for c in data["cohorts"].values() if c["campaign"] == campaign_id}
            seed = first
            while seed in used:
                seed += 1
            data["assigned"].setdefault(campaign_id, []).append(seed)
            self._write(data)
            return seed

    def register(self, fingerprint: str, campaign_id: str, seed: int, quest_id: str) -> dict:
        """Record that a quest is about to use this cohort; say how often it was used before (holdout exposure)."""
        with self.lock:
            data = self._read()
            c = data["cohorts"].setdefault(fingerprint, {"campaign": campaign_id, "seed": seed, "quests": [],
                                                         "evaluations": []})
            before = len(c["quests"])
            c["quests"].append({"quest_id": quest_id, "at": time.time()})
            self._write(data)
            return {"fingerprint": fingerprint, "seed": seed, "quests_before": before, "fresh": before == 0,
                    "vault_opened_before": len(c["evaluations"])}

    def open_vault(self, fingerprint: str, campaign_id: str, seed: int, spec_sha: str, question_key: str,
                   quest_id: str) -> dict:
        """Log an opening of this cohort's sealed vault, before it is read. Returns whether it is independent."""
        with self.lock:
            data = self._read()
            c = data["cohorts"].setdefault(fingerprint, {"campaign": campaign_id, "seed": seed, "quests": [],
                                                         "evaluations": []})
            prior = c["evaluations"]
            independent_so_far = sum(e["kind"] == "NEW_INDEPENDENT" for e in prior)
            if any(e["spec_sha256"] == spec_sha for e in prior):
                kind = "REPLAY"
            elif independent_so_far < rules.VAULT_CONFIRMATIONS and not prior:
                kind = "NEW_INDEPENDENT"
            else:
                kind = "REUSE"
            ev = {"eval_id": f"V{len(prior) + 1:02d}", "kind": kind, "spec_sha256": spec_sha,
                  "question_key": question_key, "quest_id": quest_id, "at": time.time(), "outcome": None}
            prior.append(ev)
            self._write(data)
            return {"eval_id": ev["eval_id"], "kind": kind, "independent": kind == "NEW_INDEPENDENT",
                    "prior_evaluations": len(prior) - 1, "budget": rules.VAULT_CONFIRMATIONS,
                    "independent_used_before": independent_so_far,
                    "previous_outcomes": [e["outcome"] for e in prior[:-1] if e["spec_sha256"] == spec_sha]}

    def record_result(self, fingerprint: str, eval_id: str, outcome: str, gain: bool) -> None:
        with self.lock:
            data = self._read()
            for e in data["cohorts"].get(fingerprint, {}).get("evaluations", []):
                if e["eval_id"] == eval_id:
                    e.update(outcome=outcome, gain=bool(gain))
            self._write(data)

    def cohort(self, fingerprint: str) -> dict | None:
        with self.lock:
            return json.loads(json.dumps(self._read()["cohorts"].get(fingerprint)))


def confirmation_label(kind: str, gain: bool) -> str:
    return {("NEW_INDEPENDENT", True): "NEW INDEPENDENT CONFIRMATION",
            ("NEW_INDEPENDENT", False): "INDEPENDENT TEST: NOT CONFIRMED",
            ("REPLAY", True): "PRIOR VALIDATION - NO NEW INDEPENDENT CONFIRMATION",
            ("REPLAY", False): "REPLAY: NOT CONFIRMED",
            ("REUSE", True): "VAULT REUSED - NOT A NEW CONFIRMATION",
            ("REUSE", False): "VAULT REUSED: NOT CONFIRMED"}[(kind, bool(gain))]


class ChampionStore(_Store):
    def __init__(self, path=None):
        super().__init__(path, {"champions": {}})

    def get(self, subject: str) -> dict | None:
        with self.lock:
            rec = self._read()["champions"].get(subject)
            return json.loads(json.dumps(rec)) if rec else None

    def all(self) -> dict:
        with self.lock:
            return json.loads(json.dumps(self._read()["champions"]))

    def settle(self, subject: str, quest: dict) -> dict:
        """The predeclared promotion rule, applied once at the end of a quest.

        `quest` lists every scroll's scientific result this quest (science.py) and the incumbent's id, if any.
          * the best this quest = highest status, ties broken by holdout skill (one cohort, one metric);
          * no incumbent: a supported best is CROWNED, otherwise NO_CHAMPION;
          * a challenger replaces the incumbent only with a strictly higher status this quest (REPLACED);
          * a supported incumbent DEFENDED its title (a tie goes to the incumbent: no switch on noise);
          * an incumbent CONTRADICTED on the fresh cohort with no supported successor is DETHRONED;
          * anything else is UNRESOLVED: the old champion is kept, marked as not re-confirmed.
        Independent confirmations only ever come from a NEW_INDEPENDENT vault opening."""
        order = {s: i for i, s in enumerate(rules.STATUS_ORDER)}
        rows = quest["scrolls"]
        best = min(rows, key=lambda r: (order[r["status"]], -(r.get("ss_oos") or -9), r["id"])) if rows else None
        inc_id = quest.get("incumbent_id")
        inc = next((r for r in rows if r["id"] == inc_id), None)
        with self.lock:
            data = self._read()
            old = data["champions"].get(subject)
            now = time.strftime("%Y-%m-%d %H:%M:%S")
            if old is not None and inc is None:
                outcome = "NOT_CONTESTED"   # the champion was not in this quest, so this quest cannot change it
            elif old is None:
                if best is not None and best["status"] in SUPPORTED:
                    data["champions"][subject] = self._record(subject, best, quest, now, "CROWNED",
                                                              history=(old or {}).get("history", []))
                    outcome = "CROWNED"
                else:
                    outcome = "NO_CHAMPION"
            elif best is not None and best["id"] != inc["id"] and best["status"] in SUPPORTED \
                    and order[best["status"]] < order[inc["status"]]:
                hist = old.get("history", []) + [{"quest_id": quest["quest_id"], "event": "REPLACED", "at": now,
                                                  "status": inc["status"], "by": best["hypothesis"]["hypothesis_id"]}]
                data["champions"][subject] = self._record(subject, best, quest, now, "REPLACED", history=hist,
                                                          predecessor=old)
                outcome = "REPLACED"
            else:
                rec = old
                if inc["status"] in SUPPORTED:
                    outcome = "DEFENDED"
                elif inc["status"] == "CONTRADICTED":
                    outcome = "DETHRONED"
                else:
                    outcome = "UNRESOLVED"
                rec["history"] = rec.get("history", []) + [self._entry(inc, quest, now, outcome)]
                if inc.get("confirmation_kind") == "NEW_INDEPENDENT" and inc["status"] == "SUPPORTED_ON_SYNTHETIC_VALIDATION":
                    rec["confirmations"] = rec.get("confirmations", 0) + 1
                rec["last_result"] = self._entry(inc, quest, now, outcome)
                rec["status_now"] = inc["status"]
                if outcome == "DETHRONED":
                    data["champions"].pop(subject)
                    data.setdefault("retired", {}).setdefault(subject, []).append({**rec, "retired_at": now})
                else:
                    data["champions"][subject] = rec
            self._write(data)
            return {"outcome": outcome, "champion": json.loads(json.dumps(data["champions"].get(subject)))}

    @staticmethod
    def _entry(r: dict, quest: dict, now: str, event: str) -> dict:
        return {"quest_id": quest["quest_id"], "event": event, "at": now, "status": r["status"],
                "seed": quest["seed"], "world": quest["world"], "ss_oos": r.get("ss_oos"), "holm_p": r.get("holm_p"),
                "trial_outcome": r.get("trial_outcome"), "confirmation_kind": r.get("confirmation_kind"),
                "spec_sha256": r.get("spec_sha256"), "analysis_version": rules.ANALYSIS_VERSION}

    def _record(self, subject: str, r: dict, quest: dict, now: str, event: str, history: list,
                predecessor: dict | None = None) -> dict:
        independent = r.get("confirmation_kind") == "NEW_INDEPENDENT" and r["status"] == "SUPPORTED_ON_SYNTHETIC_VALIDATION"
        return {"subject": subject, "subject_label": quest.get("subject_label"), "hypothesis": r["hypothesis"],
                "status": r["status"], "status_now": r["status"], "confirmations": 1 if independent else 0,
                "since": now, "crowned_in": quest["quest_id"], "label": CHAMPION_LABEL,
                "last_result": self._entry(r, quest, now, event),
                "history": history + [self._entry(r, quest, now, event)],
                "manifest_ids": r.get("manifest_ids", []),
                "predecessor": (predecessor or {}).get("hypothesis")}

"""The Hypothesis Gauntlet: hypothesis agents walk four levels of evidence.

The party moves together: every hero faces a level's enemies, then the level closes
(the Temple ends with the Publication Bias Knight counting every claim tried), then
the portal opens. Agents choose, the checks measure, the rules in rules.py decide HP.
"""

import hashlib
import time
from collections import Counter

import pandas as pd

from ..arena import decoys, engine
from ..arena.features import default_registry, public_catalog, register
from ..arena.ledger import Ledger, preregister
from ..arena.models import Gladiator
from ..arena.orchestrator import _round
from . import checks, report, rules
from .agents import ScriptedResearcher, ScriptedSkeptic
from .models import Hero, QuestEvent

DECOY_DIRECTIONS = {decoys.NOISE: "negative", decoys.LUCKY: "either",
                    decoys.LEAK: "positive", decoys.COPYCAT: "positive"}
DECOY_NAMES = [decoys.NOISE, decoys.LUCKY, decoys.LEAK, decoys.COPYCAT]


class QuestStopped(Exception):
    """Raised inside the quest thread once someone leaves the game screen."""


class Gauntlet:
    def __init__(self, run_id: str, train: pd.DataFrame, test: pd.DataFrame | None = None,
                 sensors: dict[str, pd.DataFrame] | None = None, researcher=None, skeptic=None,
                 ledger: Ledger | None = None, hypotheses: list[dict] | None = None,
                 with_decoys: bool = True, max_heroes: int = 8, seed: int = 0,
                 n_perm: int = 200, n_boot: int = 500, pace: float = 0.0,
                 runs_dir: str = "data/quests", target: str = "rise", question: str = rules.DEFAULT_QUESTION,
                 theories: list[str] | None = None, sources: dict | None = None):
        self.run_id, self.seed, self.n_perm, self.n_boot = run_id, seed, n_perm, n_boot
        self.pace, self.target, self.max_heroes = pace, target, max_heroes
        self.hypotheses, self.with_decoys = hypotheses, with_decoys
        self.question, self.theories = question, [t for t in (theories or []) if t.strip()]
        self.sources = {"discovery": "discovery set", "holdout": "independent holdout", "synthetic": False,
                        **(sources or {})}
        self.versions = {"discovery": _version(train), "holdout": _version(test)}
        self._encounters = 0
        self.researcher = researcher or ScriptedResearcher()
        self.skeptic = skeptic or ScriptedSkeptic()
        self.ledger = ledger or Ledger(run_id, runs_dir, model=QuestEvent)

        self.registry = default_registry()
        if with_decoys:
            for f in decoys.DECOY_FEATURES:
                if f.name != decoys.EMPEROR:
                    self.registry = register(self.registry, f)
            plan = decoys.plan(train, target, None, seed)
            train = decoys.attach(train, target, plan, salt=0)
            sensors = {k: decoys.attach(v, target, plan, like=train) for k, v in (sensors or {}).items()}
            test = None if test is None else decoys.attach(test, target, plan, salt=1)
        self.train, self.test, self.sensors = train, test, sensors or {}
        self.heroes: dict[str, Hero] = {}
        self.decoy_ids: dict[str, str] = {}
        self.level = 0
        self._calls = 0
        self._stop = False
        self._announced: set[str] = set()

    # ---------- the whole quest ----------

    def run(self) -> dict | None:
        try:
            self.recruit()
            for level in (1, 2, 3, 4):
                self.play_level(level)
            return self.finale()
        except QuestStopped:
            self.ledger.write(level=self.level, actor="system", action="stopped",
                              line="The player left the gauntlet, so the quest was stopped.")
            return None
        except Exception as e:  # never end silently: say what broke
            self._emit(actor="system", action="error", line=f"The quest was halted: {e!r}"[:300])
            return None

    def recruit(self) -> None:
        catalog = [f for f in public_catalog(self.registry, 3, set(self.train.columns))
                   if f["name"] not in {d.name for d in decoys.DECOY_FEATURES}]
        if self.hypotheses is not None:
            proposals = [Gladiator(id="new", claim=h["claim"], add_features=list(h["add_features"]),
                                   expected_direction=h.get("expected_direction", "either"))
                         for h in self.hypotheses]
        else:
            proposals = self.researcher.propose(catalog, self.max_heroes)
            self._check_fallback(self.researcher, "Researcher")
        self._emit(actor="system", action="quest_start",
                   result={"question": self.question, "sources": self.sources, "versions": self.versions,
                           "levels": rules.LEVELS, "starting_hp": rules.STARTING_HP,
                           "starting_credits": rules.STARTING_CREDITS, "pass_heal": rules.PASS_HEAL,
                           "concede_damage": rules.CONCEDE_DAMAGE, "score_components": rules.SCORE_COMPONENTS,
                           "hp_bonus": rules.HP_BONUS,
                           "verdicts": rules.VERDICTS, "abilities": rules.ABILITIES,
                           "encounters": {k: {f: v[f] for f in ("level", "name", "kind", "cost", "ability",
                                                                 "test", "damage", "damage_severe", "head")
                                              if f in v} for k, v in rules.ENCOUNTERS.items()}},
                   line="AI scientists enter a dungeon of conflicting evidence.")
        allowed = {f["name"] for f in catalog}
        for g in proposals[: self.max_heroes]:
            adds = [f for f in dict.fromkeys(g.add_features) if f != "carbs"][:2] or ["carbs"]
            if any(f not in allowed for f in adds) or any(set(adds) == set(h.gladiator.add_features)
                                                          for h in self.heroes.values()):
                self._emit(actor="judge", action="rejected",
                           line=f"Turned away at the gate: {g.claim[:80]} (unknown or repeated evidence).")
                continue
            self._add_hero(g.model_copy(update={"add_features": adds}))
        for text in self.theories:
            g = self.researcher.lanista.theory(text, catalog)
            if g is None:
                self._emit(actor="judge", action="rejected",
                           line=f"Your hypothesis \"{text[:80]}\" uses no evidence this dataset measures.")
                continue
            adds = [f for f in dict.fromkeys(g.add_features) if f != "carbs"][:2] or ["carbs"]
            if any(f not in allowed for f in adds):
                continue
            self._add_hero(g.model_copy(update={"add_features": adds, "origin": "crowd",
                                                "claim": text.strip()[:140]}))
        if self.with_decoys:
            for name in DECOY_NAMES:
                if name in self.train.columns:
                    h = self._add_hero(Gladiator(id="new", claim=decoys.CLAIMS[name], add_features=[name],
                                                 expected_direction=DECOY_DIRECTIONS[name], origin="decoy"))
                    self.decoy_ids[h.id] = name

    def _add_hero(self, g: Gladiator) -> Hero:
        i = len(self.heroes)
        baseline = [] if g.add_features == ["carbs"] else ["carbs"]
        g = g.model_copy(update={"id": f"H{i + 1:02d}", "baseline_features": baseline, "target": self.target})
        h = Hero(id=g.id, name=rules.NAMES[i % len(rules.NAMES)],
                 cls=rules.CLASS_BY_FEATURE.get(g.add_features[0], "Wanderer"), gladiator=g)
        self.heroes[h.id] = h
        self._emit(actor="researcher", action="recruit", hero=h, agent=h.public(),
                   line=f"{h.name} the {h.cls} claims: {g.claim}")
        return h

    def play_level(self, level: int) -> None:
        self.level = level
        info = rules.LEVELS[level]
        self._emit(actor="system", action="level_start", result=info, line=f"Level {level}: {info['name']}")
        for h in self.questing():
            options = [k for k in rules.LEVEL_ORDER[level] if rules.ENCOUNTERS[k]["kind"] == "challenge"
                       and (k != "wraith" or len(self.sensors) >= 2)]
            picks, line = self.skeptic.challenges(h, level, options)
            self._check_fallback(self.skeptic, "Skeptic")
            picks = [p for p in picks if p in options][: rules.SKEPTIC_CHALLENGES_PER_LEVEL]
            self._emit(actor="skeptic", action="plan", hero=h, result={"challenges": picks}, line=line)
            for key in rules.LEVEL_ORDER[level]:
                if rules.ENCOUNTERS[key]["kind"] == "challenge" and key not in picks:
                    continue
                self.encounter(h, key)
                if not h.questing:
                    break
            if level == 1 and h.questing and "raw_direction" in h.results:
                self._maybe_revise(h)
        if level == 3:
            self.knight()
        cleared = []
        for h in self.questing():
            h.levels_cleared += 1
            cleared.append(h.id)
        heroes = list(self.heroes.values())
        for h in heroes:
            if h.questing or h.id in cleared or level not in h.hp_by_level:
                h.hp_by_level[level] = h.hp
        alive = [h for h in heroes if h.questing]
        leader = max(alive, key=report.score, default=None)
        self._emit(actor="system", action="level_complete",
                   result={"level": level, "name": info["name"], "cleared": cleared,
                           "heroes": [h.card() for h in heroes],
                           "rows": report.level_rows(heroes, level),
                           "most_damaging": report.most_damaging_enemy(heroes, level),
                           "leader": leader and {"id": leader.id, "name": leader.name, "score": report.score(leader),
                                                 "claim": leader.gladiator.claim}},
                   line=f"Level complete: {info['name']}. {len(cleared)} of {len(self.heroes)} still standing.")

    def questing(self) -> list[Hero]:
        return [h for h in self.heroes.values() if h.questing]

    # ---------- one fight ----------

    def encounter(self, h: Hero, key: str) -> None:
        enc = rules.ENCOUNTERS[key]
        self._emit(actor="judge" if enc["kind"] == "gate" else "skeptic", action="encounter", hero=h,
                   enemy=key, ability=enc["ability"], test=enc["test"], cost=enc["cost"],
                   line=f"{enc.get('head') or enc['name']}: \"{enc['attack']}\"")
        if enc["kind"] == "challenge":
            defend, line = self.researcher.defend(h, key, self._reserve(h, key))
            self._check_fallback(self.researcher, "Researcher")
            if not defend:
                self._change_hp(h, -rules.CONCEDE_DAMAGE)
                h.conceded += 1
                h.history.append({"level": self.level, "enemy": key, "test": None, "passed": None,
                                  "hp_delta": -rules.CONCEDE_DAMAGE})
                explain = "Skipping a check saves credits, but the claim stays unverified."
                self._emit(actor="agent", action="concede", hero=h, enemy=key,
                           hp_delta=-rules.CONCEDE_DAMAGE, line=line, explain=explain,
                           encounter=self._record(h, key, None, "CONCEDED", -rules.CONCEDE_DAMAGE, explain))
                self._check_fall(h, key)
                return
            self._emit(actor="agent", action="defend", hero=h, enemy=key, ability=enc["ability"], line=line)
        if enc["cost"] > h.credits:
            h.status, h.verdict = "unproven", "UNPROVEN"
            self._emit(actor="judge", action="broke", hero=h, enemy=key,
                       line=f"{h.name} cannot pay {enc['cost']} credits for this test.",
                       explain=rules.VERDICTS["UNPROVEN"])
            return
        h.credits -= enc["cost"]
        h.spent += enc["cost"]
        result = self._run(h, enc["test"])
        h.results[enc["test"]] = result
        self._resolve(h, key, result)

    def _resolve(self, h: Hero, key: str, result: dict) -> None:
        enc = rules.ENCOUNTERS[key]
        if result.get("untestable"):
            if enc["kind"] == "challenge":  # nothing to check: refund, no harm
                h.credits += enc["cost"]
                h.spent -= enc["cost"]
            delta = 0
        else:
            h.attempted += 1
            trial = h.results.get("added_value")
            if enc["kind"] == "challenge" and trial is not None and not trial.get("passed") and enc["level"] >= 2 \
                    and key != "phantom":
                h.redundant += 1
            if result["passed"]:
                h.passed_checks += 1
                delta = rules.PASS_HEAL
            else:
                h.failed_checks += 1
                delta = -(enc.get("damage_severe", enc["damage"]) if result.get("severe") else enc["damage"])
        delta = self._change_hp(h, delta)
        h.history.append({"level": self.level, "enemy": key, "test": enc["test"],
                          "passed": result.get("passed"), "hp_delta": delta})
        line, explain = describe(enc["test"], result, h)
        verdict = "UNTESTABLE" if result.get("untestable") else ("PASS" if result["passed"] else "FAIL")
        rec = self._record(h, key, _round(result), verdict, delta, explain)
        h.encounter_ids[enc["test"]] = rec["encounter_id"]
        self._emit(actor="judge", action="result", hero=h, enemy=key, ability=enc["ability"],
                   test=enc["test"], result=_round(result), passed=result.get("passed"),
                   hp_delta=delta, line=line, explain=explain, encounter=rec)
        if result.get("untestable") and enc["kind"] == "gate":
            h.status, h.verdict = "untestable", "UNTESTABLE"
            self._emit(actor="judge", action="exit", hero=h,
                       line=f"{h.name} leaves the gauntlet: UNTESTABLE.", explain=rules.VERDICTS["UNTESTABLE"])
            return
        self._check_fall(h, key)

    def _run(self, h: Hero, test: str) -> dict:
        g, seed = h.gladiator, self._seed()
        r = h.results
        if test == "coverage":
            return checks.coverage(self.train, g)
        if test == "raw_direction":
            return checks.raw_direction(self.train, g, self.n_boot, seed)
        if test == "within_person":
            return checks.within_person(self.train, g)
        if test == "echo":
            return checks.echo(self.train, g)
        if test == "added_value":
            return engine.added_value(self.train, g, self.n_boot, seed)
        if test in ("majority_benefit", "trimmed_gain"):
            if "_gains" not in r:
                r["_gains"] = {"by_person": checks.person_gains(self.train, g).to_dict()}
            gains = pd.Series(r["_gains"]["by_person"])
            return checks.majority_benefit(gains) if test == "majority_benefit" else checks.trimmed_gain(gains)
        if test == "confounding":
            if "raw_direction" not in r or "added_value" not in r or r["added_value"].get("untestable"):
                return {"passed": False, "untestable": True, "reason": "needs the raw and adjusted results"}
            return checks.confounding(r["raw_direction"], r["added_value"])
        if test == "too_good":
            if r.get("added_value", {}).get("untestable", True):
                return {"passed": False, "untestable": True, "reason": "needs the Trial result"}
            return checks.too_good(r["added_value"])
        if test == "fold_replication":
            return checks.fold_replication(self.train, g)
        if test == "sensor_check":
            return engine.sensor_check(self.sensors, g, seed=seed)
        if test == "shuffle_test":
            return engine.shuffle_test(self.train, g, self.n_perm, seed)
        if test == "temporal":
            return checks.temporal(g, self.registry)
        if test == "leak_audit":
            return engine.leak_audit(g, self.registry)
        if test == "provenance":
            return checks.provenance(self.test, g)
        if test == "final_boss":
            h.prereg_hash = preregister(g)
            self._emit(actor="agent", action="prereg", hero=h, ability="preregister",
                       line=f"Preregister! Claim locked before the final test: {h.prereg_hash[:12]}",
                       explain="The claim can no longer be tweaked to fit the unseen data.")
            return engine.final_boss(self.train, self.test, g, self.n_boot, seed)
        raise ValueError(f"unknown test {test}")

    def knight(self) -> None:
        """Publication Bias Knight: Benjamini-Hochberg over every claim judged so far."""
        pvalues = {}
        for hid, h in self.heroes.items():
            if "shuffle_test" in h.results:
                pvalues[hid] = h.results["shuffle_test"]["p"]
            elif "added_value" in h.results and not h.results["added_value"].get("untestable"):
                pvalues[hid] = 1.0  # tried but never shuffled: still counts as a try
        if not pvalues:
            return
        verdicts = engine.penalty(pvalues)
        self._emit(actor="judge", action="census", enemy="knight",
                   line=f"The Publication Bias Knight counts {len(pvalues)} claims tried. "
                        "The more you try, the higher the bar.")
        for hid, res in verdicts.items():
            h = self.heroes[hid]
            if h.questing:
                self.encounter_result(h, "knight", res)

    def encounter_result(self, h: Hero, key: str, result: dict) -> None:
        enc = rules.ENCOUNTERS[key]
        self._emit(actor="judge", action="encounter", hero=h, enemy=key, ability=enc["ability"],
                   test=enc["test"], cost=0, line=f"{enc['name']}: \"{enc['attack']}\"")
        h.results[enc["test"]] = result
        self._resolve(h, key, result)

    def _maybe_revise(self, h: Hero) -> None:
        ok, line = self.researcher.revise(h, h.results["raw_direction"], self._reserve(h, None))
        if not ok:
            return
        g = h.gladiator
        flipped = {"positive": "negative", "negative": "positive"}.get(g.expected_direction, g.expected_direction)
        h.gladiator = g.model_copy(update={"expected_direction": flipped,
                                           "claim": f"{g.claim} (revised: the effect is {flipped})"})
        h.credits -= rules.REVISE_COST
        h.spent += rules.REVISE_COST
        h.revised = True
        self._emit(actor="researcher", action="revise", hero=h, agent=h.public(), line=line,
                   explain="Changing your mind when the data disagrees is good science, but it costs a credit.")

    # ---------- the end ----------

    def finale(self) -> dict:
        heroes = list(self.heroes.values())
        for h in heroes:
            if h.questing:
                h.verdict = self._verdict(h)
        rows = []
        for h in heroes:
            comp = report.score_components(h)
            rows.append({**h.card(), "cls": h.cls, "claim": h.gladiator.claim, "score": report.score(h),
                         "components": comp, "levels_cleared": h.levels_cleared,
                         "decoy": self.decoy_ids.get(h.id), "crowd": h.gladiator.origin == "crowd",
                         "hp_by_level": h.hp_by_level, "history": h.history,
                         "damage": report.damage_by_weakness([h])})
        rows.sort(key=lambda r: (r["verdict"] != "VALIDATED", -r["score"],
                                 -report.tiebreak(self.heroes[r["id"]])))
        validated = [r for r in rows if r["verdict"] == "VALIDATED"]
        champ_row = validated[0] if validated else None
        champion = self.heroes[champ_row["id"]] if champ_row else None
        decoy_rows = [{"id": r["id"], "name": r["name"], "decoy": r["decoy"], "verdict": r["verdict"],
                       "caught": r["verdict"] != "VALIDATED"} for r in rows if r["decoy"]]
        if champion:
            champ_row["why"] = report.why_ranked(champion, champ_row["components"], rows)
            conclusion = (f"{champion.name} the {champion.cls} emerges with the most defensible result: "
                          f"\"{champion.gladiator.claim}\".")
        else:
            conclusion = ("Inconclusive. No hypothesis survived every validation step, so the gauntlet "
                          "names no winner.")
        result = {
            "question": self.question, "sources": self.sources,
            "ranking": rows, "validated": len(validated), "best": champion and champion.id,
            "champion": champ_row and {**champ_row,
                                       "contributions": report.contributions(champion, self.sources)},
            "decoys": decoy_rows, "caught": sum(d["caught"] for d in decoy_rows),
            "verdicts": dict(Counter(r["verdict"] for r in rows)),
            "damage": report.damage_by_weakness(heroes),
            "consensus": report.consensus(self.question, champion, heroes, self.decoy_ids, self.sources),
            "score_components": rules.SCORE_COMPONENTS,
            "totals": {
                "tests_attempted": sum(r["attempted"] for r in rows),
                "credits_spent": sum(r["spent"] for r in rows),
                "invalid_claims_detected": sum(r["failed"] for r in rows),
                "useful_evidence": sum(r["passed"] for r in rows),
                "redundant": sum(r["redundant"] for r in rows),
                "conceded": sum(r["conceded"] for r in rows),
            },
            "conclusion": conclusion,
        }
        self.level = 5
        self._emit(actor="system", action="finale", result=result, line=conclusion)
        return result

    def _verdict(self, h: Hero) -> str:
        r = h.results
        if r.get("temporal", {}).get("passed") is False:
            return "LOOK-AHEAD"
        if r.get("final_boss", {}).get("untestable"):
            return "UNTESTABLE"
        if all(r.get(t, {}).get("passed") for t in rules.VALIDATION):
            return "VALIDATED"
        return "UNSUPPORTED"

    # ---------- internals ----------

    def _reserve(self, h: Hero, key: str | None) -> int:
        """Credits still needed for this hero's mandatory tests after `key` in the quest."""
        order = [k for lvl in (1, 2, 3, 4) for k in rules.LEVEL_ORDER[lvl]]
        start = order.index(key) + 1 if key else order.index(rules.LEVEL_ORDER[self.level][-1]) + 1
        return sum(rules.ENCOUNTERS[k]["cost"] for k in order[start:] if rules.ENCOUNTERS[k]["kind"] == "gate")

    def _record(self, h: Hero, key: str, numbers: dict | None, verdict: str, delta: int, explain: str) -> dict:
        """The structured encounter record (spec section 12), written into the ledger."""
        self._encounters += 1
        enc = rules.ENCOUNTERS[key]
        holdout = enc["test"] in ("final_boss", "provenance")
        return {
            "encounter_id": f"E{self._encounters:03d}", "level": self.level, "agent_id": h.id,
            "hypothesis_id": _version(h.gladiator.model_dump(), 10),
            "evidence_source": self.sources["holdout" if holdout else "discovery"],
            "evidence_version": self.versions["holdout" if holdout else "discovery"],
            "enemy_type": key, "research_action": enc["ability"] if numbers is not None else "concede",
            "test_requested": enc["test"], "numerical_result": numbers, "methodological_verdict": verdict,
            "hp_change": delta, "explanation": explain, "timestamp": time.time(),
        }

    def _change_hp(self, h: Hero, delta: int) -> int:
        new = max(0, min(rules.STARTING_HP, h.hp + delta))
        delta, h.hp = new - h.hp, new
        return delta

    def _check_fall(self, h: Hero, key: str) -> None:
        if h.hp <= 0 and h.questing:
            h.status, h.verdict = "fallen", "FALLEN"
            enc = rules.ENCOUNTERS[key]
            self._emit(actor="judge", action="fall", hero=h, enemy=key,
                       line=f"{h.name} falls to {enc.get('head') or enc['name']}!",
                       explain=rules.VERDICTS["FALLEN"])

    def _check_fallback(self, agent, role: str) -> None:
        if getattr(agent, "fallbacks", 0) and role not in self._announced:
            self._announced.add(role)
            self._emit(actor="system", action="fallback",
                       line=f"Claude isn't answering as the {role}. The scripted {role} takes over.")

    def _seed(self) -> int:
        self._calls += 1
        return self.seed + self._calls

    def stop(self) -> None:
        """Ask the quest to end; it stops at its next ledger write (an in-flight Claude call finishes first)."""
        self._stop = True

    def _emit(self, hero: Hero | None = None, **fields) -> None:
        if self._stop:
            raise QuestStopped
        if hero is not None:
            fields.setdefault("agent_id", hero.id)
            fields.update(hp=hero.hp, credits=hero.credits, status=hero.status, verdict=hero.verdict)
        self.ledger.write(level=self.level, **fields)
        if self.pace:
            time.sleep(self.pace)


def _version(obj, n: int = 8) -> str:
    """A short fingerprint of a dataset (or claim), so every record says which data it used."""
    if obj is None:
        return "none"
    if isinstance(obj, pd.DataFrame):
        blob = f"{obj.shape}|{','.join(map(str, obj.columns))}|{pd.util.hash_pandas_object(obj, index=False).sum()}"
    else:
        blob = repr(sorted(obj.items()) if isinstance(obj, dict) else obj)
    return hashlib.sha256(blob.encode()).hexdigest()[:n]


def _pm(x: float) -> str:
    return f"{x:+.2f}"


def describe(test: str, r: dict, h: Hero) -> tuple[str, str]:
    """(what the test found, with numbers; the same in plain English). Deterministic."""
    f = ", ".join(h.gladiator.add_features)
    if r.get("untestable"):
        return f"Cannot be judged: {r.get('reason', 'not enough data')}.", \
            "With too little data, nobody can say if this is true or false."
    ok = r["passed"]
    if test == "coverage":
        return f"Measured for {r['n_participants']} people.", "There is enough data to put this claim to the test."
    if test == "raw_direction":
        line = f"Raw link between {r['feature']} and the rise: r = {_pm(r['r'])} (95% CI {_pm(r['ci_low'])} to {_pm(r['ci_high'])})."
        if ok:
            return line, "The raw data leans the way the rumour says. Interesting, but a pattern is not proof yet."
        if r["contradicted"]:
            return line, "The raw data points the opposite way to the claim. Popularity was not evidence."
        return line, "The raw data does not clearly lean either way. The claim is popular, not supported."
    if test == "within_person":
        line = f"The pattern holds within {r['share_agree']:.0%} of {r['n_participants']} people's own meals."
        return line, ("It holds for most individuals, not just one anecdote." if ok
                      else "For most people it does not hold. One person's story is not a rule.")
    if test == "echo":
        if "note" in r:
            return "Nothing to echo.", "This claim is the baseline itself."
        line = f"Overlap with the baseline: |r| = {r['max_abs_r']:.2f}."
        return line, ("It brings something carbs do not already say." if ok
                      else "This claim mostly repeats carbs in a different costume.")
    if test == "added_value":
        line = (f"Adding {f} changes prediction error by {_pm(r['gain'])} mg/dL per meal "
                f"(95% CI {_pm(r['ci_low'])} to {_pm(r['ci_high'])}) across {r['n_participants']} people.")
        if ok:
            return line, "Predictions for people left out of fitting improve, and the whole range is above zero."
        extra = " It correlates on its own, but adds nothing beyond carbs." if r.get("standalone_r", 0) >= 0.15 else ""
        return line, "The improvement could be zero: the uncertainty range includes no gain at all." + extra
    if test == "majority_benefit":
        line = f"{r['share_benefit']:.0%} of {r['n_participants']} people are predicted better."
        return line, ("Most people benefit, not just a lucky few." if ok
                      else "Most people are not helped. The average is carried by a few.")
    if test == "confounding":
        line = f"Raw direction: {r['raw']}. After accounting for carbs: {r['adjusted'] or 'none'}."
        return line, ("The direction survives adjusting for carbs." if ok
                      else "The direction flips once carbs are considered: the raw pattern was really carbs.")
    if test == "too_good":
        line = f"The gain is {r['share_of_error']:.0%} of the baseline error."
        return line, ("A plausible size for a real effect." if ok
                      else "Suspiciously large. Results this good often mean the evidence peeks at the answer.")
    if test == "fold_replication":
        line = f"Replicated in {r['replicated']} of {r['n_groups']} independent groups of people."
        return line, ("It works in groups of people it was never fitted on." if ok
                      else "It fails to replicate in most independent groups.")
    if test == "sensor_check":
        parts = ", ".join(f"{k} {_pm(v)}" for k, v in r["by_sensor"].items() if v is not None)
        return f"By sensor: {parts} mg/dL per meal.", ("Both sensors agree." if ok else "The sensors disagree.")
    if test == "shuffle_test":
        line = f"{r['beaten_by']} of {r['n_perm']} scrambled copies did as well (p = {r['p']:.3f})."
        return line, ("The real data beat almost every scrambled copy: unlikely to be luck." if ok
                      else "Meaningless scrambled versions did about as well. This could be luck.")
    if test == "trimmed_gain":
        line = f"Without the top {r['dropped']} contributors, the gain is {_pm(r['trimmed_gain'])}."
        return line, ("It holds without its best cases." if ok
                      else "Remove a few best cases and the effect disappears.")
    if test == "penalty":
        line = f"{r['m']} claims tried; corrected p = {r['p_adj']:.3f}."
        return line, ("Even counting every claim tried, this one stands out." if ok
                      else "Try enough claims and one looks good by chance. Counting every try, this one does not stand out.")
    if test == "temporal":
        if ok:
            return "Every feature is known at mealtime.", "No peeking at the future."
        return (f"{', '.join(r['after_meal'])} is only known after the meal.",
                "Using information from the future is cheating, however accurate it looks.")
    if test == "leak_audit":
        if ok:
            return "Nothing here is built from the outcome.", "The evidence is independent of the answer."
        return (f"{', '.join(r['leaky'] or r['unknown'])} is built from the glucose rise itself!",
                "Evidence made from the answer always looks perfect. It is worthless.")
    if test == "provenance":
        return (f"Recorded for {r['n_participants']} people in the independent dataset "
                f"({r['missing_share']:.0%} of meals missing it)."), \
            "Official records still need checking: they cover this claim well enough to test it."
    if test == "final_boss":
        line = (f"On {r['n_participants']} never-seen people: {_pm(r['gain'])} mg/dL per meal "
                f"(95% CI {_pm(r['ci_low'])} to {_pm(r['ci_high'])}).")
        return line, ("It beats the baseline on people it has never seen. A defensible discovery." if ok
                      else "It does not beat the baseline on new people. It looked good only where it was found.")
    return ("Passed." if ok else "Failed."), ""

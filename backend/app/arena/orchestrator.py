"""The arena: runs the five days, enforces budget and reputation, writes the ledger.

Plain Python. Agents choose, the engine measures, the referee rules.
"""

import time
from collections import Counter

import pandas as pd

from . import config, decoys, engine, referee
from .agents import Lanista, ScriptedLanista, ScriptedSceptic, Sceptic
from .features import Feature, default_registry, public_catalog, register
from .ledger import Ledger, preregister
from .models import Gladiator, GladiatorState

ARENA_TESTS = ("leak_audit", "shuffle_test", "sensor_check")


class Arena:
    def __init__(self, run_id: str, train: pd.DataFrame, test: pd.DataFrame | None = None,
                 sensors: dict[str, pd.DataFrame] | None = None,
                 lanista: Lanista | None = None, sceptic: Sceptic | None = None,
                 ledger: Ledger | None = None, emperor: str | None = None, seed: int = 0,
                 n_perm: int = config.N_PERM, n_boot: int = config.N_BOOT,
                 target: str = "rise", k: int = 5, pace: float = 0.0, runs_dir: str = "data/runs"):
        self.run_id, self.target, self.k, self.pace, self.seed = run_id, target, k, pace, seed
        self.n_perm, self.n_boot = n_perm, n_boot
        self.lanista = lanista or ScriptedLanista()
        self.sceptic = sceptic or ScriptedSceptic()
        self.ledger = ledger or Ledger(run_id, runs_dir)

        self.registry: dict[str, Feature] = default_registry()
        for f in decoys.DECOY_FEATURES:
            if f.name != decoys.EMPEROR or emperor:
                self.registry = register(self.registry, f)
        self.decoy_plan = decoys.plan(train, target, emperor, seed)
        self.train = decoys.attach(train, target, self.decoy_plan, salt=0)
        self.sensors = {name: decoys.attach(f, target, self.decoy_plan, like=self.train)
                        for name, f in (sensors or {}).items()}
        self.test = None if test is None else decoys.attach(test, target, self.decoy_plan, salt=1)

        self.reputation = config.STARTING_REPUTATION
        self.denarii = config.STARTING_DENARII
        self.states: dict[str, GladiatorState] = {}
        self.day = 0
        self.banished = False
        self._settled: set[str] = set()
        self._calls = 0

    # ---------- running a whole game ----------

    def run(self) -> None:
        try:
            for day in (1, 2, 3):
                self.play_day(day)
                if self.banished:
                    break
            if not self.banished:
                self.decoy_games()
            if not self.banished:
                self.champion_day()
        except Exception as e:  # never end a game silently: say what broke, then sum up
            self._emit(actor="system", action="error", line=f"The games were halted: {e!r}"[:300])
        self.summary()

    def play_day(self, day: int) -> None:
        self._start_day(day)
        catalog = [f for f in public_catalog(self.registry, day, set(self.train.columns))
                   if f["name"] not in {d.name for d in decoys.DECOY_FEATURES}]
        for g in self.lanista.propose(day, catalog, self.graveyard(), self.k)[: self.k]:
            g = self._validate(g, day, catalog)
            if g is not None:
                self.enter(g)
            if self.banished:
                return
        self.census()

    def decoy_games(self) -> None:
        self._start_day(4)
        names = [decoys.NOISE, decoys.LUCKY, decoys.LEAK, decoys.COPYCAT]
        if self.decoy_plan.emperor:
            names.append(decoys.EMPEROR)
        for name in names:
            origin = "emperor" if name == decoys.EMPEROR else "decoy"
            self.enter(Gladiator(id="new", claim=decoys.CLAIMS[name], add_features=[name],
                                 day=4, origin=origin), actor="emperor")
            if self.banished:
                return
        self.census()

    def champion_day(self) -> None:
        self._start_day(5)
        if self.test is None:
            self._emit(actor="system", action="no_holdout", line="No holdout data loaded.")
            return
        for s in [s for s in self.states.values() if s.status == "survivor"]:
            s.prereg_hash = preregister(s.gladiator)
            self._emit(actor="system", action="prereg", state=s,
                       line=f"Locked before the fight: {s.prereg_hash[:12]}")
            if not self._pay("final_boss", s):
                continue
            result = engine.final_boss(self.train, self.test, s.gladiator, self.n_boot, self._seed())
            self._record(s, "final_boss", result)

    # ---------- one gladiator ----------

    def enter(self, g: Gladiator, actor: str = "lanista", auto_back: bool | None = None) -> GladiatorState:
        update = {"id": f"G{len(self.states) + 1:02d}", "day": self.day or g.day,
                  "baseline_features": self._baseline(self.day or g.day)}
        if decoys.EMPEROR in g.add_features:
            update["target"] = decoys.EMPEROR_TARGET
        g = g.model_copy(update=update)
        s = GladiatorState(gladiator=g)
        self.states[g.id] = s
        self._emit(actor=actor, action="propose", state=s, gladiator=g.model_dump(), line=g.claim)
        if not self._pay("added_value", s):
            return s
        self._record(s, "added_value", engine.added_value(self.train, g, self.n_boot, self._seed()))
        if not s.alive:
            return s
        back, line = (auto_back, "") if auto_back is not None else self.lanista.decide(s)
        s.backed = bool(back)
        if not s.backed:
            s.status, s.verdict = "dropped", "DROPPED"
            self._emit(actor="lanista", action="drop", state=s, line=line or "Dropped.")
            return s
        s.status = "arena"
        self._emit(actor="lanista", action="back", state=s, line=line or "Backed.")
        self.fight(s)
        return s

    def fight(self, s: GladiatorState) -> None:
        for _ in range(len(ARENA_TESTS)):
            options = [t for t in ARENA_TESTS if t not in s.results
                       and config.COST[t] <= self.denarii
                       and (t != "sensor_check" or len(self.sensors) >= 2)]
            if not options:
                break
            test, line = self.sceptic.next_attack(s, options, self.denarii)
            if test not in options:
                break
            self._emit(actor="sceptic", action="attack", state=s, test=test, line=line)
            self._run_test(s, test)
            if not s.alive:
                return
        if "leak_audit" not in s.results:
            self._emit(actor="system", action="attack", state=s, test="leak_audit",
                       line="The Inquisitor checks every gladiator before it can survive.")
            self._run_test(s, "leak_audit")
        if s.alive and not referee.crown_survivor(s):
            s.status, s.verdict = "unproven", "UNPROVEN"
        if s.status in ("survivor", "unproven"):
            self._emit(actor="engine", action=s.status, state=s,
                       line="Survives the arena!" if s.status == "survivor"
                       else "Out of denarii before the Shuffler. Unproven.")

    def census(self) -> None:
        # Every claim the Trial judged counts as a try; ones that never reached the
        # Shuffler count with p = 1. Otherwise selection before correction hides the tries.
        pvalues = {}
        for gid, s in self.states.items():
            if "shuffle_test" in s.results:
                pvalues[gid] = s.results["shuffle_test"]["p"]
            elif "added_value" in s.results and not s.results["added_value"].get("untestable"):
                pvalues[gid] = 1.0
        if not pvalues:
            return
        verdicts = engine.penalty(pvalues)
        n = len(pvalues)
        self._emit(actor="engine", action="census", test="penalty",
                   line=f"The Census counts {n} claim{'s' if n != 1 else ''} tried so far. "
                        "The more you try, the higher the bar.")
        for gid, res in verdicts.items():
            s = self.states[gid]
            if s.status != "survivor":
                continue
            if res["passed"]:
                s.results["penalty"] = res
            else:
                s.status = "arena"
                self._record(s, "penalty", res)

    def exhibition(self, text: str) -> GladiatorState | None:
        """'Test my theory': a crowd claim, fought on its own with no stakes."""
        self.day = self.day or 3
        catalog = [f for f in public_catalog(self.registry, 3, set(self.train.columns))
                   if f["name"] not in {d.name for d in decoys.DECOY_FEATURES}]
        g = self.lanista.theory(text, catalog)
        g = None if g is None else self._validate(g.model_copy(update={"origin": "crowd"}), 3, catalog)
        if g is None:
            self._emit(actor="crowd", action="no_match", line=f"No feature matches: {text[:80]}")
            return None
        s = self.enter(g.model_copy(update={"origin": "crowd"}), actor="crowd", auto_back=True)
        if s.status == "survivor" and self.test is not None:
            s.prereg_hash = preregister(s.gladiator)
            result = engine.final_boss(self.train, self.test, s.gladiator, self.n_boot, self._seed())
            self._record(s, "final_boss", result)
        return s

    def summary(self) -> dict:
        decoy_rows = []
        for s in self.states.values():
            name = s.gladiator.add_features[0]
            if s.gladiator.origin in ("decoy", "emperor"):
                decoy_rows.append({"feature": name, "verdict": s.verdict, "status": s.status,
                                   "caught": decoys.caught(name, s.status, self.decoy_plan.emperor)})
        result = {
            "verdicts": dict(Counter(s.verdict or s.status for s in self.states.values())),
            "decoys": decoy_rows,
            "caught": sum(r["caught"] for r in decoy_rows),
            "total_decoys": len(decoy_rows),
            "emperor": self.decoy_plan.emperor,
            "tested": len(self.states),
        }
        self._emit(actor="system", action="summary", result=result,
                   line=f"{result['tested']} gladiators fought. Decoys caught: "
                        f"{result['caught']} of {result['total_decoys']}.")
        return result

    def graveyard(self) -> list[dict]:
        return [{"claim": s.gladiator.claim, "add_features": s.gladiator.add_features,
                 "verdict": s.verdict, "killed_by": s.wounds[-1] if s.wounds else None}
                for s in self.states.values() if s.status in ("dead", "dropped", "fallen")]

    # ---------- internals ----------

    def _baseline(self, day: int) -> list[str]:
        return [] if day <= 1 else ["carbs"]

    def _validate(self, g: Gladiator, day: int, catalog: list[dict]) -> Gladiator | None:
        allowed = {f["name"] for f in catalog}
        today = {f["name"] for f in catalog if f["day"] == day}
        adds = [f for f in dict.fromkeys(g.add_features) if f not in self._baseline(day)][:2]
        fought = {frozenset(s.gladiator.add_features) for s in self.states.values()}
        problem = None
        if not adds:
            problem = "adds nothing beyond the baseline"
        elif any(f not in allowed for f in adds):
            problem = f"unknown features {[f for f in adds if f not in allowed]}"
        elif day > 1 and day <= 3 and g.origin != "crowd" and not set(adds) & today:
            problem = "uses no feature unlocked today"
        elif frozenset(adds) in fought and g.origin != "crowd":
            problem = "that gladiator already fought"
        if problem:
            self._emit(actor="system", action="rejected", line=f"Turned away at the gate: {problem}.",
                       gladiator=g.model_dump())
            return None
        return g.model_copy(update={"add_features": adds})

    def _seed(self) -> int:
        self._calls += 1
        return self.seed + self._calls

    def _pay(self, test: str, s: GladiatorState) -> bool:
        cost = config.COST[test]
        if cost > self.denarii:
            self._emit(actor="system", action="broke", state=s, test=test,
                       line=f"Not enough denarii for {config.OPPONENTS[test]}.")
            return False
        self.denarii -= cost
        return True

    def _run_test(self, s: GladiatorState, test: str) -> None:
        if not self._pay(test, s):
            return
        g, seed = s.gladiator, self._seed()
        if test == "leak_audit":
            result = engine.leak_audit(g, self.registry)
        elif test == "shuffle_test":
            result = engine.shuffle_test(self.train, g, self.n_perm, seed)
        else:
            result = engine.sensor_check(self.sensors, g, seed=seed)
        self._record(s, test, result)

    def _record(self, s: GladiatorState, test: str, result: dict) -> None:
        damage = referee.apply_result(s, test, result)
        self._emit(actor="engine", action="result", state=s, test=test, result=_round(result),
                   passed=result.get("passed"), line=narrate(test, result, damage))
        if s.status in ("dead", "fallen", "champion"):
            self._settle(s)

    def _settle(self, s: GladiatorState) -> None:
        gid = s.gladiator.id
        if gid in self._settled or s.gladiator.origin == "crowd":
            return
        self._settled.add(gid)
        delta = referee.reputation_change(s)
        if delta:
            self.reputation += delta
            self._emit(actor="system", action="reputation", state=s,
                       line=f"Lanista reputation {delta:+d}.")
        if self.reputation <= 0 and not self.banished:
            self.banished = True
            self._emit(actor="system", action="banished",
                       line="The Lanista's reputation is gone. Banished from the arena!")

    def _emit(self, state: GladiatorState | None = None, **fields) -> None:
        if state is not None:
            fields.update(gladiator_id=state.gladiator.id, hp=state.hp,
                          status=state.status, verdict=state.verdict)
        self.ledger.write(day=self.day, reputation=self.reputation, denarii=self.denarii, **fields)
        if self.pace:
            time.sleep(self.pace)

    def _start_day(self, day: int) -> None:
        self.day = day
        self._emit(actor="system", action="day_start", line=config.DAY_NAMES[day])


def _round(d: dict) -> dict:
    out = {}
    for k, v in d.items():
        if isinstance(v, float):
            out[k] = round(v, 4)
        elif isinstance(v, dict):
            out[k] = _round(v)
        else:
            out[k] = v
    return out


def narrate(test: str, r: dict, damage: int) -> str:
    """Deterministic narration from the engine's numbers. Agents never write these."""
    name = config.OPPONENTS[test]
    if r.get("untestable"):
        return f"{name}: cannot be judged ({r.get('reason', 'not enough data')})."
    hit = "" if r["passed"] else f" Hit for {damage}!"
    if test in ("added_value", "final_boss"):
        where = "unseen people" if test == "final_boss" else "people"
        return (f"{name}: {r['gain']:+.2f} mg/dL per meal across {r['n_participants']} {where} "
                f"(95% CI {r['ci_low']:+.2f} to {r['ci_high']:+.2f}).{hit}")
    if test == "leak_audit":
        if r["passed"]:
            return f"{name}: nothing here is built from the result."
        return f"{name}: {', '.join(r['leaky'] or r['unknown'])} is built from the result itself!{hit}"
    if test == "shuffle_test":
        return (f"{name}: {r['beaten_by']} of {r['n_perm']} shuffled copies did as well "
                f"(p = {r['p']:.3f}).{hit}")
    if test == "penalty":
        return f"{name}: {r['m']} claims tested, adjusted p = {r['p_adj']:.3f}.{hit}"
    if test == "sensor_check":
        parts = ", ".join(f"{k} {v:+.2f}" for k, v in r["by_sensor"].items() if v is not None)
        return f"{name}: {parts} mg/dL per meal.{hit}"
    return f"{name}.{hit}"

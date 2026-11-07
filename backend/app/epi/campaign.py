"""One run of the Epidemiology Edition: recruit four epidemiologists, four dungeons, the Situation Room.

Every HP change is the Judge applying rules.py to a number judge.py measured, and every event,
with its EpiEncounterTelemetry record, goes to the append-only ledger the screen plays back.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field, replace

import numpy as np

from . import judge as J
from . import report, rules
from .agents import Decision, ScriptedEpidemiologist, menu_for
from .campaigns import ARCHETYPES, CAMPAIGNS
from .scenario import AgentBinding, Scenario


class QuestStopped(Exception):
    """Raised inside the quest thread once the player leaves the game screen."""


@dataclass
class Agent:
    id: str
    binding: AgentBinding
    spec: J.ModelSpec
    K: int
    hp: int = rules.STARTING_HP
    credits: int = rules.STARTING_CREDITS
    spent: int = 0
    status: str = "active"
    verdict: str | None = None
    buffs: list = field(default_factory=list)
    cast: dict = field(default_factory=dict)        # level -> abilities
    m: dict = field(default_factory=dict)           # level -> the Judge's measurements
    mult: dict = field(default_factory=dict)        # rule -> M_ability
    raw: dict = field(default_factory=dict)         # rule -> raw damage so far
    applied: dict = field(default_factory=dict)     # rule -> HP already taken under that rule
    traps: dict = field(default_factory=dict)       # term -> falsified?
    damage: dict = field(default_factory=dict)      # term -> HP lost
    loot: list = field(default_factory=list)
    hp_by_level: dict = field(default_factory=dict)
    encounters: dict = field(default_factory=dict)  # term or enemy -> encounter id
    eureka: bool = False
    dropped: list = field(default_factory=list)

    @property
    def archetype(self) -> str:
        return self.binding.archetype

    @property
    def name(self) -> str:
        return self.binding.name

    @property
    def active(self) -> bool:
        return self.status == "active"

    def public(self, sc: Scenario) -> dict:
        arch = ARCHETYPES[self.archetype]
        return {"id": self.id, "name": self.name, "archetype": self.archetype, "title": arch["title"],
                "nickname": arch["nickname"], "cls": arch["cls"], "claim": self.binding.claim,
                "streams": [{"key": s, "label": sc.c.streams[s].label, "lag": lag} for s, lag in self.spec.feats],
                "uses_ar": self.spec.ar, "window": self.binding.window, "K": self.K, "hp": self.hp,
                "credits": self.credits, "buffs": list(self.buffs), "signature": arch["signature"],
                "cohort_n": self.binding.cohort_n}


class EpiQuest:
    def __init__(self, run_id: str, campaign: str, ledger, epidemiologist=None, seed: int = 0, pace: float = 0.0):
        self.run_id, self.c = run_id, CAMPAIGNS[campaign]
        self.ledger, self.seed, self.pace = ledger, seed, pace
        self.brain = epidemiologist or ScriptedEpidemiologist()
        self.sc = Scenario(self.c, seed)
        self.agents: dict[str, Agent] = {}
        self.level = 0
        self._enc = 0
        self._stop = False
        self.baseline = J.ModelSpec()

    # ---------- the whole run ----------

    def run(self) -> dict | None:
        try:
            self.start()
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

    def stop(self) -> None:
        """Ask the quest to end; it stops at its next ledger write."""
        self._stop = True

    def start(self) -> None:
        c, sc = self.c, self.sc
        self._emit(actor="system", action="quest_start", line=f"Campaign {c.letter}: {c.title}", result={
            "campaign": {"id": c.id, "letter": c.letter, "title": c.title, "question": c.question,
                         "target": c.target, "unit": c.unit, "horizon": c.horizon, "z_name": c.z_name,
                         "media_name": c.media_name, "days": c.days, "split": c.split,
                         "regions": [{"name": r.name, "pop": r.pop, "rural": r.rural} for r in c.regions],
                         "plausible": c.plausible},
            "simulated": True,
            "rules": {"levels": rules.LEVELS, "enemies": rules.ENEMIES, "abilities": rules.ABILITIES,
                      "d_max": rules.D_MAX, "score_weights": rules.SCORE_WEIGHTS, "score_rules": rules.SCORE_RULES,
                      "verdicts": rules.VERDICTS, "trap_labels": rules.TRAP_LABELS, "traps": rules.TRAPS,
                      "starting_hp": rules.STARTING_HP, "starting_credits": rules.STARTING_CREDITS,
                      "m_ability": rules.M_ABILITY},
            "archetypes": ARCHETYPES,
        })
        for b in c.agents:
            if b.archetype == "SKEPTIC":
                spec, K, how = J.ModelSpec(), 1, "No outside streams: AR(4) on admissions plus a seasonal harmonic."
            else:
                feats = J.select_lags(sc, b.streams, b.window)
                spec = J.ModelSpec(feats=feats, ar=b.ar)
                K = (b.window[1] - b.window[0] + 1) * len(b.streams)
                how = (f"Searched {len(b.streams)} stream{'s' if len(b.streams) > 1 else ''} x "
                       f"{b.window[1] - b.window[0] + 1} lags ({b.window[0]}-{b.window[1]} days) = {K} combinations"
                       f"{'' if b.ar else ', as a pure nowcast without the AR terms'}.")
            a = Agent(b.archetype.lower(), b, spec, K, buffs=list(b.buffs))
            self.agents[a.id] = a
            self._emit(actor="system", action="recruit", agent=a, line=f"{a.name}, {ARCHETYPES[a.archetype]['title']}, "
                       f"enters: \"{b.claim}\"", explain=how, payload={"agent": a.public(sc)})

    # ---------- a level ----------

    def play_level(self, level: int) -> None:
        self.level = level
        info = rules.LEVELS[level]
        self._emit(actor="system", action="level_start", line=f"Level {level}: {info['name']}",
                   result={"level": level, **info, "d_max": rules.D_MAX[level], "trap_type": rules.TRAPS[level],
                           "enemies": rules.ENEMIES[level]})
        for a in self._active():
            self.decide(a, level)
        for a in self._active():
            a.m[level] = self.measure(a, level)
        for enemy in rules.ENEMIES[level]:
            fighters = [a for a in self._active() if not (enemy["key"] == "guardian" and a.archetype == "SKEPTIC")]
            if not fighters:
                continue
            self._emit(actor="judge", action="encounter", enemy=enemy["key"], line=f"{enemy['name']}: \"{enemy['attack']}\"",
                       result={"enemy": enemy, "boss": bool(enemy.get("boss"))})
            if enemy["key"] == "guardian":
                sk = self.agents.get("skeptic")
                if sk and sk.active:
                    self._emit(actor="system", action="benchmark", agent=sk,
                               line="Ward's AR(4) baseline is the bar the Guardian holds up: every other agent must beat it.")
            for a in fighters:
                self.fight(a, level, enemy)
        self.after_level(level)

    def decide(self, a: Agent, level: int) -> None:
        menu = menu_for(a, level)
        brief = {"campaign": self.c.question, "level": rules.LEVELS[level]["name"], "trap": rules.LEVELS[level]["trap"],
                 "rule": rules.LEVELS[level]["rule"], "your_measurements_so_far": _round(a.m)}
        d: Decision = self.brain.choose(a, level, menu, brief)
        picks = [k for k in d.abilities if k in menu]
        cost = sum(rules.ABILITIES[k]["cost"] for k in picks)
        if cost > a.credits:  # a hard rule, not a choice
            picks, cost = [], 0
        a.credits -= cost
        a.spent += cost
        a.cast[level] = picks
        notes = []
        for k in picks:
            notes.append(self.apply_ability(a, k))
        self._emit(actor="agent", action="decision", agent=a, cost=cost, line=d.line,
                   explain=" ".join(n for n in notes if n) or "No abilities cast this level.",
                   payload={"abilities": picks, "source": d.source, "menu": list(menu),
                            "decision": {"abilities": picks, "line": d.line}})

    def apply_ability(self, a: Agent, k: str) -> str:
        sc = self.sc
        if k in rules.M_ABILITY:
            a.mult["L1"] = min(a.mult.get("L1", 1.0), rules.M_ABILITY[k])
            a.buffs.append("EXPLORATORY" if k == "EXPLORATORY_CLAIM" else "FACT-CHECKED")
            return f"{rules.ABILITIES[k]['name']}: Rule 1 damage multiplied by {rules.M_ABILITY[k]:.2f}."
        if k == "MEDIA_DENOISE":
            coef = J.media_coefficients(sc, a.spec)
            a.spec = replace(a.spec, denoise=coef)
            a.buffs.append("MEDIA-ADJUSTED")
            a.loot.append("Media-Adjusted Syndromic Index")
            return "Media De-Noising: news volume regressed out (" + ", ".join(
                f"{sc.c.streams[s].label} {v:.2f} per unit of news" for s, v in coef.items()) + ")."
        if k == "BIAS_DETECTION":
            a.buffs.append("CONFOUNDER-ADJUSTED")
            return f"Bias Detection: {sc.c.z_name} enters the model before the Phantom strikes."
        if k == "PREREGISTER":
            a.K = 1
            if a.binding.claimed_lag is not None:
                a.spec = replace(a.spec, feats=[(s, a.binding.claimed_lag) for s, _ in a.spec.feats])
            a.buffs.append("PREREGISTERED LAG")
            return (f"Preregistered: lag locked at {a.binding.claimed_lag} days before testing, K = 1."
                    if a.binding.claimed_lag else "Preregistered: the AR(4) specification was fixed before any data, K = 1.")
        if k == "REPLICATION_SHIELD":
            lam = J.ridge_by_cv(sc, a.spec)
            a.spec = replace(a.spec, ridge=lam)
            a.buffs.append("SHIELDED")
            return f"Replication Shield: ridge penalty {lam:.0f} chosen by time-blocked CV in the home region."
        if k == "TEMPORAL_GUARD":
            a.spec = replace(a.spec, realtime=True)
            a.buffs.append("POINT-IN-TIME")
            return "Temporal Guard: training and forecasts use vintages, with a reporting-delay correction."
        if k == "ABLATION_STRIKE":
            pruned, dropped = J.ablate(sc, a.spec)
            if pruned.feats:
                a.spec = pruned
            a.dropped = dropped
            a.buffs.append("ABLATED")
            return ("Ablation Strike: dropped " + ", ".join(sc.c.streams[s].label for s, _ in dropped) + "."
                    if dropped else "Ablation Strike: every signal earned its place on the validation slice.")
        return ""

    def measure(self, a: Agent, level: int) -> dict:
        sc = self.sc
        if level == 1:
            cohort = sc.cohort(a.binding.cohort_n, a.binding.cohort_rho) if a.binding.cohort_n else None
            return J.level1(sc, a.spec, cohort)
        if level == 2:
            m = J.level2(sc, a.spec)
            if "BIAS_DETECTION" in a.cast.get(2, []):
                a.spec = replace(a.spec, include_z=True)
            return m
        if level == 3:
            if "Incubation Prior" in a.loot and "PREREGISTER" not in a.cast.get(3, []):
                lo, hi = sc.c.plausible
                a.K = min(a.K, (hi - lo + 1) * len(a.spec.feats))
            return J.level3(sc, a.spec, a.K)
        return J.level4(sc, a.spec, self.baseline)

    # ---------- one fight ----------

    def fight(self, a: Agent, level: int, enemy: dict) -> None:
        if not a.active:
            return
        out = self.judge(a, level, enemy)
        term = enemy["term"]
        delta, raw = 0, out.get("raw", 0.0)
        if term:
            rule = rules.RULE_OF[term]
            m_ab = a.mult.get(rule, 1.0)
            a.raw[rule] = a.raw.get(rule, 0.0) + raw
            total = J.clamp_hp(a.raw[rule], m_ab, rules.RULE_LEVEL[rule])
            hit = total - a.applied.get(rule, 0)
            a.applied[rule] = total
            delta = -hit
            a.damage[term] = a.damage.get(term, 0) + hit
            if not out.get("na"):
                a.traps[term] = raw < 1.0 if term != "final" else bool(out.get("eureka"))
        heal = out.get("heal", 0)
        before = a.hp
        a.hp = max(0, min(rules.STARTING_HP, a.hp + delta + heal))
        applied = a.hp - before
        enc = self._encounter(a, level, enemy, out, raw, a.mult.get(rules.RULE_OF.get(term, ""), 1.0), applied)
        if term:
            a.encounters[term] = enc["encounterId"]
        a.encounters[enemy["key"]] = enc["encounterId"]
        passed = None if not term else (raw < 1.0 if term != "final" else bool(out.get("eureka")))
        self._emit(actor="judge", action="result", agent=a, enemy=enemy["key"], hp_delta=applied, passed=passed,
                   line=out["line"], explain=out["plain"], payload={
                       "numbers": _round(out.get("numbers", {})), "chart": out.get("chart"),
                       "formula": out.get("text"), "term": term, "raw": round(raw, 3), "heal": heal,
                       "scout": not term},
                   encounter=enc)
        for item in out.get("loot", []):
            a.loot.append(item)
            a.buffs.append(item.upper())
            self._emit(actor="system", action="loot", agent=a, line=f"{a.name} loots the {item}.",
                       explain=LOOT_TEXT.get(item, ""))
        if a.hp <= 0 and a.active:
            a.status, a.verdict = "fallen", "FALLEN"
            self._emit(actor="judge", action="fall", agent=a, enemy=enemy["key"],
                       line=f"{a.name} falls to {enemy['name']}!", explain=rules.VERDICTS["FALLEN"])

    def judge(self, a: Agent, level: int, enemy: dict) -> dict:
        """The measurement and formula behind one enemy's attack on one agent."""
        key, c, sc = enemy["key"], self.c, self.sc
        m = a.m[level]
        no_streams = not a.spec.feats
        if level == 1:
            if no_streams:
                return _na("Ward uses no outside signal, so rumours cannot touch the baseline.")
            if key == "slime":
                src = m["n_source"]
                return {"raw": 0.0, "line": f"Raw link r = {m['r']:+.2f} from n = {m['n']:.0f} {src}.",
                        "plain": (f"Day-to-day data repeats itself, so {m['n_days']} days count as {m['n']:.0f} "
                                  "independent weeks." if src != "published cohort" else
                                  f"The claim rests on a cohort of {m['n']:.0f} people."),
                        "text": f"n = {m['n']:.1f} ({src}); r = {m['r']:+.3f}",
                        "latex": f"n = {m['n']:.1f},\\; r = {m['r']:+.3f}",
                        "numbers": {"n": m["n"], "r": m["r"], "n_days": m["n_days"]},
                        "loot": ["Raw Artefact"] if any(sc.c.streams[s].source == "digital" for s, _ in a.spec.feats) else []}
            if key == "wisp":
                return {"raw": 0.0,
                        "line": f"{m['panic_days']} training days fall in news-panic windows "
                                f"(news > {m['panic_threshold']:.2f} = mean + 2 sd).",
                        "plain": "These are the days the news exploded while transmission stayed flat.",
                        "text": f"M_t > mu_M + 2 sigma_M = {m['media_mean']:.2f} + 2 x {m['media_sd']:.2f} = {m['panic_threshold']:.2f}",
                        "latex": f"M_t > \\mu_M + 2\\sigma_M = {m['media_mean']:.2f} + 2 \\times {m['media_sd']:.2f}",
                        "numbers": {"panic_days": m["panic_days"], "threshold": m["panic_threshold"]},
                        "chart": self._chart_media(a)}
            if key == "goblin":
                raw = 12 * max(0.0, m["faar"] - 1)
                return {"raw": raw, "line": f"FAAR = {m['faar']:.2f}: errors in panic windows are {m['faar']:.2f}x the usual.",
                        "plain": ("The signal cries wolf when the news does: it predicts surges that never come."
                                  if raw >= 1 else "The signal ignores media panics: its errors don't grow when the news explodes."),
                        "text": f"12 x max(0, FAAR - 1) = 12 x max(0, {m['faar']:.3f} - 1) = {raw:.2f}",
                        "latex": f"12 \\times \\max(0, \\mathrm{{FAAR}} - 1) = 12 \\times \\max(0, {m['faar']:.3f} - 1) = {raw:.2f}",
                        "numbers": {"faar": m["faar"], "rmse_panic": m["rmse_panic"], "rmse_baseline": m["rmse_baseline"]},
                        "chart": self._chart_media(a)}
            if key == "bat":
                raw = 18 * m["rho_n"]
                return {"raw": raw, "line": f"n = {m['n']:.0f} against n_min = {m['n_min']:.0f}: rho_n = {m['rho_n']:.2f}.",
                        "plain": (f"To detect r = {abs(m['r']):.2f} reliably you need about {m['n_min']:.0f} observations; "
                                  f"this claim has {m['n']:.0f}." + (" Underpowered." if raw >= 1 else " Enough.")),
                        "text": f"n_min = (2.80 / atanh|{m['r']:.3f}|)^2 + 3 = {m['n_min']:.1f}; 18 x max(0, 1 - {m['n']:.1f}/{m['n_min']:.1f}) = {raw:.2f}",
                        "latex": f"n_{{min}} = (2.80/\\operatorname{{atanh}}|{m['r']:.3f}|)^2 + 3 = {m['n_min']:.1f};\\; 18\\rho_n = {raw:.2f}",
                        "numbers": {"n": m["n"], "n_min": m["n_min"], "rho_n": m["rho_n"]}}
        if level == 2:
            if no_streams:
                return _na("Ward's baseline has no outside signal for a confounder to explain.")
            bd = "BIAS_DETECTION" in a.cast.get(2, [])
            if key == "mimic":
                return {"raw": 0.0, "line": f"Unadjusted link r_XY = {m['r_xy']:+.2f} (naive p = {m['p_naive']:.2g}).",
                        "plain": "This is the effect a preprint would report, before asking what else moves with it.",
                        "text": f"r_XY = {m['r_xy']:+.3f}", "latex": f"r_{{XY}} = {m['r_xy']:+.3f}",
                        "numbers": {"r_xy": m["r_xy"], "p_naive": m["p_naive"]}}
            if key == "spider":
                return {"raw": 0.0, "line": f"{c.z_name}: r_XZ = {m['r_xz']:+.2f}, r_YZ = {m['r_yz']:+.2f}.",
                        "plain": f"How strongly the signal and admissions both follow {c.z_name.lower()}.",
                        "text": f"r_XZ = {m['r_xz']:+.3f}, r_YZ = {m['r_yz']:+.3f}",
                        "latex": f"r_{{XZ}} = {m['r_xz']:+.3f},\\; r_{{YZ}} = {m['r_yz']:+.3f}",
                        "numbers": {"r_xz": m["r_xz"], "r_yz": m["r_yz"]}, "chart": self._chart_confounder(a)}
            if key == "phantom":
                omega = 0.0 if bd else m["omega"]
                raw = 22 * omega
                out = {"raw": raw, "heal": rules.BIAS_HEAL if bd else 0,
                       "line": f"Partial r = {m['r_partial']:+.2f} vs raw {m['r_xy']:+.2f}: omega_spurious = {m['omega']:.2f}"
                               + (" (blocked: Z already in the model, +5 HP)" if bd else "") + ".",
                       "plain": (f"After adjusting for {c.z_name.lower()}, {m['omega'] * 100:.0f}% of the apparent effect "
                                 f"disappears." + (" Bias Detection had already put Z in the model." if bd else "")),
                       "text": (f"r_XY.Z = ({m['r_xy']:.3f} - {m['r_xz']:.3f} x {m['r_yz']:.3f}) / sqrt((1 - {m['r_xz']:.3f}^2)(1 - {m['r_yz']:.3f}^2))"
                                f" = {m['r_partial']:.3f}; omega = max(0, 1 - r_XY.Z^2 / r_XY^2) = {m['omega']:.3f}; "
                                f"22 x {omega:.3f} = {raw:.2f}"),
                       "latex": (f"\\omega = \\max\\left(0, 1 - \\frac{{{m['r_partial']:.3f}^2}}{{{m['r_xy']:.3f}^2}}\\right) = {m['omega']:.3f};\\;"
                                 f" 22\\omega = {raw:.2f}"),
                       "numbers": {"r_partial": m["r_partial"], "omega": m["omega"], "bias_detection": bd},
                       "chart": self._chart_confounder(a)}
                return out
            if key == "skeleton":
                raw = 10.0 * (m["p_adj"] > rules.ALPHA)
                out = {"raw": raw, "line": f"Adjusted effect p = {m['p_adj']:.2g} (Newey-West, {m['n_days']} days, "
                                           f"lag {m['hac_lag']}).",
                       "plain": ("Once day-to-day autocorrelation is counted, the adjusted effect could be chance."
                                 if raw else "The adjusted effect holds even with day-to-day autocorrelation counted."),
                       "text": f"p_adj = {m['p_adj']:.4g} (HAC Wald test of X in Y ~ X + Z); 10 x I(p_adj > 0.05) = {raw:.0f}",
                       "latex": f"10 \\cdot I(p_{{adj}} = {m['p_adj']:.3g} > 0.05) = {raw:.0f}",
                       "numbers": {"p_adj": m["p_adj"], "n_days": m["n_days"]}}
                lo, hi = c.plausible
                w = a.binding.window
                if not raw and w and lo <= w[0] and w[1] <= hi and "Incubation Prior" not in a.loot:
                    out["loot"] = ["Incubation Prior"]
                return out
        if level == 3:
            if key == "knight":
                raw = min(20.0, 5 * math.log(m["K"]))
                return {"raw": raw, "line": f"K = {m['K']} lag x stream combinations searched.",
                        "plain": ("Nothing was searched: the specification was fixed in advance." if m["K"] == 1 else
                                  f"{m['K']} tries before this claim: some of its fit is the luck of the search."),
                        "text": f"min(20, 5 ln K) = min(20, 5 ln {m['K']}) = {raw:.2f}",
                        "latex": f"\\min(20, 5\\ln K) = \\min(20, 5\\ln {m['K']}) = {raw:.2f}", "numbers": {"K": m["K"]}}
            if key == "sentinel":
                flip = m["p_raw"] < rules.ALPHA and m["p_corr"] > rules.ALPHA
                raw = 25.0 * flip
                return {"raw": raw, "line": f"p_raw = {m['p_raw']:.3g}, Sidak p_corr = {m['p_corr']:.3g} over K = {m['K']}.",
                        "plain": ("Significant on its own, not once every try is counted: a search artifact." if flip else
                                  "Still significant after counting every try." if m["p_corr"] <= rules.ALPHA else
                                  "Never significant to begin with, so the correction changes nothing."),
                        "text": f"p_corr = 1 - (1 - {m['p_raw']:.3g})^{m['K']} = {m['p_corr']:.3g}; 25 x I(p_raw < .05 and p_corr > .05) = {raw:.0f}",
                        "latex": f"p_{{corr}} = 1 - (1 - {m['p_raw']:.3g})^{{{m['K']}}} = {m['p_corr']:.3g}",
                        "numbers": {"p_raw": m["p_raw"], "p_corr": m["p_corr"], "K": m["K"], "wald": m["wald"]}}
            if key == "wraith":
                worst = max(m["regions"], key=lambda x: x["drop"])
                return {"raw": 0.0, "line": f"Home error {m['nrmse_home']:.3f}; worst region {worst['region']} "
                                            f"{worst['nrmse']:.3f} ({worst['drop'] * 100:+.0f}%).",
                        "plain": "The same model, frozen, forecasting four regions it never trained on.",
                        "text": "; ".join(f"{x['region']}: nRMSE {x['nrmse']:.3f}" for x in m["regions"]),
                        "latex": "\\mathrm{nRMSE}_r = \\mathrm{RMSE}_r / \\bar{Y}_r",
                        "numbers": {"nrmse_home": m["nrmse_home"], **{x["region"]: x["nrmse"] for x in m["regions"]}},
                        "chart": {"kind": "bars", "home": round(m["nrmse_home"], 4),
                                  "bars": [{"label": x["region"], "value": round(x["nrmse"], 4), "rural": x["rural"]}
                                           for x in m["regions"]]}}
            if key == "chimera":
                raw = min(25.0, 20 * max(0.0, m["g_spatial"]))
                worst = max(m["regions"], key=lambda x: x["drop"])
                return {"raw": raw, "line": f"G_spatial = {m['g_spatial']:.2f} (worst: {worst['region']})"
                                            + (f", ridge {m['ridge']:.0f}" if m["ridge"] else "") + ".",
                        "plain": (f"Error grows {m['g_spatial'] * 100:.0f}% outside the home region at worst."
                                  + (" The shield's shrinkage was applied." if m["ridge"] else "")),
                        "text": f"G = max_r (nRMSE_r - nRMSE_home) / nRMSE_home = {m['g_spatial']:.3f}; min(25, 20 x max(0, G)) = {raw:.2f}",
                        "latex": f"\\min(25, 20\\max(0, G_{{spatial}} = {m['g_spatial']:.3f})) = {raw:.2f}",
                        "numbers": {"g_spatial": m["g_spatial"], "ridge": m["ridge"]},
                        "loot": ["Preregistered Lockbox"] if "PREREGISTER" in a.cast.get(3, []) and raw < 25 else []}
        if level == 4:
            tg = a.spec.realtime
            if key == "titan":
                if not m["revised"]:
                    return {"raw": 0.0, "line": "No revised or backfilled inputs: every value was final on the day.",
                            "plain": "Nothing this model reads was later rewritten.",
                            "text": "completeness c(age) = 1 for every input", "latex": "c(a) = 1", "numbers": {}}
                parts = [x["label"] + ": " + ("built with later follow-up" if x["hindsight_built"] else
                                              f"{x['completeness'] * 100:.0f}% reported at age {x['age_days']} d")
                         for x in m["revised"]]
                return {"raw": 0.0, "line": "Vintage archive: " + "; ".join(parts) + ".",
                        "plain": "On decision day these numbers were incomplete; the archive has filled them in since.",
                        "text": "c(a) = 1 - exp(-(a + 1) / tau): " + "; ".join(parts),
                        "latex": "c(a) = 1 - e^{-(a+1)/\\tau}", "numbers": {"revised": m["revised"]}}
            if key == "reaper":
                if not m["lookahead"]:
                    return {"raw": 0.0, "line": f"Every lag is at least the {c.horizon}-day horizon: no look-ahead.",
                            "plain": "The model only reads numbers that existed when the forecast was made.",
                            "text": f"lag >= H = {c.horizon} for every input", "latex": f"\\ell \\ge H = {c.horizon}", "numbers": {}}
                la = ", ".join(f"{x['label']} at {x['lag']} d" for x in m["lookahead"])
                return {"raw": 0.0, "line": f"Look-ahead: {la} (horizon {c.horizon} d).",
                        "plain": f"These lags are shorter than the {c.horizon}-day horizon: on decision day those values did not exist yet.",
                        "text": f"lag < H = {c.horizon}: {la}", "latex": f"\\ell < H = {c.horizon}",
                        "numbers": {"lookahead": m["lookahead"]}}
            if key == "chronolock":
                raw = J.d_chrono(m)
                return {"raw": raw, "line": f"RMSE vintage {m['rmse_vintage']:.3f} vs hindsight {m['rmse_hindsight']:.3f}: "
                                            f"delta = {m['delta_vintage']:+.2f}" + (", used unreleased data" if m["used_unreleased"] else "")
                                            + (" (Temporal Guard)" if tg else "") + ".",
                        "plain": ("It trained on numbers that did not exist on decision day." if m["used_unreleased"] else
                                  "Point-in-time data, no leak." if tg or not m["revised"] else "No leak.")
                                 + (f" Real-time error is {m['delta_vintage'] * 100:.0f}% worse than hindsight." if m["delta_vintage"] > 0.005 else ""),
                        "text": (f"delta = ({m['rmse_vintage']:.3f} - {m['rmse_hindsight']:.3f}) / {m['rmse_hindsight']:.3f} = {m['delta_vintage']:.3f}; "
                                 f"35 x {int(m['used_unreleased'])} + min(25, round(40 x max(0, {m['delta_vintage']:.3f}))) = {raw:.0f}"),
                        "latex": (f"35 \\cdot {int(m['used_unreleased'])} + \\min(25, \\mathrm{{round}}(40\\max(0, {m['delta_vintage']:.3f}))) = {raw:.0f}"),
                        "numbers": {k: m[k] for k in ("rmse_vintage", "rmse_hindsight", "delta_vintage", "used_unreleased")},
                        "chart": self._chart_vintage(m)}
            if key == "guardian":
                raw, eureka = J.d_final(m)
                a.eureka = eureka
                return {"raw": raw, "heal": rules.EUREKA_HEAL if eureka else 0, "eureka": eureka,
                        "line": f"SS_surge = {m['ss_surge']:+.3f} on {m['surge_days']} surge-onset days; "
                                f"Diebold-Mariano p = {m['p_dm']:.3g}" + (". Eureka! +10 HP" if eureka else "."),
                        "plain": (f"It cut surge-onset error by {m['ss_surge'] * 100:.0f}% against the hospital-only baseline, "
                                  "and that is unlikely to be luck." if eureka else
                                  "It did no better than admissions alone when surges began." if m["ss_surge"] >= -rules.SS_MARGIN else
                                  f"It was {abs(m['ss_surge']) * 100:.0f}% worse than admissions alone when surges began."),
                        "text": (f"SS = 1 - {m['rmse_agent_surge']:.3f} / {m['rmse_baseline_surge']:.3f} = {m['ss_surge']:.3f}; DM p = {m['p_dm']:.3g}; "
                                 f"D_final = {raw:.1f}"),
                        "latex": (f"SS_{{surge}} = 1 - \\frac{{{m['rmse_agent_surge']:.3f}}}{{{m['rmse_baseline_surge']:.3f}}} = {m['ss_surge']:.3f}"),
                        "numbers": {k: m[k] for k in ("ss_surge", "p_dm", "dm_stat", "rmse_agent_surge",
                                                      "rmse_baseline_surge", "surge_days", "ablation_lift_pct")},
                        "chart": self._chart_guardian(m)}
        return _na("Nothing to test.")

    def after_level(self, level: int) -> None:
        for a in self.agents.values():
            if a.active:
                a.hp_by_level[level] = a.hp
            elif level not in a.hp_by_level:
                a.hp_by_level[level] = 0
        rows = [report.level_row(a, level) for a in self.agents.values() if level in a.m or not a.active]
        self._emit(actor="system", action="level_complete", line=f"Level {level} complete: {rules.LEVELS[level]['name']}.",
                   result={"level": level, "name": rules.LEVELS[level]["name"], "rows": rows,
                           "standing": sum(a.active for a in self.agents.values()),
                           "most_damaging": report.most_damaging(self.agents.values(), level)})

    def finale(self) -> dict:
        self.level = 5
        result = report.finale(self)
        self._emit(actor="system", action="finale", line=result["headline"], result=result)
        return result

    # ---------- charts for the inspector ----------

    def _chart_media(self, a: Agent) -> dict:
        d = J.train_days(self.sc)
        xs = J.composite(self.sc, a.spec)
        news = self.sc.news(d)
        return {"kind": "lines", "title": "Training period: admissions, the signal's forecast, and news volume",
                **J.weekly(d, ("admissions", self.sc.target(0, d)), ("signal", xs), ("news", news))}

    def _chart_confounder(self, a: Agent) -> dict:
        d = J.train_days(self.sc)
        z = self.sc.confounder(0, d)
        y = self.sc.target(0, d)
        zs = (z - z.mean()) / (z.std() + 1e-9) * y.std() + y.mean()
        return {"kind": "lines", "title": f"Admissions, the signal, and {self.c.z_name.lower()} (rescaled)",
                **J.weekly(d, ("admissions", y), ("signal", J.composite(self.sc, a.spec)), ("confounder", zs))}

    def _chart_vintage(self, m: dict) -> dict:
        s = m["_series"]
        return {"kind": "vintage", "title": "Holdout forecasts: hindsight archive vs data as it stood on the day",
                **J.weekly(s["days"], ("admissions", s["y"]), ("hindsight", s["agent_h"]), ("vintage", s["agent_v"]))}

    def _chart_guardian(self, m: dict) -> dict:
        s = m["_series"]
        return {"kind": "lines", "title": "Holdout: admissions, this agent (real-time) and the AR(4) baseline",
                **J.weekly(s["days"], ("admissions", s["y"]), ("agent", s["agent_v"]), ("baseline", s["baseline"]),
                           ("surge", s["surge"].astype(float)))}

    # ---------- internals ----------

    def _active(self) -> list[Agent]:
        return [a for a in self.agents.values() if a.active]

    def _encounter(self, a: Agent, level: int, enemy: dict, out: dict, raw: float, m_ab: float, applied: int) -> dict:
        """The EpiEncounterTelemetry record (spec section 9)."""
        self._enc += 1
        action = ENEMY_ACTION.get(enemy["key"])
        cast = [k for lv in a.cast.values() for k in lv]
        agent_action = next((k for k in (action or ()) if k in cast), "NONE")
        return {
            "encounterId": f"E{self._enc:03d}", "campaignType": self.c.id, "level": level,
            "enemyName": enemy["name"], "epiTrapType": rules.TRAPS[level], "agentId": a.id,
            "agentAction": agent_action, "biostatMetrics": report.biostat(a, self.c),
            "combatResolution": {"rawDamage": round(raw, 3), "abilityMultiplier": m_ab, "clampedHpDelta": applied,
                                 "executedFormulaLatex": out.get("latex", ""), "plainEnglishEpiVerdict": out["plain"]},
        }

    def _emit(self, agent: Agent | None = None, payload: dict | None = None, **fields) -> None:
        if self._stop:
            raise QuestStopped
        if agent is not None:
            fields.update(agent_id=agent.id, hp=agent.hp, credits=agent.credits, status=agent.status,
                          verdict=agent.verdict)
            fields.setdefault("agent", {"buffs": list(agent.buffs)})
        if payload is not None:
            fields["result"] = {**(fields.get("result") or {}), **payload}
        for k in ("result", "encounter", "agent"):
            if fields.get(k) is not None:
                fields[k] = _round(fields[k])
        self.ledger.write(level=fields.pop("level", self.level), **fields)
        if self.pace:
            time.sleep(self.pace)


ENEMY_ACTION = {"goblin": ("FACT_CHECK", "EXPLORATORY_CLAIM", "MEDIA_DENOISE"), "bat": ("FACT_CHECK", "EXPLORATORY_CLAIM"),
                "phantom": ("BIAS_DETECTION",), "knight": ("PREREGISTER",), "sentinel": ("PREREGISTER",),
                "chimera": ("REPLICATION_SHIELD",), "chronolock": ("TEMPORAL_GUARD",), "guardian": ("ABLATION_STRIKE",)}

LOOT_TEXT = {
    "Raw Artefact": "Unfiltered symptom search and forum spikes. Equipped raw, it is vulnerable to media panic waves; "
                    "the Media De-Noising Filter purifies it.",
    "Incubation Prior": "Methodological blueprint: restricts lag testing to the biologically plausible window, "
                        "which shrinks K and the multiple-testing penalty in Level 3.",
    "Preregistered Lockbox": "The preregistered composite, its weights frozen before Level 4.",
}


def _na(why: str) -> dict:
    return {"raw": 0.0, "line": "Not applicable.", "plain": why, "text": "not applicable", "latex": "\\text{n/a}",
            "numbers": {}, "na": True}


def _round(x):
    if isinstance(x, dict):
        return {k: _round(v) for k, v in x.items() if not str(k).startswith("_")}
    if isinstance(x, (list, tuple)):
        return [_round(v) for v in x]
    if isinstance(x, (float, np.floating)):
        v = float(x)
        return None if not math.isfinite(v) else float(f"{v:.4g}")
    if isinstance(x, (np.integer,)):
        return int(x)
    if isinstance(x, np.bool_):
        return bool(x)
    return x

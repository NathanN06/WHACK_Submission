"""One run of the Peptide & GLP-1 edition: the Alchemist carries three hypothesis scrolls through four
dungeons, the Gatekeeper Skeptic holds the active-comparator baseline, and the finale writes the brief.

Every HP change is the Judge applying rules.py to a number judge.py measured. Every event, with its
PepEncounterTelemetry record, goes to the append-only ledger the screen plays back.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field

import numpy as np

from . import judge as J
from . import report, rules
from .agents import Decision, ScriptedHero, menu_for
from .campaigns import ARCHETYPES, CAMPAIGNS, HERO
from .world import COVARIATE_LABELS, HOLDOUT_END, SITES, TRAIN_END, Scroll, World


class QuestStopped(Exception):
    """Raised inside the quest thread once the player leaves the game screen."""


@dataclass
class Agent:
    """One hypothesis scroll and everything the Judge has recorded about it."""
    id: str
    scroll: Scroll
    st: J.ScrollState
    hp: int = rules.STARTING_HP
    credits: int = rules.STARTING_CREDITS
    spent: int = 0
    status: str = "active"
    verdict: str | None = None
    buffs: list = field(default_factory=list)
    cast: dict = field(default_factory=dict)
    m: dict = field(default_factory=dict)
    mult: dict = field(default_factory=dict)
    raw: dict = field(default_factory=dict)
    applied: dict = field(default_factory=dict)
    traps: dict = field(default_factory=dict)
    damage: dict = field(default_factory=dict)
    hp_by_level: dict = field(default_factory=dict)
    encounters: dict = field(default_factory=dict)
    eureka: bool = False

    @property
    def archetype(self) -> str:
        return self.scroll.archetype

    @property
    def name(self) -> str:
        return self.scroll.title

    @property
    def claim(self) -> str:
        return self.scroll.claim

    @property
    def active(self) -> bool:
        return self.status == "active"

    def public(self, w: World) -> dict:
        arch = ARCHETYPES[self.archetype]
        o = next(x for x in w.c.outcomes if x.key == self.st.outcome)
        return {"id": self.id, "name": self.name, "archetype": self.archetype, "title": arch["title"],
                "nickname": arch["nickname"], "cls": arch["cls"], "claim": self.claim, "outcome": o.label,
                "origin": self.scroll.origin, "K": self.st.K, "design": self.st.design, "hp": self.hp,
                "credits": self.credits, "buffs": list(self.buffs), "kind": "scroll"}


class PepQuest:
    def __init__(self, run_id: str, campaign: str, ledger, hero=None, seed: int = 0, pace: float = 0.0):
        self.run_id, self.c = run_id, CAMPAIGNS[campaign]
        self.ledger, self.seed, self.pace = ledger, seed, pace
        self.brain = hero or ScriptedHero()
        self.w = World(self.c, seed)
        self.agents: dict[str, Agent] = {}
        self.level = 0
        self._enc = 0
        self._stop = False
        self.baseline: dict | None = None

    # ---------- the whole run ----------

    def run(self) -> dict | None:
        try:
            self.start()
            for level in (1, 2, 3, 4):
                self.play_level(level)
            return self.finale()
        except QuestStopped:
            self.ledger.write(level=self.level, actor="system", action="stopped",
                              line="The Research Director left the gauntlet, so the expedition was stopped.")
            return None
        except Exception as e:  # never end silently: say what broke
            self._emit(actor="system", action="error", line=f"The expedition was halted: {e!r}"[:300])
            return None

    def stop(self) -> None:
        self._stop = True

    def start(self) -> None:
        c, w = self.c, self.w
        tr, ho = int(w.mask("train").sum()), int(w.mask("holdout").sum())
        self._emit(actor="system", action="quest_start", line=f"Campaign {c.letter}: {c.title}", result={
            "campaign": {"id": c.id, "letter": c.letter, "title": c.title, "question": c.question, "drug": c.drug,
                         "comparator": c.comparator, "population": c.population, "target": c.outcomes[0].label,
                         "outcomes": [{"key": o.key, "label": o.label} for o in c.outcomes],
                         "sites": [{"name": n, "rural": r} for n, r in SITES], "patients": c.n,
                         "split": {"train": tr, "holdout": ho, "vault2": c.n - tr - ho,
                                   "train_end_day": TRAIN_END, "holdout_end_day": HOLDOUT_END}},
            "simulated": True, "hero": HERO,
            "gatekeeper": {**ARCHETYPES["SKEPTIC"], "baseline": c.comparator},
            "rules": {"levels": rules.LEVELS, "enemies": rules.ENEMIES, "abilities": rules.ABILITIES,
                      "d_max": rules.D_MAX, "score_weights": rules.SCORE_WEIGHTS, "score_rules": rules.SCORE_RULES,
                      "verdicts": rules.VERDICTS, "trap_labels": rules.TRAP_LABELS, "traps": rules.TRAPS,
                      "starting_hp": rules.STARTING_HP, "starting_credits": rules.STARTING_CREDITS},
            "archetypes": ARCHETYPES,
        })
        for s in c.scrolls:
            K = s.outcomes_searched * s.subgroups_searched
            a = Agent(s.key, s, J.ScrollState(outcome=s.outcome, design=s.design, K=K))
            self.agents[a.id] = a
            how = (f"Found in {s.origin}. As carried: exposure counted from the index date for anyone who ever filled "
                   f"a prescription; {K} outcome-and-subgroup combination{'s' if K > 1 else ''} in its search space.")
            self._emit(actor="system", action="recruit", agent=a, line=f"The Alchemist takes up {s.title}: \"{s.claim}\"",
                       explain=how, payload={"agent": a.public(w)})
        self._gate(0, f"I am the Warden of the Null. My baseline is {report._comp(c)}, with no drug effect at all. "
                      "Your scrolls must beat it on patients you have never seen.")

    # ---------- a level ----------

    def play_level(self, level: int) -> None:
        self.level = level
        info = rules.LEVELS[level]
        self._emit(actor="system", action="level_start", line=f"Level {level}: {info['name']}",
                   result={"level": level, **info, "d_max": rules.D_MAX[level], "trap_type": rules.TRAPS[level],
                           "enemies": rules.ENEMIES[level]})
        target = next((a for a in self._active() if a.archetype == "HYPE"), None) or (self._active() or [None])[0]
        if target:
            self._gate(level, self.c.gatekeeper[level].format(scroll=target.name))
        for a in self._active():
            self.decide(a, level)
        for a in self._active():
            a.m[level] = self.measure(a, level)
        for enemy in rules.ENEMIES[level]:
            fighters = self._active()
            if not fighters:
                continue
            self._emit(actor="judge", action="encounter", enemy=enemy["key"], line=f"{enemy['name']}: \"{enemy['attack']}\"",
                       result={"enemy": enemy, "boss": bool(enemy.get("boss"))})
            if enemy["key"] == "guardian":
                self._benchmark()
            for a in fighters:
                self.fight(a, level, enemy)
        self.after_level(level)

    def decide(self, a: Agent, level: int) -> None:
        menu = menu_for(a, level)
        brief = {"campaign": self.c.question, "scroll": a.name, "claim": a.claim, "level": rules.LEVELS[level]["name"],
                 "trap": rules.LEVELS[level]["trap"], "rule": rules.LEVELS[level]["rule"]}
        d: Decision = self.brain.choose(a, level, menu, brief)
        picks = [k for k in d.abilities if k in menu]
        cost = sum(rules.ABILITIES[k]["cost"] for k in picks)
        if cost > a.credits:  # a hard rule, not a choice
            picks, cost = [], 0
        a.credits -= cost
        a.spent += cost
        a.cast[level] = picks
        notes = [self.apply_ability(a, k) for k in picks]
        self._emit(actor="agent", action="decision", agent=a, cost=cost, line=d.line,
                   explain=" ".join(n for n in notes if n) or "No abilities cast for this scroll this level.",
                   payload={"abilities": picks, "source": d.source, "menu": list(menu),
                            "decision": {"abilities": picks, "line": d.line}})

    def apply_ability(self, a: Agent, k: str) -> str:
        st = a.st
        if k in rules.M_ABILITY:
            rule, m = rules.M_ABILITY[k]
            a.mult[rule] = min(a.mult.get(rule, 1.0), m)
            a.buffs.append("EXPLORATORY")
            return f"Exploratory Claim: Rule 1 damage multiplied by {m:.2f}."
        if k == "DENOISE":
            st.denoised = True
            a.buffs.append("DE-NOISED")
            return "De-Noise Filter: affiliate-coded posts stripped and reposts collapsed before counting."
        if k == "SPECIES_GUARD":
            st.species_guard = True
            a.buffs.append("SPECIES GUARD")
            return "Species Guard: only human evidence counts toward the species term, if there is any."
        if k == "BIAS_DETECTION":
            a.buffs.append("CONFOUNDER-ADJUSTED")
            return ("Bias Detection: " + ", ".join(COVARIATE_LABELS[k2].lower() for k2 in COVARIATE_LABELS)
                    + " and site enter the model before the Phantom strikes.")
        if k == "PREREGISTER":
            st.K = 1
            a.buffs.append("PREREGISTERED")
            return "Preregistered: one outcome, the whole population, declared before testing. K = 1."
        if k == "REPLICATION_SHIELD":
            st.replicated = True
            a.buffs.append("REPLICATION SHIELD")
            return f"Replication Shield: the analysis is re-run in all {len(SITES)} EHR sites."
        if k == "TEMPORAL_GUARD":
            st.design = "new_user"
            a.buffs.append("TIME-ZERO ALIGNED")
            return "Temporal Guard: new-user design; time before the first fill stays unexposed."
        if k == "ABLATION_STRIKE":
            keep, g = J.ablation_keeps_drug(self.w, st)
            st.ablated = not keep
            a.buffs.append("ABLATED" if st.ablated else "ABLATION-TESTED")
            return (f"Ablation Strike: the drug term did not lower validation loss (SS = {g['ss_oos']:+.4f}), so it was dropped."
                    if st.ablated else f"Ablation Strike: the drug term earned its place on the validation slice (SS = {g['ss_oos']:+.4f}).")
        return ""

    def measure(self, a: Agent, level: int) -> dict:
        w, s, st = self.w, a.scroll, a.st
        if level == 1:
            return J.level1(w, s, st)
        if level == 2:
            m = J.level2(w, s, st)
            if "BIAS_DETECTION" in a.cast.get(2, []):
                st.adjusted = True
            return m
        if level == 3:
            return J.level3(w, s, st)
        return J.level4(w, s, st)

    # ---------- one fight ----------

    def fight(self, a: Agent, level: int, enemy: dict) -> None:
        if not a.active:
            return
        out = self.judge(a, level, enemy)
        term = enemy["term"]
        delta, raw = 0, out.get("raw", 0.0)
        m_ab = 1.0
        if term:
            rule = rules.RULE_OF[term]
            m_ab = a.mult.get(rule, 1.0)
            a.raw[rule] = a.raw.get(rule, 0.0) + raw
            total = J.clamp_hp(a.raw[rule], m_ab, rules.RULE_LEVEL[rule])
            hit = total - a.applied.get(rule, 0)
            a.applied[rule] = total
            delta = -hit
            a.damage[term] = a.damage.get(term, 0) + hit
            a.traps[term] = raw < 1.0 if term != "final" else bool(out.get("eureka"))
        heal = out.get("heal", 0)
        before = a.hp
        a.hp = max(0, min(rules.STARTING_HP, a.hp + delta + heal))
        applied = a.hp - before
        enc = self._encounter(a, level, enemy, out, raw, m_ab, applied)
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
        if a.hp <= 0 and a.active:
            a.status, a.verdict = "shattered", "SHATTERED"
            self._emit(actor="judge", action="shatter", agent=a, enemy=enemy["key"],
                       line=f"{a.name} shatters into ash before {enemy['name']}. The Alchemist walks on.",
                       explain=rules.VERDICTS["SHATTERED"])

    def judge(self, a: Agent, level: int, enemy: dict) -> dict:
        """The measurement and formula behind one enemy's attack on one scroll."""
        key, c, w = enemy["key"], self.c, self.w
        m = a.m[level]
        st = a.st
        olabel = report._lower(next(o.label for o in c.outcomes if o.key == st.outcome))
        if level == 1:
            by = m["by_platform"]
            stack = {"kind": "stack", "title": "Supporting posts by platform",
                     "rows": [{"label": p, "parts": [{"name": "organic", "value": v["organic"]},
                                                     {"name": "affiliate", "value": v["affiliate"]}]} for p, v in by.items()]}
            if key == "slime":
                return {"raw": 0.0, "line": f"{m['posts']} supporting posts scraped: " +
                        ", ".join(f"{p} {v['organic'] + v['affiliate']}" for p, v in by.items()) + ".",
                        "plain": "The Slime counts how loud the claim is. Loud is not the same as true.",
                        "text": f"posts = {m['posts']}", "latex": f"n_{{posts}} = {m['posts']}",
                        "numbers": {"posts": m["posts"], **{p: v["organic"] + v["affiliate"] for p, v in by.items()}},
                        "chart": stack}
            if key == "wisp":
                return {"raw": 0.0, "line": f"{m['reposts']} of {m['posts']} posts are reposts; the largest echo has {m['largest_echo']} copies.",
                        "plain": "Many posts retell the same few stories. Only independent stories count as evidence.",
                        "text": f"independent stories = {m['n_eff']}" + (" after de-noising" if m["denoised"] else ""),
                        "latex": f"N_{{eff}} = {m['n_eff']}",
                        "numbers": {"reposts": m["reposts"], "largest_echo": m["largest_echo"], "n_eff": m["n_eff"]},
                        "chart": {"kind": "stack", "title": "Original stories vs reposts",
                                  "rows": [{"label": "Posts", "parts": [{"name": "original", "value": m["posts"] - m["reposts"]},
                                                                        {"name": "repost", "value": m["reposts"]}]}]}}
            d = J.d_l1(m)
            if key == "siren":
                raw = d["affiliate"]
                return {"raw": raw, "line": f"Affiliate skew phi = {m['phi']:.2f}" + (" after the De-Noise Filter" if m["denoised"] else "") + ".",
                        "plain": (f"{m['phi'] * 100:.0f}% of the supporting posts carry a discount code or sponsorship."
                                  if m["phi"] > 0 else "No sponsored posts are left in the count."),
                        "text": f"15 x phi = 15 x {m['phi']:.3f} = {raw:.2f}", "latex": f"15\\varphi_{{aff}} = 15 \\times {m['phi']:.3f} = {raw:.2f}",
                        "numbers": {"phi_affiliate": m["phi"], "posts_counted": m["posts_counted"]}, "chart": stack}
            if key == "bat":
                raw = d["neff"]
                return {"raw": raw, "line": f"N_eff = {m['n_eff']} independent stories (full credit at {rules.N_EFF_FULL}).",
                        "plain": (f"Only {m['n_eff']} independent stories stand behind the claim." if raw else
                                  f"{m['n_eff']} independent stories: enough to take seriously, not enough to prove anything."),
                        "text": f"15 x max(0, 1 - {m['n_eff']} / 30) = {raw:.2f}",
                        "latex": f"15\\max(0, 1 - {m['n_eff']}/30) = {raw:.2f}", "numbers": {"n_eff": m["n_eff"]}}
        if level == 2:
            nv, ad = m["naive"], m["adjusted"]
            forest = {"kind": "forest", "title": f"Rate ratio for {olabel} (training cohort)", "ref": 1.0,
                      "rows": [{"label": "Naive", **_ci(nv)}, {"label": "Adjusted for confounders", **_ci(ad)}]}
            if key == "mimic":
                return {"raw": 0.0, "line": f"Naive rate ratio {nv['rr']:.2f} (p = {nv['p']:.2g}) from {nv['events']} events.",
                        "plain": f"Taken at face value, users have {abs(1 - nv['rr']) * 100:.0f}% {'fewer' if nv['rr'] < 1 else 'more'} events.",
                        "text": f"log RR_naive = {nv['beta']:.3f} (se {nv['se']:.3f})", "latex": f"\\hat\\beta_{{naive}} = {nv['beta']:.3f}",
                        "numbers": {"rr_naive": nv["rr"], "p": nv["p"], "events": nv["events"]}}
            if key == "spider":
                worst = max(m["balance"], key=lambda x: abs(x["smd"]))
                return {"raw": 0.0, "line": f"Users differ most in {COVARIATE_LABELS[worst['covariate']].lower()} (SMD {worst['smd']:+.2f}).",
                        "plain": "Peptide users are not like comparators before they ever take a dose.",
                        "text": "SMD = (mean_users - mean_comparators) / pooled sd",
                        "latex": "SMD = \\frac{\\bar x_1 - \\bar x_0}{s_p}",
                        "numbers": {x["covariate"]: x["smd"] for x in m["balance"]},
                        "chart": {"kind": "bars", "title": "Standardized mean difference, users vs comparators",
                                  "bars": [{"label": COVARIATE_LABELS[x["covariate"]], "value": round(x["smd"], 3)} for x in m["balance"]]}}
            d = J.d_l2(m, st.species_guard, st.adjusted)
            if key == "rat":
                raw = d["rodent"]
                guarded = st.species_guard and m["human"] > 0
                return {"raw": raw, "line": f"tau_rodent = {m['tau']:.2f}: {m['rodent']} rodent, {m['in_vitro']} in vitro, {m['human']} human papers"
                                            + (" (Species Guard)" if guarded else "") + ".",
                        "plain": ("Most of the supporting evidence never involved a human." if m["tau"] > 0.5 else
                                  "Most of the supporting evidence is human." if m["tau"] < 0.5 else "Half the evidence is non-human.")
                                 + (" The guard counts only the human studies." if guarded else
                                    " The guard found no human study to stand on." if st.species_guard else ""),
                        "text": f"22 x tau = 22 x {m['tau']:.3f}" + (f" x {rules.SPECIES_GUARD_M}" if guarded else "") + f" = {raw:.2f}",
                        "latex": f"22\\tau_{{rodent}} = 22 \\times {m['tau']:.3f} = {22 * m['tau']:.2f}",
                        "numbers": {"tau_rodent": m["tau"], "human": m["human"], "rodent": m["rodent"], "in_vitro": m["in_vitro"]},
                        "chart": {"kind": "stack", "title": "Supporting papers by species",
                                  "rows": [{"label": "Papers", "parts": [{"name": "human", "value": m["human"]},
                                                                         {"name": "rodent", "value": m["rodent"]},
                                                                         {"name": "in vitro", "value": m["in_vitro"]}]}]}}
            if key == "phantom":
                raw = d["confound"]
                return {"raw": raw, "heal": rules.BIAS_HEAL if st.adjusted else 0,
                        "line": f"Rate ratio {nv['rr']:.2f} naive vs {ad['rr']:.2f} adjusted: shift = {m['shift']:.2f}"
                                + (" (Bias Detection: +5 HP)" if st.adjusted else "") + ".",
                        "plain": (f"Adjusting for who takes the peptide moves the effect {m['shift'] * 100:.0f}% of the way back toward nothing."
                                  if ad["beta"] * nv["beta"] > 0 and abs(ad["beta"]) < abs(nv["beta"]) else
                                  f"Adjusting for who takes the peptide changes the effect by {m['shift'] * 100:.0f}%.")
                                 + (" The scroll had already adjusted, so the Phantom finds nothing to exploit." if st.adjusted else ""),
                        "text": f"20 x min(1, |{nv['beta']:.3f} - {ad['beta']:.3f}| / |{nv['beta']:.3f}|) = {20 * m['shift']:.2f}"
                                + (" -> 0 (Bias Detection)" if st.adjusted else ""),
                        "latex": f"20\\min(1, \\frac{{|{nv['beta']:.3f} - {ad['beta']:.3f}|}}{{|{nv['beta']:.3f}|}}) = {20 * m['shift']:.2f}",
                        "numbers": {"rr_naive": nv["rr"], "rr_adjusted": ad["rr"], "shift": m["shift"], "p_adjusted": ad["p"]},
                        "chart": forest}
        if level == 3:
            d = J.d_l3(m)
            if key == "knight":
                raw, b = d["sidak"], m["best"]
                olab = report._lower(next(o.label for o in c.outcomes if o.key == b["outcome"]))
                return {"raw": raw, "line": f"Best of K = {m['K']}: {olab}, {b['subgroup']}, p_raw = {m['p_raw']:.2g}; Sidak p_corr = {m['p_corr']:.2g}.",
                        "plain": ("Even after paying for every test it ran, the effect is unlikely to be chance."
                                  if not raw else "Once every subgroup and outcome it tried is counted, the best one could be chance."),
                        "text": f"p_corr = 1 - (1 - {m['p_raw']:.3g})^{m['K']} = {m['p_corr']:.3g}; 20 x I(p_corr > 0.05) = {raw:.0f}",
                        "latex": f"p_{{corr}} = 1 - (1 - {m['p_raw']:.3g})^{{{m['K']}}} = {m['p_corr']:.3g}",
                        "numbers": {"K": m["K"], "p_raw": m["p_raw"], "p_corr": m["p_corr"]}}
            if key == "sentinel":
                raw = d["hlab"]
                top = max(m["labs"].items(), key=lambda kv: kv[1]) if m["labs"] else ("none", 0)
                total = sum(m["labs"].values()) or 1
                return {"raw": raw, "line": f"H_lab = {m['h_lab']:.2f}; the largest source holds {top[1] / total * 100:.0f}% of the evidence"
                                            + (f"; {len(m['replicating'])} EHR sites replicated" if m["shielded"] else "") + ".",
                        "plain": ("The evidence comes overwhelmingly from one lab." if m["h_lab"] > 0.5 else
                                  "The evidence is spread across independent sources.") +
                                 (" Replicating sites count as independent labs." if m["shielded"] and m["replicating"] else ""),
                        "text": f"H = sum of squared source shares = {m['h_lab']:.3f}; 20 x H = {raw:.2f}",
                        "latex": f"20 H_{{lab}} = 20 \\times {m['h_lab']:.3f} = {raw:.2f}",
                        "numbers": {"h_lab": m["h_lab"], "sources": len(m["labs"]), "replicating_sites": len(m["replicating"])},
                        "chart": {"kind": "bars", "title": "Share of the evidence by lab or replicating site",
                                  "bars": [{"label": k, "value": round(v / total, 3)} for k, v in
                                           sorted(m["labs"].items(), key=lambda kv: -kv[1])]}}
            if key == "wraith":
                n_rep = len(m["replicating"])
                return {"raw": 0.0, "line": f"Effect replicated (p < 0.05, same direction) in {n_rep} of {len(SITES)} sites.",
                        "plain": ("Every site tells the same story." if n_rep == len(SITES) else
                                  "No site confirms it on its own." if n_rep == 0 else "Some sites agree, others do not."),
                        "text": "per-site log rate ratio, scroll's current design",
                        "latex": "\\hat\\beta_s,\\; s = 1..5",
                        "numbers": {x["site"]: x["rr"] for x in m["sites"]},
                        "chart": {"kind": "forest", "title": f"Rate ratio for {olabel} in each EHR site", "ref": 1.0,
                                  "rows": [{"label": x["site"] + (" (rural)" if x["rural"] else ""), **_ci(x)} for x in m["sites"]]}}
            if key == "chimera":
                raw = d["rct"]
                return {"raw": raw, "line": f"Completed human RCTs in the registry for this claim: {m['n_rct']}.",
                        "plain": ("No completed human trial has ever tested this claim." if raw else
                                  "At least one completed human trial exists, so the claim is not built on observation alone."),
                        "text": f"25 x I(N_RCT = 0) = 25 x {int(m['n_rct'] == 0)} = {raw:.0f}",
                        "latex": f"25 \\cdot I(N_{{RCT}} = {m['n_rct']} = 0) = {raw:.0f}",
                        "numbers": {"n_rct": m["n_rct"]}}
        if level == 4:
            if key == "titan":
                return {"raw": 0.0, "line": (f"{m['immortal_share'] * 100:.0f}% of the 'treated' person-time came before the first fill."
                                             if m["l_time"] else "Exposure starts at the first fill: no waiting time is counted as treated."),
                        "plain": ("Patients had to stay well long enough to fill a prescription, and that wait was credited to the drug."
                                  if m["l_time"] else "The design is new-user, time-zero aligned."),
                        "text": f"immortal share = {m['immortal_share']:.3f}", "latex": f"L_{{time}} = {m['l_time']}",
                        "numbers": {"immortal_share": m["immortal_share"], "l_time": m["l_time"]}}
            if key == "chronolock":
                raw = J.d_chrono(m)
                return {"raw": raw, "line": (f"Rate ratio {m['rr_current']:.2f} as carried vs {m['rr_purged']:.2f} with immortal time purged: "
                                             f"Delta_purge = {m['delta_purge']:.2f}." if m["l_time"] else
                                             f"Time-zero aligned already: rate ratio {m['rr_current']:.2f}, nothing to purge."),
                        "plain": (f"Counting the wait before the first fill made the drug look {m['delta_purge'] * 100:.0f}% stronger than it is."
                                  if m["l_time"] else "No immortal time."),
                        "text": f"35 x {m['l_time']} + 25 x {m['delta_purge']:.3f} = {raw:.2f}",
                        "latex": f"35 \\cdot {m['l_time']} + 25 \\times {m['delta_purge']:.3f} = {raw:.2f}",
                        "numbers": {"rr_current": m["rr_current"], "rr_purged": m["rr_purged"], "l_time": m["l_time"],
                                    "delta_purge": m["delta_purge"]},
                        "chart": {"kind": "forest", "title": f"Rate ratio for {olabel}: as carried vs time-zero aligned", "ref": 1.0,
                                  "rows": [{"label": "As carried", "est": round(m["rr_current"], 4)},
                                           {"label": "Immortal time purged", "est": round(m["rr_purged"], 4)}]}}
            if key == "guardian":
                raw, eureka = J.d_final(m)
                a.eureka = eureka
                ob, pr = m["observed"], m["predicted"]
                return {"raw": raw, "heal": rules.EUREKA_HEAL if eureka else 0, "eureka": eureka,
                        "line": f"SS_oos = {m['ss_oos']:+.4f} on {m['matched_pairs']} matched holdout pairs; paired p = {m['p_dm']:.3g}"
                                + (". Eureka! +10 HP" if eureka else "."),
                        "plain": (f"Using this scroll's effect predicted unseen patients {m['ss_oos'] * 100:.1f}% better than the comparator, "
                                  "and that is unlikely to be luck." if eureka else
                                  "It predicted unseen patients no better than the comparator." if m["ss_oos"] >= -rules.SS_MARGIN else
                                  f"Its effect made predictions {abs(m['ss_oos']) * 100:.1f}% worse than assuming no drug effect at all."),
                        "text": f"SS = 1 - {m['loss_scroll']:.5f} / {m['loss_comparator']:.5f} = {m['ss_oos']:.4f}; paired p = {m['p_dm']:.3g}; D_final = {raw:.1f}",
                        "latex": f"SS_{{oos}} = 1 - \\frac{{{m['loss_scroll']:.5f}}}{{{m['loss_comparator']:.5f}}} = {m['ss_oos']:.4f}",
                        "numbers": {"ss_oos": m["ss_oos"], "p_dm": m["p_dm"], "matched_pairs": m["matched_pairs"],
                                    "loss_scroll": m["loss_scroll"], "loss_comparator": m["loss_comparator"],
                                    "rr_used": math.exp(m["beta_used"])},
                        "chart": {"kind": "grouped", "title": "Vaulted holdout, matched: one-year risk observed vs predicted",
                                  "groups": [{"label": "Peptide users", "values": {"observed": ob["treated"], "scroll": pr["scroll_treated"], "baseline": pr["baseline_treated"]}},
                                             {"label": "Comparators", "values": {"observed": ob["comparator"], "scroll": pr["scroll_comparator"], "baseline": pr["baseline_comparator"]}}]}}
        return {"raw": 0.0, "line": "Not applicable.", "plain": "Nothing to test.", "text": "n/a", "latex": "\\text{n/a}", "numbers": {}}

    def _benchmark(self) -> None:
        self.baseline = {"comparator": self.c.comparator}
        self._gate(4, f"The vault opens. My benchmark is {report._comp(self.c)} with no drug effect, fitted only on the "
                      "training years and matched patient for patient on the holdout.", action="benchmark")

    def _gate(self, level: int, line: str, action: str = "gatekeeper") -> None:
        self._emit(actor="system", action=action, line=f"Gatekeeper: \"{line}\"",
                   result={"speaker": "gatekeeper", "text": line, "level": level})

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

    # ---------- internals ----------

    def _active(self) -> list[Agent]:
        return [a for a in self.agents.values() if a.active]

    def _encounter(self, a: Agent, level: int, enemy: dict, out: dict, raw: float, m_ab: float, applied: int) -> dict:
        """The PepEncounterTelemetry record."""
        self._enc += 1
        cast = [k for lv in a.cast.values() for k in lv]
        action = next((k for k in ENEMY_ACTION.get(enemy["key"], ()) if k in cast), "NONE")
        return {
            "encounterId": f"E{self._enc:03d}", "campaignType": self.c.id, "level": level,
            "enemyName": enemy["name"], "trapType": rules.TRAPS[level], "scrollId": a.id, "scrollTitle": a.name,
            "heroAction": action, "biostatMetrics": report.biostat(a),
            "combatResolution": {"rawDamage": round(raw, 3), "abilityMultiplier": m_ab, "clampedHpDelta": applied,
                                 "executedFormulaLatex": out.get("latex", ""), "plainEnglishVerdict": out["plain"]},
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


ENEMY_ACTION = {"siren": ("DENOISE", "EXPLORATORY_CLAIM"), "bat": ("DENOISE", "EXPLORATORY_CLAIM"),
                "rat": ("SPECIES_GUARD",), "phantom": ("BIAS_DETECTION",), "knight": ("PREREGISTER",),
                "sentinel": ("REPLICATION_SHIELD",), "wraith": ("REPLICATION_SHIELD",),
                "chronolock": ("TEMPORAL_GUARD",), "guardian": ("ABLATION_STRIKE",)}


def _ci(e: dict) -> dict:
    lo, hi = e["beta"] - 1.96 * e["se"], e["beta"] + 1.96 * e["se"]
    return {"est": round(e["rr"], 4), "lo": round(math.exp(lo), 4), "hi": round(math.exp(hi), 4)}


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

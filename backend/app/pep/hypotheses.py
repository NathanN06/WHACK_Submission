"""The Scribe: forms 2 to 6 hypothesis scrolls for a campaign from the REAL evidence in data/pep_evidence.duckdb.

Claude (or, without an API key, a deterministic script) writes each scroll as a TYPED claim: which outcome, which
direction (lowers or raises the event), which subgroup the cohort records, which evidence topic it rests on, how it
was found (its archetype), the bias its author fears and what result would falsify it, plus the words (title, claim,
origin). The Judge tests exactly the typed claim, so the words must describe it: they may not carry a measured
statistic, an effect size, another time window or a population the typed subgroup does not encode (textpolicy.py).
Every entry is checked on its own and a rejected one is recorded with its reason; the script fills the gap.
Two entries that would be the same study (same outcome, subgroup, direction and archetype) are duplicates.

The scroll's evidence is attached by code, copied straight from the database with its identifiers (PMID, DOI,
NCT id), the query that found it and when: the real papers (species, lab) for Levels II and III, and the count of
completed randomized trials for Level III. The social corpus and the patient cohort stay simulated (world.py).
"""

from __future__ import annotations

import dataclasses
import hashlib
import random
from collections import deque
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, ValidationError, field_validator

from . import textpolicy as TP
from .world import SUBGROUPS, Campaign, Literature, Scroll

DB_PATH = Path(__file__).resolve().parents[3] / "data" / "pep_evidence.duckdb"
MIN_SCROLLS, MAX_SCROLLS = 2, 6
ARCHETYPE_ORDER = ["HYPE", "PIONEER", "PREPRINT"]
PROMPT_VERSION = "scribe-2"
THREATS = ("confounding_by_indication", "immortal_time_bias", "site_clustering", "outcome_multiplicity", "unknown")
ESTIMAND = "one-year event rate ratio, new users vs the active comparator"

# Evidence topics per campaign (scripts/download_pep_evidence.py) and the default topic for each outcome.
TOPICS = {
    "A": {"alcohol": "GLP-1 drugs and alcohol use", "opioid": "GLP-1 drugs and opioid use",
          "nicotine": "GLP-1 drugs and smoking"},
    "B": {"bpc157": "BPC-157", "tb500": "TB-500 / thymosin beta-4"},
    "C": {"ghkcu": "GHK-Cu copper peptide", "gh_secretagogue": "Ipamorelin / CJC-1295"},
    "D": {"naion": "GLP-1 drugs and NAION", "retinopathy": "GLP-1 drugs and diabetic retinopathy"},
}
DEFAULT_TOPIC = {"A": {}, "B": {}, "C": {"frailty": "gh_secretagogue", "epiage": "gh_secretagogue"},
                 "D": {"vision": "naion"}}
SPECIES = {"human": "human", "mixed": "human", "animal": "rodent", "in_vitro": "in vitro"}   # unknown is left out

# Variety: each call shows the Scribe a fresh random sample of the real papers, a few random angles to explore,
# and the titles it already wrote for this campaign, so a new quest does not repeat the last one.
N_EXAMPLES = 6
ANGLES = ["a specific subgroup the cohort records (age under or over fifty, sex, baseline severity)",
          "the biological mechanism", "a mechanism-based prediction of which way the effect goes",
          "a surprising or contrarian twist", "what one particular paper in the sample suggests",
          "what patients say online", "a safety or trade-off framing",
          "an indirect route (weight loss, mood, appetite, sleep)", "the comparison against the comparator drug"]
_RECENT: dict[str, deque] = {}   # campaign letter -> titles the Scribe wrote lately (this server process)


# ---------------------------------------------------------------- the real evidence

def _columns(con, table: str) -> set[str]:
    return {r[0] for r in con.execute("SELECT column_name FROM duckdb_columns() WHERE table_name = ?", [table]).fetchall()}


def _select(con, table: str, wanted: list[str], where: str, args: list) -> list[dict]:
    """Rows as dicts with every wanted column; a column an older database lacks comes back as None."""
    have = _columns(con, table)
    cols = [c for c in wanted if c in have]
    rows = con.execute(f"SELECT {', '.join(cols)} FROM {table} WHERE {where}", args).fetchall()
    return [{**{c: None for c in wanted}, **dict(zip(cols, r))} for r in rows]


def load_evidence(letter: str, db_path: Path | None = None) -> dict | None:
    """Per topic: the stored papers and trials with their identifiers, read as they are. None without a database."""
    db_path = db_path or DB_PATH
    if not Path(db_path).exists():
        return None
    import duckdb
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        out = {}
        for topic, label in TOPICS.get(letter, {}).items():
            papers = _select(con, "pep_papers", ["title", "pub_year", "design", "species", "authors", "url", "pmid", "doi",
                                                 "source_id", "journal"], "campaign = ? AND topic = ?", [letter, topic])
            queries = _select(con, "pep_queries", ["source", "query", "hit_count", "stored", "fetched_at"],
                              "campaign = ? AND topic = ?", [letter, topic])
            trials = _select(con, "pep_trials", ["nct_id", "title", "status", "allocation", "has_results", "phases",
                                                 "enrollment", "url"], "campaign = ? AND topic = ?", [letter, topic])
            found = next((q["hit_count"] for q in queries if q["source"] == "europepmc"), 0) or 0
            records = [{"title": p["title"], "year": p["pub_year"], "design": p["design"], "species": SPECIES[p["species"]],
                        "lab": _lab(p["authors"]), "url": p["url"], "pmid": p["pmid"], "doi": p["doi"],
                        "source_id": p["source_id"], "journal": p["journal"]}
                       for p in papers if p["species"] in SPECIES]
            rcts = [t for t in trials if t["status"] == "COMPLETED" and t["allocation"] == "RANDOMIZED"]
            out[topic] = {"label": label, "papers_found": found, "papers_stored": len(papers), "records": records,
                          "species": {k: sum(r["species"] == k for r in records) for k in ("human", "rodent", "in vitro")},
                          "unknown_species": len(papers) - len(records),
                          "designs": _tally(p["design"] for p in papers),
                          "trials": len(trials), "completed_rcts": len(rcts), "trial_records": rcts,
                          "queries": [{k: (str(v) if k == "fetched_at" and v is not None else v) for k, v in q.items()}
                                      for q in queries],
                          "examples": [f"{p['title']} ({p['pub_year']}, {p['design']})" for p in papers[:6]]}
        faers = _select(con, "pep_faers", ["topic", "drug_group", "reactions", "drug_and_reaction", "drug_total",
                                           "reaction_total", "all_reports", "fetched_at"], "campaign = ?", [letter])
        for f in faers:
            f["fetched_at"] = str(f["fetched_at"]) if f["fetched_at"] is not None else None
        return {"topics": out, "faers": faers}
    finally:
        con.close()


def _lab(authors: str | None) -> str:
    """A paper's lab, approximated by its first author."""
    first = (authors or "").split(",")[0].strip()
    return first or "Unknown lab"


def _tally(items) -> dict:
    out: dict = {}
    for x in items:
        out[x] = out.get(x, 0) + 1
    return out


# ---------------------------------------------------------------- what the Scribe writes

class _Hypothesis(BaseModel):
    title: str = Field(min_length=3, max_length=80)
    claim: str = Field(min_length=10, max_length=320)
    outcome: str
    topic: str
    archetype: str
    origin: str = Field(min_length=3, max_length=260)
    direction: Literal["lowers", "raises"]
    subgroup: str = "everyone"
    threat: Literal[THREATS] = "unknown"  # type: ignore[valid-type]
    falsifier: str = Field("", max_length=260)
    horizon_days: Literal[365] = 365                     # a typed design parameter: the one window the cohort follows
    comparator: Literal["active_comparator"] = "active_comparator"

    @field_validator("title", "claim", "origin", "falsifier", mode="before")
    @classmethod
    def _trim(cls, v, info):
        """A wordy field is cut at a word boundary rather than throwing away the whole entry."""
        limit = {"title": 80, "claim": 320, "origin": 260, "falsifier": 260}[info.field_name]
        if isinstance(v, str) and len(v) > limit:
            v = v[:limit].rsplit(" ", 1)[0].rstrip(" ,;:-")
        return v


class _Batch(BaseModel):
    hypotheses: list[dict]


SYSTEM = """You are the Scribe of the Hypothesis Gauntlet. From a summary of REAL published evidence, propose exactly {n}
distinct, testable hypotheses for the campaign question: {question}
Drug: {drug}. Comparator: {comparator}. Population: {population}.
A Statistical Judge tests each hypothesis on a simulated cohort as a TYPED claim: the one-year rate of the outcome event
in new users of the drug versus the comparator, in one subgroup the cohort records, in the direction you predict.
Your words must describe exactly that typed claim. For each hypothesis give:
  outcome:   one key from {outcomes} (each is an adverse event, so "lowers" is a benefit and "raises" a harm)
  direction: "lowers" or "raises"
  subgroup:  one of {subgroups} ("everyone" unless a subgroup is the point; if it is, name it in the claim)
  topic:     one evidence topic key from {topics}
  archetype: how the claim was found. HYPE = a crowd claim found on social media by searching many outcomes and
             subgroups; PIONEER = a careful, mechanistic, clinically framed claim; PREPRINT = an optimistic claim from a
             small study or animal work. Use a mix, and let the evidence suggest which fits.
  threat:    the bias its author fears most: {threats}
  title:     a plain-English headline, at most eight words, e.g. "Semaglutide cuts alcohol relapse" (no fantasy names)
  claim:     one sentence (under forty words) stating what the drug does to that outcome versus the comparator
  origin:    where such a claim comes from, grounded in the evidence summary (under twenty-five words)
  falsifier: in words, what result would show the claim is wrong
Rules for the words: no numbers, percentages, p-values, ratios or effect sizes (not even "halves" or "doubles"), no time
window other than one year, and no population other than the typed subgroup. Clinical names with digits are fine (GLP-1,
type 2 diabetes, IL-6, Phase 3). Be inventive: explore these angles this time: {angles}. Each hypothesis must be a different study: never repeat
the same outcome, subgroup and direction with the same archetype, and do not reword any title in "already_written".
Reply with JSON only: {{"hypotheses": [{{"title": ..., "claim": ..., "outcome": ..., "direction": ..., "subgroup": ...,
"topic": ..., "archetype": ..., "threat": ..., "origin": ..., "falsifier": ...}}]}}"""


def direction_of(h: _Hypothesis) -> int:
    return -1 if h.direction == "lowers" else 1


def question_key(c: Campaign, outcome: str, subgroup: str, direction: int) -> str:
    """The normalized research question: what is compared, in whom, on what, which way, measured how."""
    return f"{c.id}:{outcome}:{subgroup}:{'lowers' if direction < 0 else 'raises'}:vs-active-comparator:1y-rate-ratio"


def study_key(qkey: str, archetype: str) -> str:
    """The same question studied the same way (same search and design plan) is the same study: a duplicate."""
    return f"{qkey}|{archetype}"


def hypothesis_id(c: Campaign, claim: str, qkey: str, archetype: str, version: int = 1) -> str:
    return "H-" + hashlib.sha256(f"{c.id}|{claim}|{qkey}|{archetype}|v{version}".encode()).hexdigest()[:10]


def check(h: _Hypothesis, c: Campaign, world=None, used: set | None = None) -> str | None:
    """Why an entry is rejected, or None. Pure, deterministic checks against the campaign and the cohort."""
    if h.outcome not in {o.key for o in c.outcomes}:
        return f"outcome {h.outcome!r} is not one this campaign measures"
    if h.topic not in TOPICS.get(c.letter, {}):
        return f"evidence topic {h.topic!r} is not one this campaign has"
    if h.archetype not in ARCHETYPE_ORDER:
        return f"archetype {h.archetype!r} is not HYPE, PIONEER or PREPRINT"
    if h.subgroup not in SUBGROUPS:
        return f"subgroup {h.subgroup!r} is not a variable this cohort records"
    if world is not None:
        sup = world.support(h.subgroup)
        if not sup["supported"]:
            return f"subgroup {h.subgroup!r} is too sparse to test: {sup['reason']}"
    for name in ("title", "claim", "origin", "falsifier"):
        why = TP.check_scribe(getattr(h, name), h.subgroup)
        if why:
            return f"{name} {why}"
    key = study_key(question_key(c, h.outcome, h.subgroup, direction_of(h)), h.archetype)
    if used is not None and key in used:
        return "duplicate study: same outcome, subgroup, direction and archetype as another scroll"
    return None


def _summary(c: Campaign, ev: dict | None, rng: random.Random | None = None, supported: list | None = None) -> dict:
    """What the Scribe reads: the counts copied from the database (no statistics) and a random sample of papers."""
    rng = rng or random.Random()
    recent = list(_RECENT.get(c.letter, ()))
    base = {"supported_subgroups": supported or ["everyone"], "already_written": recent,
            "estimand": ESTIMAND, "horizon_days": 365}
    if not ev:
        return {**base, "note": "No real evidence database was found; write hypotheses from the campaign question."}
    topics = {}
    for k, v in ev["topics"].items():
        t = {key: v[key] for key in ("label", "papers_found", "species", "unknown_species", "designs",
                                     "trials", "completed_rcts")}
        recs = v["records"]
        t["examples"] = ([f"{r['title']} ({r['year']}, {r['design']}, {r['species']})"
                          for r in rng.sample(recs, min(N_EXAMPLES, len(recs)))] if recs else v["examples"])
        topics[k] = t
    return {**base, "topics": topics, "faers_adverse_event_reports": ev["faers"],
            "faers_note": "spontaneous report counts: no denominator, not evidence that the drug causes anything"}


def scripted(c: Campaign, n: int, world=None, used: set | None = None) -> list[tuple[_Hypothesis, bool]]:
    """Without Claude: the campaign's hand-written scrolls first (curated: one question, three methods, kept as
    written), then plainly worded, clinically framed claims: each outcome in the campaign's direction, one contrarian
    claim, then subgroups, each a new study passing the Scribe's checks. Returns (hypothesis, curated) pairs."""
    used = set() if used is None else used
    out: list[tuple[_Hypothesis, bool]] = []
    for i, s in enumerate(c.scrolls[:n]):
        h = _Hypothesis.model_construct(title=s.title, claim=s.claim, outcome=s.outcome, archetype=s.archetype,
                                        topic=_default_topic(c, s.outcome, i, s.claim), origin=s.origin[:260] or "the campaign brief",
                                        direction="lowers" if (s.direction or c.effect_direction) < 0 else "raises",
                                        subgroup=s.subgroup, threat="unknown", falsifier="", horizon_days=365,
                                        comparator="active_comparator")
        used.add(study_key(question_key(c, h.outcome, h.subgroup, direction_of(h)), h.archetype))
        out.append((h, True))
    verb = "lowers" if c.effect_direction < 0 else "raises"
    opposite = "raises" if verb == "lowers" else "lowers"
    comp = c.comparator.replace(" (active comparator)", "")
    who = {"everyone": "", "50 and over": "Among patients aged 50 and over, ", "women": "In women, ",
           "higher severity": "In patients with more severe disease, ", "under 50": "Among patients under 50, ",
           "men": "In men, ", "lower severity": "In patients with milder disease, "}
    # each outcome in the campaign's direction, then one contrarian claim (both directions get a hearing), then subgroups
    candidates = ([(o, "everyone", verb) for o in c.outcomes] + [(c.outcomes[0], "everyone", opposite)]
                  + [(o, g, verb) for g in ("50 and over", "women", "higher severity", "under 50", "men", "lower severity")
                     for o in c.outcomes])
    i = len(out)
    for o, g, way in candidates:
        if len(out) >= n:
            break
        arch = "PIONEER"   # plainly worded, clinically framed claims: the hand-written HYPE and PREPRINT are the foils
        label = o.label if o.label[1:2].isupper() else o.label[0].lower() + o.label[1:]
        label = label.replace(" within a year", "")
        start = who[g]
        drug = c.drug if not start else c.drug[0].lower() + c.drug[1:] if not c.drug[:2].isupper() else c.drug
        claim = f"{start}taking {drug} {way} the risk of {label} compared with {comp}."
        claim = claim[0].upper() + claim[1:]
        title = f"The {o.key.capitalize()} Scroll" + ("" if g == "everyone" else f" ({g})") + \
                (" (contrarian)" if way != verb else "")
        h = _Hypothesis(title=title, archetype=arch,
                        claim=claim, outcome=o.key, topic=_default_topic(c, o.key, i), origin="the real literature summary",
                        direction=way, subgroup=g, threat="confounding_by_indication",
                        falsifier=f"The adjusted, time-zero analysis shows no reduction or a rise in {label}."
                        if way == "lowers" else f"The adjusted, time-zero analysis shows no rise or a fall in {label}.")
        if check(h, c, world, used) is None:
            used.add(study_key(question_key(c, h.outcome, h.subgroup, direction_of(h)), h.archetype))
            out.append((h, False))
            i += 1
    return out


def _default_topic(c: Campaign, outcome: str, i: int, claim: str = "") -> str:
    import re
    topics = list(TOPICS.get(c.letter, {}))
    if outcome in topics:
        return outcome
    named = [t for t in topics if any(w.lower() in claim.lower() for w in re.split(r" / | and ", TOPICS[c.letter][t])
                                      if len(w) > 3 and not w.lower().startswith("glp"))]
    if len(named) == 1:
        return named[0]
    return DEFAULT_TOPIC.get(c.letter, {}).get(outcome) or (topics[i % len(topics)] if topics else "")


def ask_claude(complete, c: Campaign, n: int, ev: dict | None, rng: random.Random | None = None,
               supported: list | None = None):
    """(raw entries or None, trace). Each entry is validated on its own by form()."""
    from ..llm import ask_traced
    rng = rng or random.Random()
    system = SYSTEM.format(n=n, question=c.question, drug=c.drug, comparator=c.comparator, population=c.population,
                           outcomes={o.key: o.label for o in c.outcomes}, topics=TOPICS.get(c.letter, {}),
                           subgroups=supported or SUBGROUPS, threats=" | ".join(THREATS),
                           angles="; ".join(rng.sample(ANGLES, 3)))
    reply, trace = ask_traced(complete, system, _summary(c, ev, rng, supported), _Batch, PROMPT_VERSION)
    return (reply.hypotheses if reply else None), trace


# ---------------------------------------------------------------- scrolls

def form(c: Campaign, n: int, complete=None, db_path: Path | None = None, world=None,
         incumbent: dict | None = None) -> tuple[list[Scroll], dict]:
    """2 to 6 scrolls for campaign c (the incumbent champion counts toward them) and a record of how they were formed."""
    n = max(MIN_SCROLLS, min(MAX_SCROLLS, int(n)))
    ev = load_evidence(c.letter, db_path or DB_PATH)
    supported = [g for g in SUBGROUPS if world is None or world.support(g)["supported"]]
    used: set = set()
    scrolls: list[Scroll] = []
    if incumbent is not None:
        inc = incumbent_scroll(c, incumbent, ev)
        used.add(study_key(inc.question_key, inc.archetype))
        scrolls.append(inc)
    slots = n - len(scrolls)
    chosen: list[tuple[_Hypothesis, str]] = []
    rejected: list[dict] = []
    trace = {"execution_mode": "SCRIPTED", "fallback_reason": "NO_API_KEY" if complete is None else None,
             "schema_validation": "NOT_RUN", "prompt_version": PROMPT_VERSION, "request_id": None}
    if complete is not None:
        raw, trace = ask_claude(complete, c, slots, ev, supported=supported)
        for k, entry in enumerate(raw or []):
            if len(chosen) >= slots:
                break
            try:
                h = _Hypothesis.model_validate(entry)
            except ValidationError as e:
                rejected.append({"index": k, "title": str((entry or {}).get("title", ""))[:80],
                                 "reason": "schema: " + "; ".join(f"{'.'.join(map(str, x['loc']))} {x['msg']}"
                                                                  for x in e.errors())[:240]})
                continue
            why = check(h, c, world, used)
            if why:
                rejected.append({"index": k, "title": h.title, "reason": why})
                continue
            used.add(study_key(question_key(c, h.outcome, h.subgroup, direction_of(h)), h.archetype))
            chosen.append((h, "SCRIBE_CLAUDE"))
        if chosen:
            _RECENT.setdefault(c.letter, deque(maxlen=18)).extend(h.title for h, _ in chosen)
        elif trace.get("execution_mode") == "LIVE_CLAUDE":
            trace = {**trace, "execution_mode": "SCRIPTED_FALLBACK", "fallback_reason": "ALL_ENTRIES_REJECTED"}
    if len(chosen) < slots:   # any slot Claude left empty (or every slot, without Claude) is filled by the script
        for h, curated in scripted(c, 2 * MAX_SCROLLS, world, set(used)):
            if len(chosen) >= slots:
                break
            key = study_key(question_key(c, h.outcome, h.subgroup, direction_of(h)), h.archetype)
            if key in used:   # the incumbent, or a study Claude already wrote
                continue
            used.add(key)
            chosen.append((h, "HAND_WRITTEN" if curated else "SCRIBE_SCRIPT"))
    for i, (h, mode) in enumerate(chosen):
        scrolls.append(_scroll(c, h, len(scrolls), ev, mode))
    claude = any(m == "SCRIBE_CLAUDE" for _, m in chosen)
    info = {"count": len(scrolls), "source": "claude" if claude else "script", "evidence": "real" if ev else "simulated",
            "execution": {**trace, "entries_rejected": len(rejected)}, "rejected": rejected,
            "incumbent": scrolls[0].hypothesis_id if incumbent is not None else None,
            "scrolls": [{"key": s.key, "hypothesis_id": s.hypothesis_id, "question_key": s.question_key,
                         "origin_mode": s.origin_mode, "subgroup": s.subgroup,
                         "direction": "lowers" if s.direction < 0 else "raises"} for s in scrolls],
            "topics": {k: {key: v[key] for key in ("label", "papers_found", "papers_stored", "species",
                                                   "unknown_species", "trials", "completed_rcts")}
                       for k, v in (ev or {}).get("topics", {}).items()},
            "faers": (ev or {}).get("faers", [])}
    return scrolls, info


def _scroll(c: Campaign, h: _Hypothesis, i: int, ev: dict | None, mode: str) -> Scroll:
    template = next(s for s in c.scrolls if s.archetype == h.archetype)
    topic = (ev or {}).get("topics", {}).get(h.topic)
    extra = _real(topic, h.topic)
    d = direction_of(h)
    qkey = question_key(c, h.outcome, h.subgroup, d)
    return dataclasses.replace(template, key=f"h{i + 1}", title=h.title, claim=h.claim, outcome=h.outcome,
                               origin=h.origin, direction=d, subgroup=h.subgroup, threat=h.threat, falsifier=h.falsifier,
                               hypothesis_id=hypothesis_id(c, h.claim, qkey, h.archetype), version=1, parent_id=None,
                               origin_mode=mode, question_key=qkey, **extra)


def _real(topic: dict | None, key: str) -> dict:
    """The real evidence that replaces a template's simulated papers and trial count, with its provenance."""
    if not topic:
        return {}
    return {"literature": Literature(records=topic["records"], queries=topic.get("queries"),
                                     trials=topic.get("trial_records")),
            "n_rct": topic["completed_rcts"], "evidence_topic": key, "evidence_real": True}


def stamp(c: Campaign, s: Scroll) -> Scroll:
    """Give a hand-written campaign scroll its typed direction, question key and immutable id."""
    d = s.direction or c.effect_direction
    qkey = question_key(c, s.outcome, s.subgroup, d)
    return dataclasses.replace(s, direction=d, question_key=qkey,
                               hypothesis_id=s.hypothesis_id or hypothesis_id(c, s.claim, qkey, s.archetype))


def incumbent_scroll(c: Campaign, record: dict, ev: dict | None) -> Scroll:
    """The previous champion, rebuilt exactly as it was formed (same id and version), to defend its title on a
    fresh cohort. Its history rides along as context; none of it is counted again as new evidence."""
    h = record["hypothesis"]
    template = next(s for s in c.scrolls if s.archetype == h["archetype"])
    topic = (ev or {}).get("topics", {}).get(h.get("topic") or "")
    extra = _real(topic, h.get("topic") or "")
    return dataclasses.replace(template, key="h1", title=h["title"], claim=h["claim"], outcome=h["outcome"],
                               origin=h["origin"], direction=h["direction"], subgroup=h["subgroup"],
                               threat=h.get("threat", "unknown"), falsifier=h.get("falsifier", ""),
                               hypothesis_id=h["hypothesis_id"], version=h.get("version", 1), parent_id=h.get("parent_id"),
                               origin_mode="INCUMBENT", question_key=h["question_key"],
                               incumbent={k: record.get(k) for k in ("status", "confirmations", "history", "since",
                                                                     "last_result", "manifest_ids")},
                               **extra)

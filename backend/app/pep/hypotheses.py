"""The Scribe: forms N hypothesis scrolls for a campaign from the REAL evidence in data/pep_evidence.duckdb.

Claude (or, without an API key, a deterministic script) writes each scroll's words: title, claim, origin,
which outcome it claims and which evidence topic it rests on, and how it was found (its archetype).
It never writes a number. The scroll's evidence is then attached by code, copied straight from the
database: the real papers behind its topic (species, lab) for Level II and III, and the count of completed
randomized trials for Level III. The social corpus and the patient cohort stay simulated (world.py).
"""

from __future__ import annotations

import dataclasses
import re
from pathlib import Path

from pydantic import BaseModel, Field

from .world import Campaign, Literature, Scroll

DB_PATH = Path(__file__).resolve().parents[3] / "data" / "pep_evidence.duckdb"
MAX_SCROLLS = 6
ARCHETYPE_ORDER = ["HYPE", "PIONEER", "PREPRINT"]

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

# Drug names that legitimately contain digits; anything else with a digit counts as a number.
_NAMES = re.compile(r"GLP-?1|BPC[- ]?157|TB-?500|CJC-?1295|GHK-Cu|SGLT-?2|DPP-?4|beta-?4|type 2|type II", re.I)
SPECIES = {"human": "human", "mixed": "human", "animal": "rodent", "in_vitro": "in vitro"}   # unknown is left out


# ---------------------------------------------------------------- the real evidence

def load_evidence(letter: str, db_path: Path = DB_PATH) -> dict | None:
    """Per topic: the stored papers and trial counts, read as they are. None if the database is missing."""
    if not Path(db_path).exists():
        return None
    import duckdb
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        out = {}
        for topic, label in TOPICS.get(letter, {}).items():
            papers = con.execute(
                "SELECT title, pub_year, design, species, authors, url FROM pep_papers "
                "WHERE campaign = ? AND topic = ?", [letter, topic]).fetchall()
            found = con.execute("SELECT hit_count FROM pep_queries WHERE campaign = ? AND topic = ? AND source = 'europepmc'",
                                [letter, topic]).fetchone()
            trials = con.execute(
                "SELECT count(*), count(*) FILTER (WHERE status = 'COMPLETED' AND allocation = 'RANDOMIZED') "
                "FROM pep_trials WHERE campaign = ? AND topic = ?", [letter, topic]).fetchone()
            records = [{"title": t, "year": y, "design": d, "species": SPECIES[s], "lab": _lab(a), "url": u}
                       for t, y, d, s, a, u in papers if s in SPECIES]
            out[topic] = {"label": label, "papers_found": found[0] if found else 0, "papers_stored": len(papers),
                          "records": records,
                          "species": {k: sum(r["species"] == k for r in records) for k in ("human", "rodent", "in vitro")},
                          "unknown_species": len(papers) - len(records),
                          "designs": _tally(d for _, _, d, _, _, _ in papers),
                          "trials": trials[0], "completed_rcts": trials[1],
                          "examples": [f"{t} ({y}, {d})" for t, y, d, *_ in papers[:6]]}
        faers = con.execute("SELECT topic, drug_group, reactions, drug_and_reaction, drug_total, reaction_total, "
                            "all_reports FROM pep_faers WHERE campaign = ?", [letter]).fetchall()
        return {"topics": out, "faers": [dict(zip(("topic", "drug_group", "reactions", "drug_and_reaction",
                                                    "drug_total", "reaction_total", "all_reports"), f)) for f in faers]}
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
    title: str = Field(min_length=3, max_length=60)
    claim: str = Field(min_length=10, max_length=320)
    outcome: str
    topic: str
    archetype: str
    origin: str = Field(min_length=3, max_length=260)


class _Hypotheses(BaseModel):
    hypotheses: list[_Hypothesis]


SYSTEM = """You are the Scribe of the Hypothesis Gauntlet. From a summary of REAL published evidence, propose
exactly {n} distinct, testable hypotheses for the campaign question: {question}
Drug: {drug}. Comparator: {comparator}. Population: {population}.
For each hypothesis choose:
  outcome:   one key from {outcomes}
  topic:     one evidence topic key from {topics}
  archetype: how the claim was found. HYPE = a crowd claim found on social media by searching many outcomes and
             subgroups; PIONEER = a careful, mechanistic, clinically framed claim; PREPRINT = an optimistic claim from
             a small study or animal work. Use a mix of archetypes, and let the evidence suggest which fits.
  title:     a plain-English headline of the hypothesis itself, at most eight words, e.g.
             "Semaglutide cuts alcohol relapse" or "BPC-157 speeds tendon healing" (no fantasy names)
  claim:     one sentence (under forty words) stating what the drug does to that outcome versus the comparator
  origin:    where such a claim comes from, grounded in the evidence summary (under twenty-five words)
Never write numbers, effect sizes or p-values: a deterministic Statistical Judge measures everything.
Reply with JSON only: {{"hypotheses": [{{"title": ..., "claim": ..., "outcome": ..., "topic": ..., "archetype": ..., "origin": ...}}]}}"""


def _has_number(text: str) -> bool:
    return any(ch.isdigit() for ch in _NAMES.sub("", text))


def _valid(h: _Hypothesis, c: Campaign) -> bool:
    return (h.outcome in {o.key for o in c.outcomes} and h.topic in TOPICS.get(c.letter, {})
            and h.archetype in ARCHETYPE_ORDER
            and not any(_has_number(t) for t in (h.title, h.claim, h.origin)))


def _summary(c: Campaign, ev: dict | None) -> dict:
    """What the Scribe reads: the counts copied from the database, no statistics."""
    if not ev:
        return {"note": "No real evidence database was found; write hypotheses from the campaign question."}
    return {"topics": {k: {key: v[key] for key in ("label", "papers_found", "species", "unknown_species", "designs",
                                                   "trials", "completed_rcts", "examples")}
                       for k, v in ev["topics"].items()},
            "faers_adverse_event_reports": ev["faers"]}


def scripted(c: Campaign, n: int) -> list[_Hypothesis]:
    """Without Claude: the campaign's own scrolls first, then one plain claim per remaining outcome and archetype."""
    out = [_Hypothesis(title=s.title, claim=s.claim, outcome=s.outcome, topic=_default_topic(c, s.outcome, i, s.claim),
                       archetype=s.archetype, origin=s.origin[:260] or "the campaign brief")
           for i, s in enumerate(c.scrolls[:n])]
    verb = "lowers" if c.effect_direction < 0 else "raises"
    comp = c.comparator.replace(" (active comparator)", "")
    i = len(out)
    while len(out) < n:
        o = c.outcomes[i % len(c.outcomes)]
        arch = ARCHETYPE_ORDER[i % len(ARCHETYPE_ORDER)]
        label = o.label if o.label[1:2].isupper() else o.label[0].lower() + o.label[1:]
        out.append(_Hypothesis(title=f"The {o.key.capitalize()} Scroll", archetype=arch,
                               claim=f"Taking {c.drug} {verb} the risk of {label} compared with {comp}.",
                               outcome=o.key, topic=_default_topic(c, o.key, i), origin="the real literature summary"))
        i += 1
    return out


def _default_topic(c: Campaign, outcome: str, i: int, claim: str = "") -> str:
    topics = list(TOPICS.get(c.letter, {}))
    if outcome in topics:
        return outcome
    named = [t for t in topics if any(w.lower() in claim.lower() for w in re.split(r" / | and ", TOPICS[c.letter][t])
                                      if len(w) > 3 and not w.lower().startswith("glp"))]
    if len(named) == 1:
        return named[0]
    return DEFAULT_TOPIC.get(c.letter, {}).get(outcome) or (topics[i % len(topics)] if topics else "")


def ask_claude(complete, c: Campaign, n: int, ev: dict | None) -> list[_Hypothesis] | None:
    from ..arena.agents import ask
    system = SYSTEM.format(n=n, question=c.question, drug=c.drug, comparator=c.comparator, population=c.population,
                           outcomes={o.key: o.label for o in c.outcomes}, topics=TOPICS.get(c.letter, {}))
    reply = ask(complete, system, _summary(c, ev), _Hypotheses)
    return reply.hypotheses if reply else None


# ---------------------------------------------------------------- scrolls

def form(c: Campaign, n: int, complete=None, db_path: Path = DB_PATH) -> tuple[list[Scroll], dict]:
    """N scrolls for campaign c and a record of how they were formed (for the ledger)."""
    n = max(1, min(MAX_SCROLLS, int(n)))
    ev = load_evidence(c.letter, db_path)
    hyps, source = None, "script"
    if complete is not None:
        got = ask_claude(complete, c, n, ev)
        if got:
            good = [h for h in got if _valid(h, c)][:n]
            if good:
                hyps, source = good, "claude"
    hyps = (hyps or []) + scripted(c, n)[len(hyps or []):]   # any slot Claude left empty is filled by the script
    scrolls = [_scroll(c, h, i, ev) for i, h in enumerate(hyps)]
    info = {"count": len(scrolls), "source": source, "evidence": "real" if ev else "simulated",
            "topics": {k: {key: v[key] for key in ("label", "papers_found", "papers_stored", "species",
                                                   "unknown_species", "trials", "completed_rcts")}
                       for k, v in (ev or {}).get("topics", {}).items()},
            "faers": (ev or {}).get("faers", [])}
    return scrolls, info


def _scroll(c: Campaign, h: _Hypothesis, i: int, ev: dict | None) -> Scroll:
    template = next(s for s in c.scrolls if s.archetype == h.archetype)
    topic = (ev or {}).get("topics", {}).get(h.topic)
    extra = {}
    if topic:   # the real evidence replaces the template's simulated papers and trial count
        extra = {"literature": Literature(records=topic["records"]), "n_rct": topic["completed_rcts"],
                 "evidence_topic": h.topic, "evidence_real": True}
    return dataclasses.replace(template, key=f"h{i + 1}", title=h.title, claim=h.claim, outcome=h.outcome,
                               origin=h.origin, **extra)

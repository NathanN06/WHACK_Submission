#!/usr/bin/env python3
"""Download REAL public evidence for the four Gauntlet campaigns into data/pep_evidence.duckdb.

Sources (all free, no API key):
  - Europe PMC          papers and preprints: title, year, journal, publication type, MeSH, species
  - ClinicalTrials.gov  registered studies: status, phase, enrollment, whether results were posted
  - openFDA FAERS       counts of real adverse-event reports (2x2 tables for disproportionality)

Real patient-level records (who took the drug, confounders, relapse) are not public, so the
Gauntlet's cohort stays simulated; this database only replaces the literature, trial and
pharmacovigilance evidence. The script stores raw counts and records; it computes no statistics.

It lives in its own file (not whack.duckdb) because build_db.py rebuilds whack.duckdb from scratch.
The database is rebuilt on every run (written to a temp file, then swapped in).

Usage:
  .venv/bin/python scripts/download_pep_evidence.py                  # all campaigns
  .venv/bin/python scripts/download_pep_evidence.py --only D         # one campaign
  .venv/bin/python scripts/download_pep_evidence.py --max-papers 50  # fewer papers per topic
"""

from __future__ import annotations

import argparse
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import duckdb
import httpx

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "data" / "pep_evidence.duckdb"
UA = {"User-Agent": "WHACK-hackathon-evidence/0.1"}

EPMC = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
CTGOV = "https://clinicaltrials.gov/api/v2/studies"
FAERS = "https://api.fda.gov/drug/event.json"

GLP1 = '(semaglutide OR tirzepatide OR liraglutide OR dulaglutide OR "GLP-1 receptor agonist")'

# Per campaign: topics, each with a Europe PMC query and ClinicalTrials.gov condition/intervention terms.
TOPICS = {
    "A": [
        ("alcohol", "GLP-1 drugs and alcohol use", f"{GLP1} AND (alcohol OR \"alcohol use disorder\")",
         "alcohol use disorder", "semaglutide OR tirzepatide OR liraglutide OR dulaglutide OR exenatide"),
        ("opioid", "GLP-1 drugs and opioid use", f"{GLP1} AND (opioid OR \"opioid use disorder\")",
         "opioid use disorder", "semaglutide OR tirzepatide OR liraglutide OR dulaglutide OR exenatide"),
        ("nicotine", "GLP-1 drugs and smoking", f"{GLP1} AND (smoking OR nicotine OR tobacco)",
         "smoking OR nicotine dependence OR tobacco use disorder",
         "semaglutide OR tirzepatide OR liraglutide OR dulaglutide OR exenatide"),
    ],
    "B": [
        ("bpc157", "BPC-157", '("BPC-157" OR "BPC 157" OR "body protection compound 157" OR "pentadecapeptide BPC")',
         None, "BPC-157 OR BPC 157"),
        ("tb500", "TB-500 / thymosin beta-4", '("TB-500" OR "TB500" OR "thymosin beta-4" OR "thymosin beta 4")',
         None, "thymosin beta-4 OR TB-500"),
    ],
    "C": [
        ("ghkcu", "GHK-Cu copper peptide", '("GHK-Cu" OR "copper peptide GHK" OR "copper tripeptide" OR "GHK copper")',
         None, "GHK-Cu OR copper peptide"),
        ("gh_secretagogue", "Ipamorelin / CJC-1295", '(ipamorelin OR "CJC-1295" OR "CJC 1295")',
         None, "ipamorelin OR CJC-1295"),
    ],
    "D": [
        ("naion", "GLP-1 drugs and NAION",
         f'{GLP1} AND (NAION OR "ischemic optic neuropathy" OR "ischaemic optic neuropathy")',
         "ischemic optic neuropathy OR NAION", "semaglutide OR tirzepatide OR liraglutide OR dulaglutide"),
        ("retinopathy", "GLP-1 drugs and diabetic retinopathy", f'{GLP1} AND "diabetic retinopathy"',
         "diabetic retinopathy", "semaglutide OR tirzepatide OR liraglutide OR dulaglutide"),
    ],
}

# FAERS: (campaign, topic, drug_group, generic names, reaction MedDRA preferred terms)
FAERS_DRUGS = {
    "glp1": ["semaglutide", "tirzepatide", "liraglutide", "dulaglutide", "exenatide"],
    "sglt2": ["empagliflozin", "dapagliflozin", "canagliflozin"],   # campaign D's active comparator
}
FAERS_ROWS = [
    ("D", "naion", ["Optic ischaemic neuropathy"]),
    ("D", "retinopathy", ["Diabetic retinopathy"]),
    ("D", "vision", ["Blindness", "Visual impairment", "Vision blurred"]),
]

ANIMAL_RE = re.compile(r"\b(rats?|mice|mouse|murine|rodents?|rabbits?|dogs?|pigs?|porcine|zebrafish|primates?)\b", re.I)
HUMAN_RE = re.compile(r"\b(patients?|participants?|humans?|women|men|adults?|volunteers?|cohort|subjects)\b", re.I)
INVITRO_RE = re.compile(r"\b(in vitro|cell lines?|cultured|fibroblasts|keratinocytes|cells)\b", re.I)


# ---------------------------------------------------------------- HTTP

def get(client: httpx.Client, url: str, params: dict, tries: int = 4) -> dict | None:
    """GET JSON with retries. Returns None on a 404 (openFDA's 'no matches')."""
    for i in range(tries):
        try:
            r = client.get(url, params=params)
            if r.status_code == 404:
                return None
            if r.status_code == 429 or r.status_code >= 500:
                raise httpx.HTTPStatusError("retryable", request=r.request, response=r)
            r.raise_for_status()
            return r.json()
        except (httpx.HTTPError, ValueError) as e:
            if i == tries - 1:
                raise
            wait = 2 ** i
            print(f"    retry in {wait}s ({e.__class__.__name__})", file=sys.stderr)
            time.sleep(wait)
    return None


# ---------------------------------------------------------------- Europe PMC

def species_of(mesh: list[str], text: str) -> tuple[str, str]:
    """(species, basis): human / animal / in_vitro / mixed / unknown, from MeSH first, then keywords."""
    m = set(mesh)
    if m:
        h, a = "Humans" in m, "Animals" in m
        if h and a:
            return "mixed", "mesh"
        if h:
            return "human", "mesh"
        if a:
            return "animal", "mesh"
        if m & {"In Vitro Techniques", "Cells, Cultured", "Cell Line"}:
            return "in_vitro", "mesh"
    a, h, v = bool(ANIMAL_RE.search(text)), bool(HUMAN_RE.search(text)), bool(INVITRO_RE.search(text))
    if a and h:
        return "mixed", "text"
    if a:
        return "animal", "text"
    if h:
        return "human", "text"
    if v:
        return "in_vitro", "text"
    return "unknown", "none"


def design_of(pub_types: list[str], source: str) -> str:
    t = {p.lower() for p in pub_types}
    if source == "PPR" or "preprint" in t:
        return "preprint"
    for key, label in [("meta-analysis", "meta_analysis"), ("systematic review", "systematic_review"),
                       ("randomized controlled trial", "rct"), ("clinical trial", "clinical_trial"),
                       ("observational study", "observational"), ("case reports", "case_report"),
                       ("review", "review"), ("letter", "letter"), ("editorial", "editorial")]:
        if any(key in p for p in t):
            return label
    return "other"


def fetch_papers(client, letter, topic, label, query, max_papers):
    rows, cursor, hits = [], "*", 0
    while len(rows) < max_papers:
        d = get(client, EPMC, {"query": query, "format": "json", "resultType": "core",
                               "pageSize": min(100, max_papers - len(rows)), "cursorMark": cursor})
        if not d:
            break
        hits = d.get("hitCount", 0)
        res = d.get("resultList", {}).get("result", [])
        for r in res:
            mesh = [h.get("descriptorName", "") for h in (r.get("meshHeadingList") or {}).get("meshHeading", [])]
            ptypes = (r.get("pubTypeList") or {}).get("pubType", [])
            title, abstract = r.get("title") or "", r.get("abstractText") or ""
            sp, basis = species_of(mesh, f"{title} {abstract}")
            rows.append({
                "campaign": letter, "topic": topic, "source_id": f"{r.get('source')}:{r.get('id')}",
                "pmid": r.get("pmid"), "doi": r.get("doi"), "title": title,
                "journal": ((r.get("journalInfo") or {}).get("journal") or {}).get("title"),
                "pub_year": int(r["pubYear"]) if str(r.get("pubYear", "")).isdigit() else None,
                "source": r.get("source"), "design": design_of(ptypes, r.get("source", "")),
                "pub_types": "; ".join(ptypes), "species": sp, "species_basis": basis,
                "mesh": "; ".join(mesh), "cited_by": r.get("citedByCount"),
                "authors": (r.get("authorString") or "")[:500], "abstract": abstract,
                "url": f"https://europepmc.org/article/{r.get('source')}/{r.get('id')}",
            })
        nxt = d.get("nextCursorMark")
        if not res or not nxt or nxt == cursor:
            break
        cursor = nxt
    q = {"campaign": letter, "topic": topic, "label": label, "source": "europepmc", "query": query,
         "hit_count": hits, "stored": len(rows)}
    return rows, q


# ---------------------------------------------------------------- ClinicalTrials.gov

def fetch_trials(client, letter, topic, label, cond, intr):
    params = {"query.intr": intr, "pageSize": 200, "countTotal": "true", "format": "json"}
    if cond:
        params["query.cond"] = cond
    rows, total, token = [], 0, None
    while True:
        if token:
            params["pageToken"] = token
        d = get(client, CTGOV, params)
        if not d:
            break
        total = d.get("totalCount", total)
        for s in d.get("studies", []):
            p = s.get("protocolSection", {})
            ident, status = p.get("identificationModule", {}), p.get("statusModule", {})
            design = p.get("designModule", {})
            info = design.get("designInfo", {})
            rows.append({
                "campaign": letter, "topic": topic, "nct_id": ident.get("nctId"),
                "title": ident.get("briefTitle"), "status": status.get("overallStatus"),
                "study_type": design.get("studyType"), "phases": "; ".join(design.get("phases", [])),
                "allocation": info.get("allocation"),
                "masking": (info.get("maskingInfo") or {}).get("masking"),
                "enrollment": (design.get("enrollmentInfo") or {}).get("count"),
                "start_date": (status.get("startDateStruct") or {}).get("date"),
                "completion_date": (status.get("completionDateStruct") or {}).get("date"),
                "has_results": bool(s.get("hasResults")),
                "conditions": "; ".join(p.get("conditionsModule", {}).get("conditions", [])),
                "interventions": "; ".join(i.get("name", "") for i in
                                           p.get("armsInterventionsModule", {}).get("interventions", [])),
                "sponsor": ((p.get("sponsorCollaboratorsModule") or {}).get("leadSponsor") or {}).get("name"),
                "url": f"https://clinicaltrials.gov/study/{ident.get('nctId')}",
            })
        token = d.get("nextPageToken")
        if not token:
            break
    q = {"campaign": letter, "topic": topic, "label": label, "source": "clinicaltrials.gov",
         "query": f"cond={cond or '-'} | intr={intr}", "hit_count": total, "stored": len(rows)}
    return rows, q


# ---------------------------------------------------------------- openFDA FAERS

def or_terms(field: str, values: list[str]) -> str:
    return "(" + "+".join(f'{field}:"{v.replace(" ", "+")}"' for v in values) + ")"


def faers_count(client, search: str | None) -> int:
    # openFDA wants '+' as the space between terms, so the query string is built by hand.
    url = FAERS + "?limit=1" + (f"&search={search}" if search else "")
    for i in range(4):
        r = client.get(url)
        if r.status_code == 404:
            return 0
        if r.status_code == 200:
            return r.json()["meta"]["results"]["total"]
        time.sleep(2 ** i)
    r.raise_for_status()
    return 0


def fetch_faers(client, letter, topic, reactions):
    """One 2x2 table per drug group: a = drug & reaction, plus the margins and the database total."""
    rx = or_terms("patient.reaction.reactionmeddrapt", reactions)
    total = faers_count(client, None)
    reaction_total = faers_count(client, rx)
    rows = []
    for group, names in FAERS_DRUGS.items():
        dr = or_terms("patient.drug.openfda.generic_name", names)
        drug_total = faers_count(client, dr)
        a = faers_count(client, f"{dr}+AND+{rx}")
        rows.append({"campaign": letter, "topic": topic, "drug_group": group, "drugs": "; ".join(names),
                     "reactions": "; ".join(reactions), "drug_and_reaction": a, "drug_total": drug_total,
                     "reaction_total": reaction_total, "all_reports": total})
        time.sleep(0.3)   # openFDA without a key: 240 requests/minute
    return rows


# ---------------------------------------------------------------- database

SCHEMA = {
    "pep_queries": """campaign VARCHAR, topic VARCHAR, label VARCHAR, source VARCHAR, query VARCHAR,
                      hit_count INTEGER, stored INTEGER, fetched_at TIMESTAMP""",
    "pep_papers": """campaign VARCHAR, topic VARCHAR, source_id VARCHAR, pmid VARCHAR, doi VARCHAR, title VARCHAR,
                     journal VARCHAR, pub_year INTEGER, source VARCHAR, design VARCHAR, pub_types VARCHAR,
                     species VARCHAR, species_basis VARCHAR, mesh VARCHAR, cited_by INTEGER, authors VARCHAR,
                     abstract VARCHAR, url VARCHAR""",
    "pep_trials": """campaign VARCHAR, topic VARCHAR, nct_id VARCHAR, title VARCHAR, status VARCHAR,
                     study_type VARCHAR, phases VARCHAR, allocation VARCHAR, masking VARCHAR, enrollment INTEGER,
                     start_date VARCHAR, completion_date VARCHAR, has_results BOOLEAN, conditions VARCHAR,
                     interventions VARCHAR, sponsor VARCHAR, url VARCHAR""",
    "pep_faers": """campaign VARCHAR, topic VARCHAR, drug_group VARCHAR, drugs VARCHAR, reactions VARCHAR,
                    drug_and_reaction INTEGER, drug_total INTEGER, reaction_total INTEGER, all_reports INTEGER,
                    fetched_at TIMESTAMP""",
}

TABLE_DOCS = {
    "pep_queries": "One row per (campaign, topic, source) query: the exact query sent and how many records matched "
                   "in total (hit_count) versus how many were stored (stored). REAL public data.",
    "pep_papers": "REAL papers and preprints from Europe PMC for each Gauntlet campaign topic (most relevant first). "
                  "species and design are heuristic labels from MeSH / publication type / keywords.",
    "pep_trials": "REAL registered studies from ClinicalTrials.gov matching each campaign topic.",
    "pep_faers": "REAL openFDA FAERS report counts: one 2x2 table per (topic, drug group). Spontaneous reports "
                 "only: counts are not incidence and cannot prove causation.",
}

COLUMN_DOCS = {
    ("*", "campaign"): "Gauntlet campaign letter (A-D), as in backend/app/pep/campaigns.py.",
    ("*", "topic"): "Topic key within the campaign (e.g. 'alcohol', 'naion').",
    ("pep_queries", "hit_count"): "Total matching records reported by the source.",
    ("pep_queries", "stored"): "Records actually stored in this database (capped by --max-papers for papers).",
    ("pep_papers", "source"): "Europe PMC source: MED = PubMed, PMC = PubMed Central, PPR = preprint.",
    ("pep_papers", "design"): "preprint, meta_analysis, systematic_review, rct, clinical_trial, observational, "
                              "case_report, review, letter, editorial or other (from publication types).",
    ("pep_papers", "species"): "human, animal, in_vitro, mixed or unknown.",
    ("pep_papers", "species_basis"): "mesh (MeSH headings), text (keywords in title/abstract) or none.",
    ("pep_papers", "cited_by"): "Europe PMC citation count at fetch time.",
    ("pep_trials", "status"): "Overall recruitment status, e.g. COMPLETED, RECRUITING, TERMINATED.",
    ("pep_trials", "allocation"): "RANDOMIZED, NON_RANDOMIZED or NA.",
    ("pep_trials", "has_results"): "True if results were posted to ClinicalTrials.gov.",
    ("pep_faers", "drug_group"): "glp1 (semaglutide, tirzepatide, liraglutide, dulaglutide, exenatide) or "
                                 "sglt2 (empagliflozin, dapagliflozin, canagliflozin; campaign D's comparator).",
    ("pep_faers", "drug_and_reaction"): "Reports naming any drug in the group AND any listed reaction (cell a).",
    ("pep_faers", "drug_total"): "All reports naming any drug in the group (a + b).",
    ("pep_faers", "reaction_total"): "All reports with any listed reaction, any drug (a + c).",
    ("pep_faers", "all_reports"): "All reports in FAERS at fetch time (a + b + c + d).",
}


def write_db(queries, papers, trials, faers) -> None:
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    tmp = DB_PATH.with_name(DB_PATH.name + ".tmp")
    tmp.unlink(missing_ok=True)
    con = duckdb.connect(str(tmp))
    for name, cols in SCHEMA.items():
        con.execute(f"CREATE TABLE {name} ({cols})")
    data = {"pep_queries": [{**q, "fetched_at": now} for q in queries], "pep_papers": papers,
            "pep_trials": trials, "pep_faers": [{**f, "fetched_at": now} for f in faers]}
    for name, rows in data.items():
        if not rows:
            continue
        cols = [c[0] for c in con.execute(f"DESCRIBE {name}").fetchall()]
        con.executemany(f"INSERT INTO {name} VALUES ({', '.join('?' * len(cols))})",
                        [[r.get(c) for c in cols] for r in rows])
    q = lambda s: "'" + s.replace("'", "''") + "'"
    for t, doc in TABLE_DOCS.items():
        con.execute(f"COMMENT ON TABLE {t} IS {q(doc)}")
        for (c,) in con.execute(f"SELECT column_name FROM duckdb_columns() WHERE table_name = '{t}'").fetchall():
            doc = COLUMN_DOCS.get((t, c)) or COLUMN_DOCS.get(("*", c))
            if doc:
                con.execute(f'COMMENT ON COLUMN {t}."{c}" IS {q(doc)}')
    con.close()
    tmp.replace(DB_PATH)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--only", choices=sorted(TOPICS), action="append", help="campaign letter (repeatable)")
    ap.add_argument("--max-papers", type=int, default=200, help="papers stored per topic (default 200)")
    args = ap.parse_args()
    letters = args.only or sorted(TOPICS)
    DB_PATH.parent.mkdir(exist_ok=True)

    queries, papers, trials, faers = [], [], [], []
    t0 = time.time()
    with httpx.Client(headers=UA, timeout=60, follow_redirects=True) as client:
        for L in letters:
            print(f"Campaign {L}")
            for topic, label, epmc_q, cond, intr in TOPICS[L]:
                p, q = fetch_papers(client, L, topic, label, epmc_q, args.max_papers)
                papers += p
                queries.append(q)
                t, q2 = fetch_trials(client, L, topic, label, cond, intr)
                trials += t
                queries.append(q2)
                print(f"  {topic:16s} papers {q['stored']:>4}/{q['hit_count']:<6} trials {q2['stored']:>4}")
            for letter, topic, reactions in FAERS_ROWS:
                if letter == L:
                    rows = fetch_faers(client, L, topic, reactions)
                    faers += rows
                    print("  FAERS " + topic + ": " + ", ".join(
                        f"{r['drug_group']} {r['drug_and_reaction']}/{r['drug_total']}" for r in rows))

    write_db(queries, papers, trials, faers)
    print(f"\nWrote {DB_PATH.relative_to(ROOT)}: {len(papers)} papers, {len(trials)} trials, "
          f"{len(faers)} FAERS tables in {time.time() - t0:.0f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())

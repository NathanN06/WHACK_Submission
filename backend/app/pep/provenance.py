"""The Archivist's manifest: where every piece of evidence came from, and how every reported number was made.

Source types are kept apart, and only stored identifiers are ever cited (nothing is generated):
  SIMULATED_COHORT                  the synthetic EHR cohort the Judge tests claims on (campaign, seed, fingerprint)
  SIMULATED_SOCIAL_CORPUS           the synthetic posts of Level I
  SIMULATED_LITERATURE              hand-written campaign papers, when no real evidence database is present
  REAL_PUBLICATION_METADATA         a paper found by a stored Europe PMC query: PMID, DOI or source id, title, year
  REAL_TRIAL_RECORD                 a ClinicalTrials.gov registry entry: NCT id, status, whether results are posted
  REAL_PHARMACOVIGILANCE_REPORTS    openFDA FAERS report counts: no denominator, not evidence of causation
Paper counts, trial counts and adverse-event report counts are context, never evidence that a drug works or harms.
"""

from __future__ import annotations

from . import rules

CONTEXT_ONLY = "Context only: matched by topic query, not checked against this claim and not evidence of efficacy."


def paper_id(r: dict) -> str | None:
    if r.get("pmid"):
        return f"PMID:{r['pmid']}"
    if r.get("doi"):
        return f"DOI:{r['doi']}"
    if r.get("source_id"):
        return f"EPMC:{r['source_id']}"
    return None


def scroll_sources(q, a) -> list[dict]:
    """Every evidence item behind one scroll, with its source type and identifier."""
    s, w = a.scroll, q.w
    out = [{"id": f"COHORT:{w.fingerprint()}", "type": "SIMULATED_COHORT", "origin": "world.py",
            "detail": f"campaign {q.c.id}, seed {q.seed}; training, holdout and sealed-vault partitions by calendar time",
            "relevance": "the patients every number about this claim is measured on"}]
    if s.corpus is not None:
        out.append({"id": f"CORPUS:{s.key}", "type": "SIMULATED_SOCIAL_CORPUS", "origin": "world.py",
                    "detail": "synthetic YouTube, Quora and Reddit posts", "relevance": "Level I rumours"})
    L = s.literature
    if L is not None and L.records is not None:
        topic = (q.formation or {}).get("topics", {}).get(s.evidence_topic, {})
        query = next((x for x in (getattr(L, "queries", None) or []) if x.get("source") == "europepmc"), {})
        for r in L.records:
            out.append({"id": paper_id(r), "type": "REAL_PUBLICATION_METADATA", "origin": "Europe PMC",
                        "title": r.get("title"), "year": r.get("year"), "url": r.get("url"), "species": r.get("species"),
                        "design": r.get("design"), "query": query.get("query"), "retrieved_at": query.get("fetched_at"),
                        "snapshot": "data/pep_evidence.duckdb", "relevance": CONTEXT_ONLY,
                        "topic": s.evidence_topic, "topic_label": topic.get("label")})
        trials_q = next((x for x in (getattr(L, "queries", None) or []) if x.get("source") == "clinicaltrials.gov"), {})
        for t in getattr(L, "trials", None) or []:
            out.append({"id": f"NCT:{t['nct_id']}" if t.get("nct_id") else None, "type": "REAL_TRIAL_RECORD",
                        "origin": "ClinicalTrials.gov", "title": t.get("title"), "status": t.get("status"),
                        "allocation": t.get("allocation"), "results_posted": t.get("has_results"), "url": t.get("url"),
                        "query": trials_q.get("query"), "retrieved_at": trials_q.get("fetched_at"),
                        "snapshot": "data/pep_evidence.duckdb",
                        "relevance": "A completed randomized trial registered on this topic. Its results were not "
                                     "retrieved or assessed, so it neither supports nor refutes the claim."})
    elif L is not None:
        out.append({"id": f"LIT:{s.key}", "type": "SIMULATED_LITERATURE", "origin": "campaigns.py",
                    "detail": f"{L.human} human, {L.rodent} rodent, {L.in_vitro} in vitro papers (hand-written)",
                    "relevance": "Levels II and III, simulated"})
    return out


def campaign_sources(q) -> list[dict]:
    """Evidence about the campaign as a whole: the adverse-event report counts, labelled for what they are."""
    out = []
    for f in (q.formation or {}).get("faers", []) or []:
        out.append({"id": f"FAERS:{q.c.letter}:{f.get('topic')}:{f.get('drug_group')}", "type": "REAL_PHARMACOVIGILANCE_REPORTS",
                    "origin": "openFDA FAERS", "drug_group": f.get("drug_group"), "reactions": f.get("reactions"),
                    "reports_with_drug_and_reaction": f.get("drug_and_reaction"), "reports_with_drug": f.get("drug_total"),
                    "retrieved_at": f.get("fetched_at"), "snapshot": "data/pep_evidence.duckdb",
                    "relevance": "Spontaneous report counts: no denominator, reporting bias, not evidence that the "
                                 "drug causes the reaction."})
    return out


METHODS = {
    "final": ("Guardian: Brier skill of the claim's effect vs the comparator's risk model; paired one-sided t-test of "
              "per-patient loss on 1:1 propensity-matched new users", "holdout (index days 1100-1449)"),
    "chrono": ("Poisson rate model with a person-time offset, as carried vs new-user (time-zero) design",
               "training years (index day < 1100)"),
    "confound": ("Poisson rate model, naive vs adjusted for six confounders and site", "training years (index day < 1100)"),
    "sidak": ("Best of K Poisson tests over the scroll's search, Sidak-corrected", "training years (index day < 1100)"),
    "hlab": ("Per-site Poisson rate models; lab concentration from real paper metadata", "training years (index day < 1100)"),
    "trial": ("Guardian test of the locked claim on the sealed vault", "sealed vault (index day >= 1450)"),
    "status": ("Reference new-user adjusted Poisson model with 95% Wald interval; Holm across the quest's claims",
               "training years (index day < 1100) and the Guardian's holdout p-values"),
}


def chain(q, statement_id: str, text: str, cite: str | None, method_key: str) -> dict:
    """report statement -> ledger row -> method and version -> data partition and filters -> origin and seed."""
    seq = next((e.seq for e in q.ledger.events if e.encounter and e.encounter.get("encounterId") == cite), None)
    method, partition = METHODS.get(method_key, ("", ""))
    return {"statement": statement_id, "text": text, "encounter": cite, "ledger_seq": seq,
            "method": method, "method_version": rules.ANALYSIS_VERSION, "partition": partition,
            "origin": "SIMULATED_COHORT", "campaign": q.c.id, "seed": q.seed, "world": q.w.fingerprint()}

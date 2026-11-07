"""The four pre-loaded campaigns (spec section 8): variable bindings over one Statistical Judge.

Each campaign binds the same four archetypes to its own streams, confounder and lag windows.
All four worlds are simulated with planted truths (see scenario.py); `truth` is only shown in the
decision brief, after the Judge has ruled.
"""

from .scenario import AgentBinding as A
from .scenario import Campaign, Stream


def _episodes(n: int, start: int, end: int, seed: int, amp=(0.8, 2.2), width=(2.0, 4.0)) -> tuple:
    """Short pollution episodes for the environmental campaign (deterministic)."""
    import numpy as np
    rng = np.random.default_rng(seed)
    days = np.sort(rng.choice(np.arange(start, end), n, replace=False))
    return tuple((int(d), float(rng.uniform(*amp)), float(rng.uniform(*width))) for d in days)


def _digital(prefix: str, terms: list[tuple[str, int, float, float, float]]) -> dict:
    """Search/social streams: (label, lead, truth, media, season); noisy, region-specific."""
    return {f"{prefix}{i}": Stream(label, lead=lead, truth=t, media=m, season=s, noise=0.6, spread=1.2)
            for i, (label, lead, t, m, s) in enumerate(terms)}


SKEPTIC_CLAIM = "AR(4) plus a seasonal harmonic on admissions alone explains it; outside streams are noise."

# ---------- Campaign A: wastewater bio-surveillance ----------

_A_DIGITAL = _digital("a_dig", [
    ("Search: 'fever'", 3, 0.25, 1.0, 0.6), ("Search: 'cough'", 2, 0.2, 0.8, 0.8),
    ("Search: 'flu symptoms'", 4, 0.3, 1.3, 0.5), ("Forum: 'sick' threads", 1, 0.15, 1.1, 0.3),
    ("Social: symptom videos", 0, 0.1, 1.6, 0.2), ("Search: 'loss of taste'", 5, 0.15, 0.7, 0.1),
    ("Forum: cold-medicine mentions", 2, 0.2, 0.5, 0.8),
])
WASTEWATER = Campaign(
    id="WASTEWATER_FLU", letter="A", title="Wastewater Bio-Surveillance",
    question="Does municipal SARS-CoV-2 / Influenza A wastewater RNA provide a real-time 7-day lead over ICU "
             "admissions, or is it an artifact of seasonal trend and backfilled lab reports?",
    target="Hospital admissions", unit="per 100k per day (7-day mean)", horizon=5,
    z_name="Ambient temperature & sewer flow dilution", z_kind="cold", media_name="National news mentions",
    waves=((70, 1.6, 16), (190, 1.0, 20), (330, 2.0, 18), (455, 1.2, 15), (560, 1.8, 20), (690, 1.4, 16), (820, 2.1, 18)),
    panic_days=(130, 262, 395, 508, 628, 757, 874), season_amp=0.4,
    streams={
        "ww_rna": Stream("Wastewater RNA (flow-normalized)", lead=7, truth=1.0, noise=0.15, backfill_tau=1.2,
                         spread=0.1, source="lab"),
        **_A_DIGITAL,
        "a_lab": Stream("Official lab-confirmed cases", lead=3, truth=1.0, noise=0.15, backfill_tau=6.0, spread=0.1,
                        source="official"),
        "a_otc": Stream("OTC antipyretic sales", lead=2, truth=0.5, media=0.4, season=0.4, noise=0.4, spread=0.3,
                        source="pharmacy"),
    },
    agents=(
        A("HYPE", "Vex", "Mining every search, forum and social symptom feed at any lag from 1 to 21 days predicts hospital admissions.",
          streams=tuple(_A_DIGITAL), window=(1, 21), ar=False),
        A("PIONEER", "Imara", "Flow-normalized wastewater RNA leads hospital admissions by 5 to 7 days.",
          streams=("ww_rna",), window=(5, 7), claimed_lag=7,
          plan={2: ("BIAS_DETECTION",), 3: ("PREREGISTER", "REPLICATION_SHIELD"), 4: ("TEMPORAL_GUARD",)},
          buffs=("FLOW-NORMALIZED",)),
        A("PREPRINT", "Quill", "A single-hospital preprint (n = 28): OTC antipyretic sales predict surges 3 weeks early.",
          streams=("a_otc",), window=(14, 28), claimed_lag=21, cohort_n=28, cohort_rho=0.3,
          ar=False, plan={1: ("EXPLORATORY_CLAIM",)}),
        A("SKEPTIC", "Ward", SKEPTIC_CLAIM, plan={3: ("PREREGISTER",)}),
    ),
    plausible=(5, 7),
    truth="Wastewater RNA leads admissions by 7 days and carries real signal. Search and social streams are mostly "
          "news panic and season. Official lab counts track admissions but are backfilled over about three weeks. "
          "OTC sales lead by only 2 days, not 21.",
)

# ---------- Campaign B: digital syndromic mirage (pediatric RSV) ----------

_B_DIGITAL = _digital("b_dig", [
    ("Search: 'RSV symptoms'", 3, 0.3, 1.4, 0.6), ("Search: 'baby wheezing'", 4, 0.25, 1.0, 0.7),
    ("Search: 'bronchiolitis'", 2, 0.2, 1.2, 0.5), ("Forum: parenting 'sick baby' threads", 1, 0.15, 0.9, 0.9),
    ("Social: 'tripledemic' posts", 0, 0.05, 1.8, 0.2), ("Search: 'nebulizer'", 5, 0.2, 0.6, 0.6),
    ("Search: 'daycare closed'", 2, 0.1, 0.5, 1.2),
])
DIGITAL_RSV = Campaign(
    id="DIGITAL_RSV", letter="B", title="Digital Syndromic Mirage",
    question="Can unfiltered search query volume and social symptom posts predict regional pediatric RSV surges "
             "without triggering false alarms during national media coverage?",
    target="Pediatric RSV admissions", unit="per 100k children per day (7-day mean)", horizon=5,
    z_name="School term calendar", z_kind="school", media_name="National RSV news coverage",
    waves=((60, 2.0, 16), (430, 2.3, 17), (795, 2.1, 15), (250, 0.6, 14), (610, 0.7, 14)),
    panic_days=(150, 228, 305, 520, 668, 860), season_amp=0.6, base_rate=6.0, wave_rate=18.0,
    streams={
        "b_synd": Stream("Pediatric ED syndromic visits", lead=6, truth=0.9, media=0.9, season=0.2, noise=0.3,
                         backfill_tau=1.5, spread=0.15, source="sensor"),
        **_B_DIGITAL,
        "b_lab": Stream("Official RSV lab tests (NREVSS)", lead=3, truth=1.0, noise=0.15, backfill_tau=7.0, spread=0.1,
                        source="official"),
        "b_app": Stream("Symptom-app 'runny nose' check-ins", lead=1, truth=0.4, media=0.6, season=0.5, noise=0.5,
                        spread=0.4, source="digital"),
    },
    agents=(
        A("HYPE", "Vex", "Unfiltered RSV searches, parenting forums and official tests, at any lag from 1 to 21 days, "
                         "predict pediatric admissions.", streams=(*_B_DIGITAL, "b_lab"), window=(1, 21), ar=False),
        A("PIONEER", "Imara", "Media-adjusted pediatric ED syndromic visits lead RSV admissions by 5 to 8 days.",
          streams=("b_synd",), window=(5, 8), claimed_lag=6,
          plan={1: ("MEDIA_DENOISE",), 2: ("BIAS_DETECTION",), 3: ("PREREGISTER",), 4: ("TEMPORAL_GUARD",)},
          buffs=("SYNDROMIC",)),
        A("PREPRINT", "Quill", "A single-hospital preprint (n = 28): 'runny nose' check-ins in a symptom app predict RSV "
                               "surges 3 weeks early.", streams=("b_app",), window=(14, 28), claimed_lag=21,
          cohort_n=28, cohort_rho=0.35, ar=False, plan={1: ("EXPLORATORY_CLAIM",)}),
        A("SKEPTIC", "Ward", SKEPTIC_CLAIM, plan={3: ("PREREGISTER",)}),
    ),
    plausible=(5, 8),
    truth="ED syndromic visits lead admissions by 6 days but jump whenever RSV is in the news; de-noising removes that. "
          "Raw search and social streams are driven by news coverage and the school calendar. Lab tests are backfilled.",
)

# ---------- Campaign C: pharmacoepidemiology EHR audit ----------

_C_DIGITAL = _digital("c_dig", [
    ("Forum: 'Antiviral X saved me'", 2, 0.0, 1.2, 0.4), ("Search: 'Antiviral X'", 1, 0.1, 1.5, 0.3),
    ("Social: 'Antiviral X side effects'", 0, 0.0, 1.4, 0.2), ("Forum: long-illness threads", 3, 0.15, 0.6, 0.6),
    ("Search: 'where to get Antiviral X'", 2, 0.05, 1.1, 0.5), ("Pharmacy chatter: shortages", 4, 0.0, 0.9, 0.4),
    ("Search: 'hospital wait times'", 1, 0.25, 0.7, 0.5),
])
PHARMACO = Campaign(
    id="PHARMACO_EHR", letter="C", title="Pharmacoepidemiology EHR Audit",
    question="Does existing observational clinic data prove Repurposed Antiviral X reduces 28-day hospitalization, "
             "or is the 42% apparent reduction driven by confounding by indication and immortal time bias?",
    target="28-day hospitalizations (eligible outpatients)", unit="per 100k per day (7-day mean)", horizon=5,
    z_name="Baseline severity mix (confounding by indication)", z_kind="severity",
    media_name="Media alerts about Antiviral X",
    waves=((100, 1.5, 20), (260, 1.8, 22), (430, 1.2, 18), (575, 1.6, 20), (720, 1.4, 20), (850, 1.7, 18)),
    panic_days=(180, 350, 505, 650, 790), season_amp=0.5,
    streams={
        "c_uptake": Stream("Antiviral X uptake, exposure classified with follow-up", lead=0, truth=0.0, season=0.6,
                           hindsight=-0.9, noise=0.35, source="ehr"),
        **_C_DIGITAL,
        "c_faers": Stream("FAERS adverse-event reports (official)", lead=2, truth=0.3, media=1.0, noise=0.3,
                          backfill_tau=10.0, source="official"),
        "c_clinic": Stream("Single-clinic Antiviral X uptake", lead=0, truth=0.0, season=0.4, hindsight=-0.6, noise=0.9,
                           source="cohort"),
    },
    agents=(
        A("HYPE", "Vex", "Forum testimonials, search interest and adverse-event reports, at any lag from 1 to 21 days, "
                         "predict hospitalizations.", streams=(*_C_DIGITAL, "c_faers"), window=(1, 21), ar=False),
        A("PIONEER", "Imara", "Higher Antiviral X uptake predicts fewer hospitalizations 5 to 10 days later, after "
                              "adjusting for severity.", streams=("c_uptake",), window=(5, 10), claimed_lag=7,
          plan={2: ("BIAS_DETECTION",), 3: ("PREREGISTER", "REPLICATION_SHIELD"), 4: ("TEMPORAL_GUARD",)},
          buffs=("SEVERITY-ADJUSTED",)),
        A("PREPRINT", "Quill", "A single-clinic study (n = 28): Antiviral X cut hospitalizations by 42%, visible 3 weeks ahead.",
          streams=("c_clinic",), window=(14, 28), claimed_lag=21, cohort_n=28, cohort_rho=0.25,
          ar=False, plan={1: ("EXPLORATORY_CLAIM",)}),
        A("SKEPTIC", "Ward", SKEPTIC_CLAIM, plan={3: ("PREREGISTER",)}),
    ),
    plausible=(5, 10),
    truth="Antiviral X has no effect on hospitalization. Its apparent benefit comes from confounding by indication "
          "(sicker patients get it) and immortal-time bias (exposure classified with later follow-up).",
)

# ---------- Campaign D: environmental heatwave and PM2.5 ----------

_D_DIGITAL = _digital("d_dig", [
    ("Search: 'inhaler refill'", 1, 0.3, 1.0, 0.6), ("Social: 'can't breathe'", 0, 0.2, 1.4, 0.4),
    ("Forum: wildfire smoke complaints", 2, 0.25, 1.2, 0.5), ("Search: 'air quality'", 1, 0.3, 1.3, 0.7),
    ("Social: pollen-allergy posts", 3, 0.1, 0.8, 0.9), ("Search: 'asthma attack'", 0, 0.3, 1.1, 0.3),
    ("Air-quality app opens", 2, 0.2, 0.9, 0.8),
])
ENV_ASTHMA = Campaign(
    id="ENV_ASTHMA", letter="D", title="Environmental Heatwave & PM2.5 Surge",
    question="Do satellite PM2.5 spikes and heat-index thresholds predict acute asthma ER admissions across "
             "held-out rural districts?",
    target="Asthma ER admissions", unit="per 100k per day", horizon=2, smooth=1,
    z_name="Season and temperature", z_kind="heat", media_name="Wildfire and heat news coverage",
    waves=_episodes(46, 0, 900, seed=7, amp=(0.6, 1.8), width=(3.0, 6.0)),
    panic_days=(95, 240, 410, 560, 700, 845), season_amp=0.5, base_rate=20.0, wave_rate=24.0, infection_delay=1,
    streams={
        "d_pm25": Stream("Satellite PM2.5", lead=2, truth=1.0, season=0.3, noise=0.35, backfill_tau=0.8,
                         rural_factor=0.75, spread=0.15, source="sensor"),
        **_D_DIGITAL,
        "d_aqi": Stream("Regulatory AQI monitors (validated)", lead=1, truth=1.0, noise=0.15, backfill_tau=5.0,
                        source="official"),
        "d_pollen": Stream("Pollen counts", lead=1, truth=0.3, season=0.9, noise=0.5, spread=0.4, source="sensor"),
    },
    agents=(
        A("HYPE", "Vex", "Searches, smoke complaints, app opens and AQI monitors, at any lag from 1 to 21 days, predict "
                         "asthma admissions.", streams=(*_D_DIGITAL, "d_aqi"), window=(1, 21), ar=False),
        A("PIONEER", "Imara", "Satellite PM2.5 two to four days earlier predicts asthma ER admissions, in towns and counties.",
          streams=("d_pm25",), window=(2, 4), claimed_lag=2,
          plan={2: ("BIAS_DETECTION",), 3: ("PREREGISTER", "REPLICATION_SHIELD"), 4: ("TEMPORAL_GUARD",)},
          buffs=("SATELLITE-CALIBRATED",)),
        A("PREPRINT", "Quill", "A single-district study (n = 24): pollen counts predict asthma surges two weeks early.",
          streams=("d_pollen",), window=(10, 21), claimed_lag=14, cohort_n=24, cohort_rho=0.3,
          ar=False, plan={1: ("EXPLORATORY_CLAIM",)}),
        A("SKEPTIC", "Ward", SKEPTIC_CLAIM, plan={3: ("PREREGISTER",)}),
    ),
    plausible=(2, 4),
    truth="PM2.5 drives asthma admissions two days later, more weakly in rural districts. Searches and posts follow news "
          "coverage and season. Regulatory AQI is accurate but published days late. Pollen leads by one day, not fourteen.",
)

CAMPAIGNS = {c.id: c for c in (WASTEWATER, DIGITAL_RSV, PHARMACO, ENV_ASTHMA)}
BY_LETTER = {c.letter: c for c in CAMPAIGNS.values()}
ARCHETYPES = {
    "HYPE": {"title": "The Hype Nowcaster", "nickname": "The Google Flu Mirage", "cls": "Nowcaster",
             "signature": ["Data Dredge"]},
    "PIONEER": {"title": "The Bio-Surveillance Pioneer", "nickname": "Mechanistic Specialist", "cls": "Pioneer",
                "signature": ["Bias Detection", "Replication Shield", "Temporal Guard"]},
    "PREPRINT": {"title": "The Preprint Opportunist", "nickname": "Small-Cohort Optimist", "cls": "Opportunist",
                 "signature": ["Exploratory Claim"]},
    "SKEPTIC": {"title": "The Surveillance Skeptic", "nickname": "Autoregressive Baseline", "cls": "Skeptic",
                "signature": ["Preregister", "Ablation Strike"]},
}

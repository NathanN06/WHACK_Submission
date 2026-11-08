"""The four pre-loaded peptide campaigns and the scrolls the hero carries into each.

Each world is simulated with planted truths (see world.py); the numbers below are how the world was
built, not findings. Scroll archetypes decide how each hypothesis was found and which abilities the
hero buys for it:
  HYPE      found on social media: searches every outcome and subgroup, never pays for caution
  PIONEER   a mechanistic, clinically framed claim: buys rigour where the evidence is vulnerable
  PREPRINT  a small clinic log or animal preprint: fast, optimistic, spends almost nothing
The Gatekeeper's baseline (the matched active comparator with no drug effect) is not a scroll.
"""

import math

from .world import Campaign, Corpus, Literature, Outcome, Scroll

PIONEER_PLAN = {2: ["BIAS_DETECTION"], 3: ["PREREGISTER", "REPLICATION_SHIELD"], 4: ["TEMPORAL_GUARD"]}
PIONEER_PLAN_SPECIES = {2: ["SPECIES_GUARD", "BIAS_DETECTION"], 3: ["PREREGISTER", "REPLICATION_SHIELD"], 4: ["TEMPORAL_GUARD"]}
PREPRINT_PLAN = {1: ["EXPLORATORY_CLAIM"]}

GLP1_ADDICTION = Campaign(
    id="GLP1_ADDICTION", letter="A", title="The Craving Cure",
    question="Do semaglutide and tirzepatide really reduce alcohol and opioid relapse, or is it weight-loss "
             "enthusiasm, healthy-user bias and immortal time?",
    drug="Semaglutide / tirzepatide", comparator="DPP-4 inhibitors (active comparator)",
    population="Adults with type 2 diabetes or obesity and a recorded alcohol or opioid use disorder",
    n=24000,
    outcomes=[Outcome("alcohol", "Alcohol relapse within a year", 0.38, math.log(0.65)),
              Outcome("opioid", "Opioid relapse within a year", 0.30, math.log(0.88)),
              Outcome("nicotine", "Smoking relapse within a year", 0.45, 0.0)],
    confounding={"healthy": 0.35, "severity": -0.2, "therapy": 0.3, "trt": 0.1},
    risk={"healthy": -0.25, "severity": 0.35, "therapy": -0.3, "age10": -0.1},
    scrolls=[
        Scroll("hype", "HYPE", "The Cure-All Scroll",
               "Reddit and YouTube agree: GLP-1 drugs cure every addiction, from alcohol to opioids to smoking.",
               outcome="alcohol", outcomes_searched=3, subgroups_searched=7, design="ever",
               corpus=Corpus(posts=900, affiliate=0.45, stories=21, affiliate_story_share=0.3),
               literature=Literature(human=6, rodent=9, in_vitro=3, labs=(0.2, 0.2, 0.2, 0.2, 0.2)), n_rct=1,
               origin="a viral podcast clip and 900 reposts"),
        Scroll("pioneer", "PIONEER", "The Semaglutide Scroll",
               "Semaglutide reduces alcohol relapse compared with DPP-4 inhibitors in multi-site EHR cohorts.",
               outcome="alcohol", design="ever",
               corpus=Corpus(posts=140, affiliate=0.04, stories=64, platforms=(0.15, 0.35, 0.5)),
               literature=Literature(human=9, rodent=4, in_vitro=1, labs=(0.3, 0.25, 0.2, 0.15, 0.1)), n_rct=1,
               plan=PIONEER_PLAN, origin="an addiction psychiatrist's review of GLP-1 receptor biology"),
        Scroll("preprint", "PREPRINT", "The Clinic-Log Scroll",
               "A 24-patient clinic log: tirzepatide halves opioid relapse within weeks.",
               outcome="opioid", subgroups_searched=7, design="ever",
               corpus=Corpus(posts=60, affiliate=0.3, stories=9, affiliate_story_share=0.2),
               literature=Literature(human=1, rodent=2, labs=(1.0,)), n_rct=0,
               plan=PREPRINT_PLAN, origin="an open-label clinic log posted as a preprint"),
    ],
    gatekeeper={1: "{scroll} smells of sponsored links, Alchemist. Strip the codes and count the stories.",
                2: "Your patients joined coaching and hit the gym the month they started. Was it the drug?",
                3: "How many outcomes and subgroups did you open before one glowed?",
                4: "Beat my matched DPP-4 baseline on patients you have never seen, without counting the wait before the first fill."},
    truth="Semaglutide-class drugs cut the hazard of alcohol relapse by about a third (hazard ratio 0.65) in every site. "
          "The opioid effect is small (0.88) and smoking is unaffected. Users are healthier and more often in therapy, "
          "and counting the wait before the first fill as treated time inflates every naive estimate.",
)

BPC157_TENDON = Campaign(
    id="BPC157_TENDON", letter="B", title="The Wolverine Mirage",
    question="Do BPC-157 and TB-500 regenerate human tendons, or is it affiliate hype, rodent-only evidence "
             "and athletes who also do their rehab?",
    drug="BPC-157 / TB-500 (gray-market injections)", comparator="Physiotherapy-only rehabilitation",
    population="Adults with Achilles or rotator-cuff tendinopathy in sports-medicine clinics",
    outcomes=[Outcome("return", "No return to sport within a year", 0.32, 0.0),
              Outcome("reinjury", "Re-injury or rupture within a year", 0.15, 0.0),
              Outcome("pain", "Persistent pain at a year", 0.40, 0.0)],
    confounding={"healthy": 0.9, "trt": 0.6, "therapy": 0.5, "severity": -0.3},
    risk={"healthy": -0.45, "therapy": -0.35, "trt": -0.2, "severity": 0.5},
    scrolls=[
        Scroll("hype", "HYPE", "The Wolverine Scroll",
               "The 'Wolverine peptide': BPC-157 heals torn tendons in days.",
               outcome="return", outcomes_searched=3, subgroups_searched=7, design="ever",
               corpus=Corpus(posts=1600, affiliate=0.55, stories=14, affiliate_story_share=0.5),
               literature=Literature(human=0, rodent=31, in_vitro=8, labs=(0.82, 0.06, 0.06, 0.06)), n_rct=0,
               origin="a fitness influencer's injection vlog"),
        Scroll("pioneer", "PIONEER", "The Rehab Scroll",
               "BPC-157 shortens return to sport compared with physiotherapy alone, after adjusting for co-interventions.",
               outcome="return", design="ever",
               corpus=Corpus(posts=120, affiliate=0.1, stories=41, platforms=(0.2, 0.3, 0.5)),
               literature=Literature(human=1, rodent=14, labs=(0.75, 0.15, 0.1)), n_rct=0,
               plan=PIONEER_PLAN_SPECIES, origin="a sports physician's question about angiogenic peptides"),
        Scroll("preprint", "PREPRINT", "The Rat-Tendon Scroll",
               "A rodent angiogenesis preprint: TB-500 doubles tendon collagen in two weeks.",
               outcome="reinjury", subgroups_searched=7, design="ever",
               corpus=Corpus(posts=80, affiliate=0.4, stories=7, affiliate_story_share=0.3),
               literature=Literature(human=0, rodent=6, in_vitro=4, labs=(1.0,)), n_rct=0,
               plan=PREPRINT_PLAN, origin="a single-lab rat study"),
    ],
    gatekeeper={1: "{scroll} has more discount codes than patients. How many stories are left without them?",
                2: "Rats, Alchemist. And the humans who inject it also never miss physio. Was it the peptide?",
                3: "Name one completed human trial. One lab citing itself forty times is not replication.",
                4: "Beat my physio-only baseline on athletes you have never seen."},
    truth="BPC-157 and TB-500 have no effect on human tendon recovery in this world (hazard ratio 1.0). Users are fitter, "
          "more diligent with rehab and more often on testosterone, the literature is almost all rodent work from one lab, "
          "and no completed human trial exists.",
    effect_direction=-1,
)

LONGEVITY_STACK = Campaign(
    id="LONGEVITY_STACK", letter="C", title="The Longevity Stack",
    question="Do GHK-Cu and ipamorelin + CJC-1295 reverse biological age and add lean mass, or do healthy users, "
             "testosterone and training do the work?",
    drug="GHK-Cu / ipamorelin + CJC-1295", comparator="Matched non-users from the same longevity clinics",
    population="Adults attending longevity and men's-health clinics",
    outcomes=[Outcome("frailty", "Lean-mass loss or frailty diagnosis within a year", 0.25, 0.0),
              Outcome("epiage", "Epigenetic age advancing faster than calendar age", 0.45, 0.0),
              Outcome("skin", "Dermatology visit for skin ageing within a year", 0.30, 0.0)],
    confounding={"trt": 1.3, "healthy": 0.9, "therapy": 0.4},
    risk={"trt": -0.9, "healthy": -0.6, "age10": 0.2, "therapy": -0.2},
    scrolls=[
        Scroll("hype", "HYPE", "The Age-Reversal Scroll",
               "The peptide longevity stack stops biological ageing: epigenetic clocks run backwards.",
               outcome="epiage", outcomes_searched=3, subgroups_searched=7, design="ever",
               corpus=Corpus(posts=1100, affiliate=0.5, stories=25, affiliate_story_share=0.35),
               literature=Literature(human=2, rodent=10, in_vitro=12, labs=(0.4, 0.3, 0.3)), n_rct=0,
               origin="a biohacker's before-and-after thread"),
        Scroll("pioneer", "PIONEER", "The Lean-Mass Scroll",
               "Ipamorelin + CJC-1295 prevents lean-mass loss compared with matched non-users, adjusted for testosterone and training.",
               outcome="frailty", design="ever",
               corpus=Corpus(posts=150, affiliate=0.15, stories=46, platforms=(0.25, 0.3, 0.45)),
               literature=Literature(human=4, rodent=5, labs=(0.4, 0.3, 0.3)), n_rct=0,
               plan=PIONEER_PLAN, origin="growth-hormone secretagogue pharmacology"),
        Scroll("preprint", "PREPRINT", "The Copper-Peptide Scroll",
               "A 30-patient skin-clinic log: GHK-Cu users stop needing skin-ageing treatment.",
               outcome="skin", subgroups_searched=7, design="ever",
               corpus=Corpus(posts=90, affiliate=0.45, stories=10, affiliate_story_share=0.3),
               literature=Literature(human=1, in_vitro=9, labs=(1.0,)), n_rct=0,
               plan=PREPRINT_PLAN, origin="a dermatology clinic's newsletter"),
    ],
    gatekeeper={1: "{scroll} comes with a discount code and a supplement stack. Which part are you testing?",
                2: "Your users are on testosterone, doing zone-2 and counting calories. Adjust for them and look again.",
                3: "No completed human trial, and the best of twenty-one subgroups. Correct for the search.",
                4: "Beat my matched non-users on clients you have never seen."},
    truth="Neither peptide changes lean mass, epigenetic ageing or skin in this world (hazard ratio 1.0). Users are far more "
          "often on testosterone and in training, which explains every naive benefit.",
    effect_direction=-1,
)

GLP1_NAION = Campaign(
    id="GLP1_NAION", letter="D", title="The Ozempic Blindness Scare",
    question="Do GLP-1 agonists raise the risk of NAION ('Ozempic blindness'), or is the alarm diabetic-retinopathy "
             "severity and media amplification? Active comparator: SGLT2 inhibitors.",
    drug="GLP-1 receptor agonists", comparator="SGLT2 inhibitors (active comparator)",
    population="Adults with type 2 diabetes starting a second-line drug",
    outcomes=[Outcome("naion", "NAION diagnosis within a year", 0.004, math.log(1.5)),
              Outcome("retinopathy", "Diabetic-retinopathy progression within a year", 0.06, math.log(1.15)),
              Outcome("vision", "Any recorded vision loss within a year", 0.02, math.log(1.05))],
    n=40000,
    confounding={"severity": 0.7, "age10": 0.1, "healthy": 0.1},
    risk={"severity": 0.8, "age10": 0.35},
    scrolls=[
        Scroll("hype", "HYPE", "The Blindness-Panic Scroll",
               "'Ozempic blindness': GLP-1 drugs multiply the risk of NAION seven-fold.",
               outcome="naion", outcomes_searched=3, subgroups_searched=7, design="ever",
               corpus=Corpus(posts=2000, affiliate=0.08, stories=33, platforms=(0.5, 0.2, 0.3)),
               literature=Literature(human=6, labs=(0.4, 0.2, 0.2, 0.2)), n_rct=0,
               origin="a viral news segment"),
        Scroll("pioneer", "PIONEER", "The Small-Risk Scroll",
               "In new users, GLP-1 agonists carry a small increase in NAION risk compared with SGLT2 inhibitors.",
               outcome="naion", design="ever",
               corpus=Corpus(posts=110, affiliate=0.02, stories=52, platforms=(0.1, 0.4, 0.5)),
               literature=Literature(human=11, labs=(0.25, 0.25, 0.2, 0.15, 0.15)), n_rct=0,
               plan=PIONEER_PLAN, origin="an ophthalmology pharmacovigilance signal"),
        Scroll("preprint", "PREPRINT", "The Case-Series Scroll",
               "A 16-patient eye-clinic case series: semaglutide users lost their sight.",
               outcome="naion", subgroups_searched=7, design="ever",
               corpus=Corpus(posts=70, affiliate=0.05, stories=12),
               literature=Literature(human=1, labs=(1.0,)), n_rct=0,
               plan=PREPRINT_PLAN, origin="a single-centre case series"),
    ],
    gatekeeper={1: "{scroll} went viral on the evening news. How many independent patients are behind it?",
                2: "Sicker diabetics get GLP-1s, and sicker eyes fail. Adjust for severity first.",
                3: "No trial was built to see NAION. Correct for every outcome you peeked at.",
                4: "Beat my matched SGLT2 baseline on patients you have never seen."},
    truth="In this world GLP-1 agonists raise NAION risk by half (hazard ratio 1.5) on a tiny base rate of 0.4% a year, "
          "and nudge retinopathy progression (1.15). Sicker diabetics are more likely to get them. A seven-fold risk is "
          "not real; a small one is, but this cohort is too small to confirm it.",
    effect_direction=1,
)

CAMPAIGNS = {c.id: c for c in (GLP1_ADDICTION, BPC157_TENDON, LONGEVITY_STACK, GLP1_NAION)}
BY_LETTER = {c.letter: c for c in CAMPAIGNS.values()}

ARCHETYPES = {
    "HYPE": {"title": "Hype Scroll", "nickname": "Found on social media", "cls": "Hype"},
    "PIONEER": {"title": "Mechanistic Scroll", "nickname": "Clinically framed", "cls": "Pioneer"},
    "PREPRINT": {"title": "Preprint Scroll", "nickname": "Small study or animal preprint", "cls": "Preprint"},
    "SKEPTIC": {"title": "The Gatekeeper Skeptic", "nickname": "Warden of the Null", "cls": "Gatekeeper"},
}
HERO = {"name": "The Alchemist-Epidemiologist", "short": "The Alchemist"}

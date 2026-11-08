"""Which numbers a language model may write, and where. Context-sensitive, not a blanket ban on digits.

* Clinical nomenclature that happens to contain digits is fine: GLP-1, BPC-157, IL-6, HbA1c, type 2 diabetes,
  Phase 3, SGLT2, COVID-19.
* A measured statistic is never fine in model-written prose (p-values, confidence intervals, percentages,
  rate or hazard ratios, fold changes, sample sizes): only the Judge measures.
* The Scribe may not state an effect size in words either ("halves", "seven-fold"): the Judge tests the claimed
  direction and an important effect, not a size, so a size in the claim would be an untested assertion.
* The Alchemist may quote the Judge's released findings: any number it writes must be a correct rounding of a
  number in the payload it was shown (an attributed excerpt), or it is rejected.
A regex screen cannot prove a sentence true; it only refuses the patterns that would pass off a model's words
as a measurement. Typed fields carry everything else.
"""

from __future__ import annotations

import json
import re

NOMENCLATURE = re.compile(
    r"\bGLP-?1(?:\s?RAs?)?\b|\bBPC[- ]?157\b|\bTB-?500\b|\bCJC-?1295\b|\bGHK-?Cu\b|\bSGLT-?2i?\b|\bDPP-?4i?\b"
    r"|\bIL-?\d{1,2}\b|\bTNF-?\w*\b|\bHbA1c\b|\b(?:type|Type)\s?(?:1|2|I|II)\b|\bT[12]DM?\b"
    r"|\b[Pp]hase\s?(?:[1-4]|I{1,3}|IV)(?:/(?:[1-4]|I{1,3}|IV))?\b|\bCOVID-?19\b|\b(?:thymosin\s+)?beta-?4\b"
    r"|\b5-?HT\d?\w?\b|\bGIP\b|\bCYP\w+\b|\bApoE4\b|\bH\d\b", re.I)

MEASUREMENTS = [
    ("p-value", re.compile(r"\bp\s*(?:-?\s*value)?\s*(?:[<>=≤≥]|of|was|is)\s*0?\.\d|\bp\s*[<>=≤≥]\s*\d", re.I)),
    ("confidence interval", re.compile(r"\b(?:CI|confidence interval)\b[^.;]{0,24}\d|\d\s*%\s*CI\b", re.I)),
    ("percentage", re.compile(r"\d+(?:\.\d+)?\s*(?:%|percent\b|per\s?cent\b)", re.I)),
    ("ratio", re.compile(r"\b(?:a?RR|a?HR|a?OR|IRR|rate ratio|hazard ratio|odds ratio|risk ratio|relative risk)\b"
                         r"\s*(?:of|=|:|was|is|≈|~|at)?\s*\d", re.I)),
    ("fold change", re.compile(r"\d+(?:\.\d+)?\s*-?\s*(?:fold\b|x\b|×|times\b)", re.I)),
    ("sample size", re.compile(r"\bn\s*=\s*\d", re.I)),
]
MAGNITUDE_WORDS = re.compile(r"\b(?:halv(?:e|es|ed|ing)|doubl(?:e|es|ed|ing)|tripl(?:e|es|ed|ing)|quadrupl\w*"
                             r"|(?:two|three|four|five|six|seven|eight|nine|ten)-fold|tenfold|twofold|threefold)\b", re.I)
TIME_WINDOWS = re.compile(r"\b(?:within|in|after)\s+(?:a\s+few\s+|two\s+|three\s+)?(?:days?|weeks?|months?)\b"
                          r"|\bovernight\b|\bimmediately\b|\blong[- ]term\b|\bdecades?\b", re.I)
NUMBER = re.compile(r"(?<![\w.])\d+(?:\.\d+)?|(?<![\w.])\.\d+")

# words that name a population, mapped to the cohort's subgroup each one means
SUBGROUP_WORDS = {
    "women": re.compile(r"\b(?:women|woman|female|females)\b", re.I),
    "men": re.compile(r"\b(?:men|man|male|males)\b", re.I),
    "50 and over": re.compile(r"\b(?:over|above)\s+50\b|\b50\s*(?:\+|and over|or older|plus)\b|\bolder\b|\belderly\b"
                              r"|\bseniors?\b", re.I),
    "under 50": re.compile(r"\bunder\s+50\b|\bbelow\s+50\b|\byounger\b|\byoung adults?\b", re.I),
    "higher severity": re.compile(r"\bhigher[- ]severity\b|\bsicker\b|\b(?:more|most)\s+severe\b"
                                  r"|\bsevere\s+(?:disease|diabetes|cases|patients|users|tendinopathy|addiction|disorder)\b",
                                  re.I),
    "lower severity": re.compile(r"\blower[- ]severity\b|\bearly[- ]stage\b"
                                 r"|\bmild(?:er)?\s+(?:disease|diabetes|cases|patients|users|tendinopathy|addiction|disorder)\b",
                                 re.I),
}
AGE_PHRASES = re.compile(r"\b(?:under|over|above|below)\s+50\b|\b50\s*(?:\+|and over|or older|plus)\b", re.I)


def strip_nomenclature(text: str) -> str:
    return NOMENCLATURE.sub(" ", text or "")


def measurement_assertions(text: str) -> list[str]:
    """The kinds of measured statistic the text asserts (after clinical names are set aside)."""
    t = strip_nomenclature(text)
    return [name for name, rx in MEASUREMENTS if rx.search(t)]


def numbers(text: str) -> list[tuple[float, int]]:
    """Every number left once clinical names are removed, with how many decimals it was written with."""
    out = []
    for m in NUMBER.finditer(strip_nomenclature(text)):
        s = m.group(0)
        out.append((float(s), len(s.split(".", 1)[1]) if "." in s else 0))
    return out


def subgroups_named(text: str) -> set[str]:
    return {g for g, rx in SUBGROUP_WORDS.items() if rx.search(text or "")}


def check_scribe(text: str, subgroup: str = "everyone") -> str | None:
    """Why a sentence the Scribe wrote is not acceptable, or None. Typed fields carry the numbers."""
    found = measurement_assertions(text)
    if found:
        return f"asserts a measured statistic ({found[0]}): only the Judge measures"
    if MAGNITUDE_WORDS.search(text or ""):
        return "states an effect size the Judge does not test: claim a direction, not a size"
    if TIME_WINDOWS.search(text or ""):
        return "names a time window the one-year estimand does not test"
    rest = strip_nomenclature(text)
    if subgroup in ("under 50", "50 and over"):
        rest = AGE_PHRASES.sub(" ", rest)
    if NUMBER.search(rest):
        return "contains a number outside a typed field"
    named = subgroups_named(text) - {subgroup}
    if named:
        return f"names a population ({sorted(named)[0]}) that its typed subgroup ({subgroup}) does not encode"
    return None


def payload_numbers(payload) -> list[float]:
    return [v for v, _ in numbers(json.dumps(payload, default=str))]


def check_attributed(text: str, allowed: list[float]) -> str | None:
    """Every number in the text must be a correct rounding of a number the writer was shown."""
    for value, decimals in numbers(text):
        tol = 0.5 * 10 ** (-decimals) + 1e-9
        if not any(abs(value - v) <= tol for v in allowed):
            return f"writes the number {value:g}, which is not in the findings it was shown"
    return None

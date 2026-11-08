"""External evidence intake and verification for the Research Director's console.

Step 1 intake records what the Director submitted. Step 2 verification tries to retrieve and identify the
source (who published it, when, what it contains, whether the claim appears in it, whether it is relevant).
Step 3 classifies it. Nothing here executes, renders or follows instructions inside a submission: pages are
read as bytes, tags are stripped with regular expressions, CSVs are parsed by the csv module with size
limits, and PDFs are not opened at all.

A verified source does not make its claim true. A claim that cannot be verified is kept, labelled UNVERIFIED.
"""

from __future__ import annotations

import base64
import binascii
import csv
import hashlib
import http.client
import io
import ipaddress
import re
import socket
import ssl
import threading
import time
from urllib.parse import urlparse

from . import rules

CLASSES = ["VERIFIED AND TESTABLE", "VERIFIED BUT NOT DIRECTLY TESTABLE", "UNVERIFIED", "IRRELEVANT",
           "INVALID OR INCOMPATIBLE DATA", "REQUIRES ADDITIONAL EVIDENCE"]

SOURCE_TYPES = [  # (domain suffixes, type, evidence tier label, tier)
    (("twitter.com", "x.com", "reddit.com", "youtube.com", "youtu.be", "tiktok.com", "facebook.com", "instagram.com",
      "threads.net", "quora.com", "medium.com", "substack.com", "bsky.app", "linkedin.com"),
     "social media or blog", "an anecdote or opinion: the weakest kind of evidence", 1),
    (("medrxiv.org", "biorxiv.org", "arxiv.org", "ssrn.com", "researchsquare.com", "preprints.org"),
     "preprint", "a preprint: not yet peer reviewed", 2),
    (("doi.org", "pubmed.ncbi.nlm.nih.gov", "ncbi.nlm.nih.gov", "europepmc.org", "nejm.org", "thelancet.com",
      "bmj.com", "jamanetwork.com", "nature.com", "sciencedirect.com", "springer.com", "link.springer.com",
      "wiley.com", "onlinelibrary.wiley.com", "cell.com", "plos.org", "journals.plos.org", "academic.oup.com",
      "clinicaltrials.gov", "cochranelibrary.com"),
     "peer-reviewed journal or trial registry", "peer-reviewed research or a registry record", 3),
    ((".gov", ".gov.uk", "who.int", "europa.eu", "nhs.uk", "ema.europa.eu", "ons.gov.uk"),
     "government or agency", "an official agency publication or dataset", 3),
    (("bbc.co.uk", "bbc.com", "nytimes.com", "reuters.com", "theguardian.com", "cnn.com", "statnews.com",
      "washingtonpost.com", "apnews.com", "ft.com", "economist.com", "wsj.com", "bloomberg.com", "npr.org"),
     "news article", "a news report about research: second-hand", 1),
]

MAX_FETCH_BYTES = 1_000_000
FETCH_DEADLINE = 3.0        # seconds for the whole fetch: resolving, connecting and reading
FETCH_TYPES = ("text/html", "application/xhtml+xml", "text/plain", "text/csv", "text/markdown", "application/json")
STOPWORDS = set("the a an and or of to in on for with that this is are was were be been it its as at by from than "
                "more less into over under not no new study studies says claims claim show shows showed found "
                "find i you we they he she have has had do does did can could would should may might".split())


class Fetcher:
    """Retrieves a URL safely. http(s) only, no user name or password in the link, and only public (globally routable)
    addresses. The address that was checked is the address connected to: the connection is pinned to it, so a second
    DNS answer cannot swap in a private one (DNS rebinding). TLS still verifies the certificate for the host name.
    Redirects are never followed. One deadline covers the whole fetch, and the body, its size and its type are capped."""

    def __call__(self, url: str) -> dict:
        p = urlparse(url)
        if p.scheme not in ("http", "https") or not p.hostname:
            return {"ok": False, "error": "only http and https links can be retrieved"}
        if p.username is not None or p.password is not None:
            return {"ok": False, "error": "links that carry a user name or password are never fetched"}
        try:
            port = p.port or (443 if p.scheme == "https" else 80)
        except ValueError:
            return {"ok": False, "error": "the link has an invalid port"}
        deadline = time.monotonic() + FETCH_DEADLINE
        infos = _resolve(p.hostname, port, FETCH_DEADLINE)
        if isinstance(infos, str):
            return {"ok": False, "error": infos}
        addrs = []
        for info in infos:
            ip = ipaddress.ip_address(info[4][0].split("%", 1)[0])
            if not ip.is_global or ip.is_multicast:
                return {"ok": False, "error": "the link points at a private or local address, which is never fetched"}
            addrs.append(str(ip))
        if not addrs:
            return {"ok": False, "error": "the host could not be resolved"}
        conn = (_PinnedHTTPS(p.hostname, addrs[0], port, FETCH_DEADLINE) if p.scheme == "https"
                else _PinnedHTTP(p.hostname, addrs[0], port, FETCH_DEADLINE))
        path = (p.path or "/") + (f"?{p.query}" if p.query else "")
        try:
            conn.request("GET", path, headers={"User-Agent": "HypothesisGauntlet-EvidenceCheck/1.1",
                                               "Accept": ", ".join(FETCH_TYPES), "Accept-Encoding": "identity",
                                               "Connection": "close"})
            r = conn.getresponse()
            if 300 <= r.status < 400:
                return {"ok": False, "error": f"the link redirects (HTTP {r.status}); submit the final address instead"}
            if r.status >= 400:
                return {"ok": False, "error": f"the server answered HTTP {r.status}"}
            ctype = r.getheader("Content-Type", "") or ""
            if ctype.split(";")[0].strip().lower() not in FETCH_TYPES:
                return {"ok": False, "error": f"the server sent {ctype or 'no content type'}, which the checker does not read"}
            body = bytearray()
            while True:
                left = deadline - time.monotonic()
                if left <= 0:
                    return {"ok": False, "error": f"the source took longer than {FETCH_DEADLINE:g} seconds to send"}
                if conn.sock is not None:
                    conn.sock.settimeout(left)
                chunk = r.read1(65536) if hasattr(r, "read1") else r.read(65536)
                if not chunk:
                    break
                body += chunk
                if len(body) > MAX_FETCH_BYTES:
                    return {"ok": False, "error": "the page is larger than the 1 MB the checker reads"}
        except Exception as e:  # network policy, timeout, TLS, a malformed reply: all mean "not retrieved"
            return {"ok": False, "error": f"the source could not be retrieved ({e.__class__.__name__}: {str(e)[:120]})"}
        finally:
            conn.close()
        return {"ok": True, "status": r.status, "content_type": ctype, "bytes": len(body), "address": addrs[0],
                "sha256": hashlib.sha256(bytes(body)).hexdigest(), "text": bytes(body).decode("utf-8", errors="replace")}


def _resolve(host: str, port: int, timeout: float):
    """getaddrinfo with a deadline (it has none of its own). A list of address records, or an error message."""
    out: dict = {}

    def run():
        try:
            out["infos"] = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
        except OSError as e:
            out["error"] = f"the host could not be resolved ({e.__class__.__name__})"

    t = threading.Thread(target=run, daemon=True)
    t.start()
    t.join(timeout)
    if t.is_alive():
        return "the host took too long to resolve"
    return out.get("error") or out.get("infos") or "the host could not be resolved"


class _PinnedHTTP(http.client.HTTPConnection):
    """An HTTP connection to one already-checked address; the Host header still names the host."""

    def __init__(self, host: str, address: str, port: int, timeout: float):
        super().__init__(host, port, timeout=timeout)
        self._address = address

    def connect(self):
        self.sock = socket.create_connection((self._address, self.port), self.timeout)


class _PinnedHTTPS(http.client.HTTPSConnection):
    """An HTTPS connection to one already-checked address, verifying the certificate for the host name (SNI)."""

    def __init__(self, host: str, address: str, port: int, timeout: float):
        super().__init__(host, port, timeout=timeout, context=ssl.create_default_context())
        self._address = address

    def connect(self):
        sock = socket.create_connection((self._address, self.port), self.timeout)
        self.sock = self._context.wrap_socket(sock, server_hostname=self.host)


def source_type(url: str) -> dict:
    host = (urlparse(url).hostname or "").lower()
    for suffixes, kind, tier_label, tier in SOURCE_TYPES:
        if any(host == s or host.endswith("." + s.lstrip(".")) or (s.startswith(".") and host.endswith(s)) for s in suffixes):
            return {"type": kind, "tier": tier, "tier_label": tier_label, "host": host}
    return {"type": "website", "tier": 1, "tier_label": "an unclassified website: provenance unknown", "host": host}


META = {
    "title": ["citation_title", "dc.title", "og:title"],
    "publisher": ["citation_publisher", "citation_journal_title", "dc.publisher", "og:site_name", "publisher"],
    "published": ["citation_publication_date", "citation_date", "citation_online_date", "dc.date",
                  "article:published_time", "date", "pubdate"],
    "author": ["citation_author", "dc.creator", "author"],
}


def read_page(html: str) -> dict:
    """Metadata and visible text from an HTML page, by regular expression only (nothing is rendered or run)."""
    metas = {}
    for m in re.finditer(r"<meta\s+[^>]*>", html, flags=re.I):
        tag = m.group(0)
        name = re.search(r"(?:name|property)\s*=\s*[\"']([^\"']+)[\"']", tag, re.I)
        content = re.search(r"content\s*=\s*[\"']([^\"']*)[\"']", tag, re.I)
        if name and content:
            metas.setdefault(name.group(1).lower(), content.group(1).strip())
    out = {k: next((metas[n] for n in names if metas.get(n)), None) for k, names in META.items()}
    if not out["title"]:
        t = re.search(r"<title[^>]*>(.*?)</title>", html, re.I | re.S)
        out["title"] = re.sub(r"\s+", " ", t.group(1)).strip()[:200] if t else None
    text = re.sub(r"<(script|style|noscript)[^>]*>.*?</\1>", " ", html, flags=re.I | re.S)
    text = re.sub(r"<[^>]+>", " ", text)
    out["text"] = re.sub(r"\s+", " ", text)[:200_000]
    return out


def words(s: str) -> set:
    return {w for w in re.findall(r"[a-z][a-z0-9\-]{2,}", (s or "").lower()) if w not in STOPWORDS}


def campaign_terms(c) -> set:
    base = " ".join([c.drug, c.comparator, c.population, c.question] + [o.label for o in c.outcomes])
    terms = words(base) - {"within", "year", "adults", "active", "comparator", "really", "recorded", "diagnosis"}
    extra = {"glp-1", "glp1", "semaglutide", "tirzepatide", "ozempic", "wegovy", "mounjaro", "peptide", "peptides",
             "bpc-157", "tb-500", "ghk-cu", "ipamorelin", "naion"}
    return terms | {t for t in extra if t in base.lower() or t.replace("-", "") in base.lower().replace("-", "")}


def parse_csv(text: str) -> dict:
    """A user dataset for a Secret Research Level: needs a 0/1 treatment column and a 0/1 outcome column."""
    try:
        sample = text[:4096]
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t") if sample.strip() else csv.excel
    except csv.Error:
        dialect = csv.excel
    rows = list(csv.reader(io.StringIO(text), dialect))
    if len(rows) < 2:
        return {"ok": False, "error": "the file has no data rows"}
    header = [h.strip().lower() for h in rows[0]]
    body = rows[1:]
    if len(body) > rules.UPLOAD_MAX_ROWS:
        return {"ok": False, "error": f"more than {rules.UPLOAD_MAX_ROWS} rows"}
    if len(header) > 50:
        return {"ok": False, "error": "more than 50 columns"}
    t_col = next((header.index(h) for h in ("treated", "exposed", "treatment", "drug") if h in header), None)
    y_col = next((header.index(h) for h in ("event", "outcome", "relapse", "y") if h in header), None)
    s_col = next((header.index(h) for h in ("site", "region", "location") if h in header), None)
    if t_col is None or y_col is None:
        return {"ok": False, "error": "it needs a 0/1 'treated' (or 'exposed') column and a 0/1 'event' (or 'outcome') column",
                "columns": header}
    t, y, site, bad = [], [], [], 0
    for r in body:
        try:
            tv, yv = int(float(r[t_col])), int(float(r[y_col]))
        except (ValueError, IndexError):
            bad += 1
            continue
        if tv not in (0, 1) or yv not in (0, 1):
            bad += 1
            continue
        t.append(tv)
        y.append(yv)
        site.append(r[s_col].strip() if s_col is not None and s_col < len(r) else "")
    return {"ok": True, "columns": header, "rows": len(body), "usable": len(t), "dropped": bad,
            "treated": t, "event": y, "site": site,
            "summary": {"rows": len(body), "usable": len(t), "dropped": bad, "treated": sum(t),
                        "untreated": len(t) - sum(t), "events": sum(y),
                        "sites": len({s for s in site if s})}}


def intake(sub: dict, ctx: dict, route: dict, fetch=None) -> dict:
    """Steps 1 to 3: record, verify, classify. Returns the intake record (the Evidence Ledger row's payload)."""
    c = ctx["campaign"]
    rec = {
        "claim": (sub.get("text") or "").strip()[:2000], "url": (sub.get("url") or "").strip()[:500] or None,
        "filename": sub.get("filename"), "submitted_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "question": c.question, "target": ctx.get("target"), "level": ctx.get("level"),
        "kind": "file" if sub.get("filename") else "url" if sub.get("url") else "text",
        "source": None, "retrieval": None, "publisher": None, "published": None, "title": None,
        "contains": None, "claim_represented": None, "relevance": None, "decision_time": None,
        "testable": route.get("archetype"), "dataset": None, "classification": None, "missing": [], "notes": [],
    }
    terms = campaign_terms(c)
    text_terms = words(rec["claim"]) & terms
    content = ""

    if rec["kind"] == "file":
        _intake_file(rec, sub)
    elif rec["kind"] == "url":
        st = source_type(rec["url"])
        rec["source"] = st
        if not re.match(r"^https?://", rec["url"], re.I):
            rec["classification"] = "INVALID OR INCOMPATIBLE DATA"
            rec["missing"].append("a full http(s) link")
        else:
            got = (fetch or Fetcher())(rec["url"])
            rec["retrieval"] = {k: v for k, v in got.items() if k != "text"}
            rec["sha256"] = got.get("sha256")
            if got.get("ok"):
                ctype = got.get("content_type", "")
                page = read_page(got["text"]) if "html" in ctype or got["text"].lstrip().startswith("<") else \
                    {"title": None, "publisher": None, "published": None, "author": None, "text": got["text"][:200_000]}
                content = page["text"]
                rec.update(title=page["title"], publisher=page["publisher"], published=page["published"])
                rec["contains"] = f"{len(content):,} characters of text ({ctype or 'unknown type'})"
                cw = words(rec["claim"]) - {"study", "paper", "article"}
                found = cw & words(content)
                rec["claim_represented"] = (len(found) / len(cw) >= 0.6) if cw else None
            else:
                rec["missing"].append(got.get("error", "the source could not be retrieved"))
    else:
        rec["source"] = {"type": "the Director's own statement", "tier": 0,
                         "tier_label": "a claim with no source attached", "host": None}

    content_terms = words(content) & terms if content else set()
    rec["relevance"] = {"campaign_terms": sorted(text_terms | content_terms)[:12],
                        "challenges_the_hero": bool(route.get("archetype")),
                        "relevant": bool(text_terms or content_terms or route.get("archetype") or rec["dataset"])}
    rec["decision_time"] = ("This campaign is simulated and date-shifted, so whether a source was available at the "
                            "historical decision time cannot be checked; it is treated as new information arriving now.")
    if rec["classification"] is None:
        rec["classification"] = _classify(rec)
    if rec["classification"] == "UNVERIFIED" and rec["kind"] == "text":
        rec["missing"].append("a retrievable source (a paper, registry entry or dataset) for the claimed result")
    return rec


def _intake_file(rec: dict, sub: dict) -> None:
    name = (sub.get("filename") or "").lower()
    rec["source"] = {"type": "uploaded file", "tier": 1, "tier_label": "a user-supplied file: publisher unconfirmed",
                     "host": None}
    try:
        raw = base64.b64decode(sub.get("content_b64") or "", validate=True)
    except (binascii.Error, ValueError):
        rec["classification"] = "INVALID OR INCOMPATIBLE DATA"
        rec["missing"].append("a readable file")
        return
    rec["retrieval"] = {"ok": True, "bytes": len(raw)}
    rec["sha256"] = hashlib.sha256(raw).hexdigest()
    if len(raw) > rules.UPLOAD_MAX_BYTES:
        rec["classification"] = "INVALID OR INCOMPATIBLE DATA"
        rec["missing"].append("a file under 1 MB")
        return
    if name.endswith(".pdf") or raw[:5] == b"%PDF-":
        rec["classification"] = "REQUIRES ADDITIONAL EVIDENCE"
        rec["missing"].append("PDFs are not opened here; paste the reported result and a link to its source")
        return
    if not name.endswith((".csv", ".tsv", ".txt", ".json", ".md")):
        rec["classification"] = "INVALID OR INCOMPATIBLE DATA"
        rec["missing"].append("a supported file type (.csv, .tsv, .txt, .json, .md)")
        return
    text = raw.decode("utf-8", errors="replace")
    if name.endswith((".csv", ".tsv")):
        ds = parse_csv(text)
        if not ds["ok"]:
            rec["classification"] = "INVALID OR INCOMPATIBLE DATA"
            rec["missing"].append(ds["error"])
            rec["dataset"] = {"columns": ds.get("columns")}
            return
        rec["dataset"] = ds["summary"] | {"columns": ds["columns"]}
        rec["contains"] = (f"{ds['summary']['usable']} usable rows ({ds['summary']['treated']} treated, "
                           f"{ds['summary']['events']} events)")
        rec["_data"] = {"treated": ds["treated"], "event": ds["event"], "site": ds["site"]}
        if ds["usable"] < rules.SECRET_MIN_ROWS:
            rec["classification"] = "REQUIRES ADDITIONAL EVIDENCE"
            rec["missing"].append(f"at least {rules.SECRET_MIN_ROWS} usable rows to run a test")
        else:
            rec["classification"] = "VERIFIED AND TESTABLE"
            rec["notes"].append("Verified means the file was parsed and its contents checked. Who collected it is as you "
                                "stated and is recorded as user-supplied.")
        return
    rec["claim"] = (rec["claim"] + " " + text[:2000]).strip()
    rec["contains"] = f"{len(text):,} characters of text"


def _classify(rec: dict) -> str:
    rel = rec["relevance"]["relevant"]
    if rec["kind"] == "url":
        if not (rec["retrieval"] or {}).get("ok"):
            return "UNVERIFIED" if rel else "IRRELEVANT"
        if not rel:
            return "IRRELEVANT"
        if rec["claim_represented"] is False:
            rec["missing"].append("the page does not appear to contain the claim as you described it")
            return "REQUIRES ADDITIONAL EVIDENCE"
        if not rec["publisher"] or not rec["published"]:
            rec["missing"].append("who published it" if not rec["publisher"] else "when it was published")
            return "REQUIRES ADDITIONAL EVIDENCE"
        return "VERIFIED AND TESTABLE" if rec["testable"] else "VERIFIED BUT NOT DIRECTLY TESTABLE"
    if not rel:
        return "IRRELEVANT"
    return "UNVERIFIED"


def public(rec: dict) -> dict:
    return {k: v for k, v in rec.items() if not k.startswith("_")}

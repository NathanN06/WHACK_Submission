"""The Statistical Judge for the Peptide & GLP-1 edition. Deterministic: same world, same scroll, same numbers.

Models are fitted here with plain IRLS (no extra dependencies): Poisson rate models with a
person-time offset for effects, logistic models for propensity scores and one-year risk.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from scipy import stats

from . import rules
from .world import COVARIATES, SITES, SUBGROUPS, World


@dataclass
class ScrollState:
    """How the hero is currently testing one scroll. Abilities change it; the Judge reads it.

    `direction` and `subgroup` are the typed claim: the sign the scroll says the effect has (-1 lowers the
    outcome event, +1 raises it) and the population it is about. Every test below is run in that subgroup,
    and a gain only counts if the measured effect points the way the claim says."""
    outcome: str
    design: str = "ever"
    adjusted: bool = False
    denoised: bool = False
    species_guard: bool = False
    replicated: bool = False
    K: int = 1
    ablated: bool = False
    subgroup: str = "everyone"
    direction: int = -1


# ---------- model fitting ----------

def poisson_fit(X: np.ndarray, y: np.ndarray, pt: np.ndarray, iters: int = 30):
    """log E[y] = log(pt) + [1, X] b. Returns (b, se)."""
    A = np.column_stack([np.ones(len(y)), X])
    off = np.log(np.maximum(pt, 1e-9))
    b = np.zeros(A.shape[1])
    b[0] = math.log(max(y.sum(), 1) / max(pt.sum(), 1e-9))
    for _ in range(iters):
        mu = np.exp(np.clip(off + A @ b, -30, 30))
        H = A.T @ (A * mu[:, None]) + 1e-8 * np.eye(A.shape[1])
        step = np.linalg.solve(H, A.T @ (y - mu))
        b += step
        if np.max(np.abs(step)) < 1e-8:
            break
    mu = np.exp(np.clip(off + A @ b, -30, 30))
    cov = np.linalg.inv(A.T @ (A * mu[:, None]) + 1e-8 * np.eye(A.shape[1]))
    return b, np.sqrt(np.diag(cov))


def logistic_fit(X: np.ndarray, y: np.ndarray, iters: int = 40, ridge: float = 1e-4) -> np.ndarray:
    A = np.column_stack([np.ones(len(y)), X])
    b = np.zeros(A.shape[1])
    for _ in range(iters):
        p = 1 / (1 + np.exp(-np.clip(A @ b, -30, 30)))
        W = np.maximum(p * (1 - p), 1e-9)
        H = A.T @ (A * W[:, None]) + ridge * np.eye(A.shape[1])
        step = np.linalg.solve(H, A.T @ (y - p) - ridge * b)
        b += step
        if np.max(np.abs(step)) < 1e-8:
            break
    return b


def logistic_predict(b: np.ndarray, X: np.ndarray) -> np.ndarray:
    return 1 / (1 + np.exp(-np.clip(b[0] + X @ b[1:], -30, 30)))


def p_two(z: float) -> float:
    return float(2 * stats.norm.sf(abs(z)))


def sidak(p: float, K: int) -> float:
    return float(-np.expm1(K * np.log1p(-min(p, 1 - 1e-16))))


# ---------- effects ----------

def effect(w: World, outcome: str, design: str, adjusted: bool, mask: np.ndarray) -> dict:
    """Log rate ratio of the drug (exposure) on the outcome, with its Wald p-value."""
    r = w.rows(outcome, design, mask)
    X = r["exposed"][:, None]
    if adjusted:
        X = np.column_stack([X, w.covariates(r["i"])])
    b, se = poisson_fit(X, r["event"], r["pt"])
    beta, s = float(b[1]), float(se[1])
    return {"beta": beta, "se": s, "rr": math.exp(beta), "p": p_two(beta / s), "events": int(r["event"].sum()),
            "exposed_pt": float(r["pt"][r["exposed"] == 1].sum()), "pt": float(r["pt"].sum())}


def balance(w: World, mask: np.ndarray) -> list[dict]:
    """Standardized mean differences of each confounder between peptide users and comparators."""
    t = w.peptide[mask]
    out = []
    for k in COVARIATES:
        x = w.X[k][mask]
        a, b = x[t], x[~t]
        sd = math.sqrt((a.var() + b.var()) / 2) or 1.0
        out.append({"covariate": k, "smd": float((a.mean() - b.mean()) / sd)})
    return out


# ---------- Level 1: the Rumour Dungeon ----------

def level1(w: World, s, st: ScrollState) -> dict:
    posts = w.corpus(s, denoised=st.denoised)
    raw_posts = w.corpus(s) if st.denoised else posts
    n = len(posts)
    by = {p: {"organic": 0, "affiliate": 0} for p in ("YouTube", "Quora", "Reddit")}
    for p in raw_posts:
        by[p["platform"]]["affiliate" if p["affiliate"] else "organic"] += 1
    phi = sum(p["affiliate"] for p in posts) / n if n else 0.0
    clusters = {p["cluster"] for p in posts}
    n_eff = len(clusters)
    sizes = np.bincount([p["cluster"] for p in raw_posts]) if raw_posts else np.array([0])
    return {"posts": len(raw_posts), "posts_counted": n, "phi": phi, "n_eff": n_eff,
            "reposts": int(sum(p["repost"] for p in raw_posts)), "largest_echo": int(sizes.max()),
            "by_platform": by, "denoised": st.denoised}


def d_l1(m: dict) -> dict:
    return {"affiliate": 15 * m["phi"], "neff": 15 * max(0.0, 1 - m["n_eff"] / rules.N_EFF_FULL)}


# ---------- Level 2: the Forgotten Archives ----------

def level2(w: World, s, st: ScrollState) -> dict:
    papers = w.papers(s)
    n = len(papers)
    human = sum(p["species"] == "human" for p in papers)
    tau = (n - human) / n if n else 0.0
    train = w.mask("train") & w.subgroup(st.subgroup)
    naive = effect(w, st.outcome, st.design, False, train)
    adj = effect(w, st.outcome, st.design, True, train)
    shift = min(1.0, abs(naive["beta"] - adj["beta"]) / max(abs(naive["beta"]), 1e-9))
    # what adjusting costs or buys in precision: the same rows, so any change in the interval is the model's
    precision = {"se_naive": naive["se"], "se_adjusted": adj["se"], "ci_width_ratio": adj["se"] / max(naive["se"], 1e-12)}
    return {"papers": n, "human": human, "rodent": sum(p["species"] == "rodent" for p in papers),
            "in_vitro": sum(p["species"] == "in vitro" for p in papers), "tau": tau,
            "naive": naive, "adjusted": adj, "shift": shift, "balance": balance(w, train), "precision": precision,
            "subgroup": st.subgroup}


def d_l2(m: dict, species_guard: bool, bias_detection: bool) -> dict:
    tau = 22 * m["tau"] * (rules.SPECIES_GUARD_M if species_guard and m["human"] > 0 else 1.0)
    return {"rodent": tau, "confound": 0.0 if bias_detection else 20 * m["shift"]}


# ---------- Level 3: the Temple of Replication ----------

def search_grid(w: World, s, st: ScrollState) -> list[tuple[str, str]]:
    """The outcome-and-subgroup combinations the scroll's search opened, its own claim always first."""
    if st.K == 1:
        return [(st.outcome, st.subgroup)]
    outcomes = [st.outcome] + [o.key for o in w.c.outcomes if o.key != st.outcome]
    groups = [st.subgroup] + [g for g in SUBGROUPS if g != st.subgroup]
    return [(o, g) for o in outcomes[: s.outcomes_searched] for g in groups[: s.subgroups_searched]]


def cochran_q(sites: list[dict]) -> dict:
    """Between-site heterogeneity of the per-site log rate ratios (inverse-variance weights)."""
    b = np.array([x["beta"] for x in sites])
    v = np.array([max(x["se"], 1e-9) ** 2 for x in sites])
    wts = 1 / v
    pooled = float((wts * b).sum() / wts.sum())
    Q = float((wts * (b - pooled) ** 2).sum())
    df = len(sites) - 1
    return {"q": Q, "df": df, "p": float(stats.chi2.sf(Q, df)) if df > 0 else 1.0,
            "i2": max(0.0, (Q - df) / Q) if Q > 0 else 0.0, "pooled_beta": pooled}


def level3(w: World, s, st: ScrollState) -> dict:
    train = w.mask("train")
    grid = search_grid(w, s, st)
    tests = []
    for o, g in grid:
        e = effect(w, o, st.design, st.adjusted, train & w.subgroup(g))
        tests.append({"outcome": o, "subgroup": g, "rr": e["rr"], "p": e["p"]})
    best = min(tests, key=lambda t: t["p"])
    K = len(grid)
    p_corr = sidak(best["p"], K)
    sites = []
    mine = train & w.subgroup(st.subgroup)
    for k, (name, rural) in enumerate(SITES):
        e = effect(w, st.outcome, st.design, st.adjusted, mine & (w.site == k))
        sites.append({"site": name, "rural": rural, "rr": e["rr"], "p": e["p"], "beta": e["beta"], "se": e["se"]})
    papers = w.papers(s)
    counts: dict[str, float] = {}
    for p in papers:
        counts[p["lab"]] = counts.get(p["lab"], 0) + 1
    direction = st.direction   # the scroll's claimed direction, never the campaign's
    replicating = [x for x in sites if x["p"] < rules.ALPHA and np.sign(x["beta"]) == direction]
    if st.replicated and replicating:
        unit = len(papers) / max(1, len(counts)) if papers else 1.0
        for x in replicating:
            counts[x["site"]] = counts.get(x["site"], 0) + unit
    total = sum(counts.values())
    h_lab = sum((v / total) ** 2 for v in counts.values()) if total else 1.0
    return {"K": K, "best": best, "tests": tests, "p_raw": best["p"], "p_corr": p_corr, "sites": sites,
            "replicating": [x["site"] for x in replicating], "h_lab": h_lab, "labs": counts,
            "n_rct": s.n_rct, "shielded": st.replicated, "heterogeneity": cochran_q(sites),
            "declared": {"outcome": st.outcome, "subgroup": st.subgroup}}


def d_l3(m: dict) -> dict:
    return {"sidak": 20.0 * (m["p_corr"] > rules.ALPHA), "hlab": 20 * m["h_lab"], "rct": 25.0 * (m["n_rct"] == 0)}


# ---------- Level 4: the Citadel of Truth ----------

def immortal_share(w: World, outcome: str, design: str, mask: np.ndarray) -> float:
    """Share of the 'exposed' person-time that came before the first fill (zero in a new-user design)."""
    if design != "ever":
        return 0.0
    r = w.rows(outcome, "ever", mask)
    exposed = r["exposed"] == 1
    if not exposed.any():
        return 0.0
    S = w.start[r["i"][exposed]]
    return float(np.minimum(S, r["pt"][exposed]).sum() / r["pt"][exposed].sum())


def level4(w: World, s, st: ScrollState) -> dict:
    train = w.mask("train") & w.subgroup(st.subgroup)
    share = immortal_share(w, st.outcome, st.design, train)
    l_time = int(st.design == "ever" and share > 0.01)
    cur = effect(w, st.outcome, st.design, st.adjusted, train)
    purged = effect(w, st.outcome, "new_user", st.adjusted, train)
    delta = min(1.0, abs(cur["beta"] - purged["beta"]) / max(abs(cur["beta"]), 1e-9)) if l_time else 0.0
    beta = 0.0 if st.ablated else cur["beta"]
    g = guardian(w, st.outcome, beta, subgroup=st.subgroup)
    return {"immortal_share": share, "l_time": l_time, "beta_current": cur["beta"], "beta_purged": purged["beta"],
            "rr_current": cur["rr"], "rr_purged": purged["rr"], "delta_purge": delta, "beta_used": beta,
            "direction_claimed": st.direction, "direction_ok": direction_ok(beta, st.direction), **g}


def direction_ok(beta: float, direction: int) -> bool:
    """Does the effect the scroll carries point the way its claim says? A dropped (ablated) term never does."""
    return beta != 0.0 and int(np.sign(beta)) == int(direction)


def risk_models(w: World, outcome: str, mask: np.ndarray):
    nu = w.new_user(outcome, mask)
    X = w.covariates(nu["i"])
    pooled = logistic_fit(X, nu["y"])
    comp = nu["treated"] == 0
    comparator = logistic_fit(X[comp], nu["y"][comp])
    ps = logistic_fit(X, nu["treated"])
    return pooled, comparator, ps


def match(ps_t: np.ndarray, ps_c: np.ndarray, caliper: float = rules.CALIPER) -> list[tuple[int, int]]:
    """Greedy 1:1 nearest-neighbour matching on the propensity score, without replacement."""
    order = np.argsort(-ps_t)  # hardest to match first
    free = np.ones(len(ps_c), bool)
    pairs = []
    for i in order:
        d = np.where(free, np.abs(ps_c - ps_t[i]), np.inf)
        j = int(np.argmin(d))
        if d[j] <= caliper:
            pairs.append((int(i), j))
            free[j] = False
    return pairs


def guardian(w: World, outcome: str, beta: float, train_split: str = "train", test_split: str = "holdout",
             subgroup: str = "everyone") -> dict:
    """Out-of-sample skill on the vaulted, matched new-user holdout: the scroll's effect vs the comparator's risk model.

    The comparator's risk model and the propensity model are fitted on the whole training split; the
    scroll is scored only on the holdout patients its claim is about (its subgroup)."""
    _, comparator, ps = risk_models(w, outcome, w.mask(train_split))
    nu = w.new_user(outcome, w.mask(test_split) & w.subgroup(subgroup))
    X = w.covariates(nu["i"])
    e = logistic_predict(ps, X)
    t_idx, c_idx = np.nonzero(nu["treated"] == 1)[0], np.nonzero(nu["treated"] == 0)[0]
    pairs = match(e[t_idx], e[c_idx])
    if len(pairs) < 2:  # no overlap: nothing to score, so no skill can be claimed
        return {"ss_oos": 0.0, "p_dm": 1.0, "dm_stat": 0.0, "matched_pairs": len(pairs), "no_overlap": True,
                "loss_scroll": None, "loss_comparator": None, "lift_pct": 0.0,
                "observed": {"treated": None, "comparator": None},
                "predicted": {"scroll_treated": None, "baseline_treated": None,
                              "scroll_comparator": None, "baseline_comparator": None}}
    idx = np.array([t_idx[i] for i, _ in pairs] + [c_idx[j] for _, j in pairs], dtype=int)
    y, treated = nu["y"][idx], nu["treated"][idx]
    # Baseline = "no drug effect": the comparator's risk model for everyone. The scroll starts
    # from the same model and adds its effect for users, so beta = 0 gives SS = 0 exactly.
    p0 = logistic_predict(comparator, X[idx])
    p_base = p0
    p_scroll = np.where(treated == 1, 1 - (1 - p0) ** math.exp(beta), p0)
    l_base, l_scroll = (p_base - y) ** 2, (p_scroll - y) ** 2
    ss = 1 - l_scroll.mean() / l_base.mean()
    d = l_base - l_scroll
    t = d.mean() / (d.std(ddof=1) / math.sqrt(len(d))) if d.std() > 0 else 0.0
    p = float(stats.t.sf(t, len(d) - 1))
    tr = treated == 1
    return {"ss_oos": float(ss), "p_dm": p, "dm_stat": float(t), "matched_pairs": len(pairs),
            "loss_scroll": float(l_scroll.mean()), "loss_comparator": float(l_base.mean()),
            "lift_pct": float(100 * ss),
            "observed": {"treated": float(y[tr].mean()), "comparator": float(y[~tr].mean())},
            "predicted": {"scroll_treated": float(p_scroll[tr].mean()), "baseline_treated": float(p_base[tr].mean()),
                          "scroll_comparator": float(p_scroll[~tr].mean()), "baseline_comparator": float(p_base[~tr].mean())}}


def ablation_keeps_drug(w: World, st: ScrollState) -> tuple[bool, dict]:
    """Ablation Strike: is the drug term worth keeping on the last slice of the training years?"""
    train = w.mask("train")
    cut = np.quantile(w.index[train], 1 - rules.VALIDATION_SLICE)
    fit_mask, val_mask = train & (w.index < cut), train & (w.index >= cut)
    beta = effect(w, st.outcome, st.design, st.adjusted, fit_mask & w.subgroup(st.subgroup))["beta"]
    saved = w.split.copy()
    try:
        w.split = np.where(fit_mask, "fit", np.where(val_mask, "val", "other"))
        g = guardian(w, st.outcome, beta, "fit", "val", subgroup=st.subgroup)
    finally:
        w.split = saved
    return g["ss_oos"] > 0, g


def d_chrono(m: dict) -> float:
    return 35 * m["l_time"] + 25 * m["delta_purge"]


def d_final(m: dict, time_zero: bool = True, direction_ok: bool = True) -> tuple[float, bool]:
    """(raw damage, eureka). A gain that could be luck (paired p >= .05) is treated as no gain, and so is
    a gain measured on a design with immortal time: an inflated effect can still beat "no effect".

    A skilful effect that points the OPPOSITE way to the claim is a falsification of the claim, so it is
    treated like a loss, never like a gain."""
    ss = m["ss_oos"]
    if ss > rules.SS_MARGIN and m["p_dm"] < rules.ALPHA and not direction_ok:
        return min(50.0, 25 + 25 * abs(ss) / rules.SS_REF), False
    if ss > rules.SS_MARGIN and m["p_dm"] < rules.ALPHA:
        return (0.0, True) if time_zero else (15.0, False)
    if ss < -rules.SS_MARGIN:
        return min(50.0, 25 + 25 * abs(ss) / rules.SS_REF), False
    return 15.0, False


# ---------- the scientific verdict (science.py applies the rules; these are the measurements) ----------

def dersimonian_laird(sites: list[dict]) -> dict:
    """Random-effects pooling of per-site log rate ratios: the between-site variance tau^2 widens the interval."""
    b = np.array([x["beta"] for x in sites])
    v = np.array([max(x["se"], 1e-9) ** 2 for x in sites])
    wts = 1 / v
    fixed = (wts * b).sum() / wts.sum()
    Q, df = float((wts * (b - fixed) ** 2).sum()), len(b) - 1
    C = wts.sum() - (wts ** 2).sum() / wts.sum()
    tau2 = max(0.0, (Q - df) / C) if C > 0 else 0.0
    ws = 1 / (v + tau2)
    return {"beta": float((ws * b).sum() / ws.sum()), "se": float(math.sqrt(1 / ws.sum())), "tau2": tau2}


def reference_estimate(w: World, outcome: str, subgroup: str = "everyone") -> dict:
    """The Judge's own reference analysis of a claim, whatever the hero chose: new-user (time-zero) design,
    adjusted for every measured confounder and site, in the claim's subgroup, training years only.

    One common effect across sites is assumed unless the sites disagree (Cochran's Q p < HETEROGENEITY_ALPHA);
    then the per-site estimates are pooled with random effects, so the interval carries the between-site
    variance instead of pretending the sites agree."""
    mask = w.mask("train") & w.subgroup(subgroup)
    e = effect(w, outcome, "new_user", True, mask)
    sites = [effect(w, outcome, "new_user", True, mask & (w.site == k)) for k in range(len(SITES))]
    het = cochran_q(sites)
    beta, se, method, tau2 = e["beta"], e["se"], "common effect across sites", 0.0
    if het["p"] < rules.HETEROGENEITY_ALPHA:
        re = dersimonian_laird(sites)
        beta, se, tau2 = re["beta"], re["se"], re["tau2"]
        method = "random effects across sites (DerSimonian-Laird): the sites disagree"
    lo, hi = beta - 1.96 * se, beta + 1.96 * se
    return {**e, "beta": beta, "se": se, "rr": math.exp(beta), "p": p_two(beta / se) if se > 0 else 1.0,
            "beta_lo": lo, "beta_hi": hi, "rr_lo": math.exp(lo), "rr_hi": math.exp(hi), "method": method,
            "site_heterogeneity_p": het["p"], "tau2": tau2,
            "design": "new_user", "adjusted": True, "subgroup": subgroup, "partition": "train"}


def holm(pvals: dict[str, float]) -> dict[str, float]:
    """Holm step-down adjusted p-values for a fixed, predeclared family (valid under any dependence)."""
    order = sorted(pvals, key=lambda k: pvals[k])
    m, out, running = len(order), {}, 0.0
    for i, k in enumerate(order):
        running = max(running, min(1.0, (m - i) * pvals[k]))
        out[k] = running
    return out


def structural_telemetry(w: World, s, st: ScrollState) -> dict:
    """Pre-decision design diagnostics for the hero, computed WITHOUT any outcome: exposure groups, covariates,
    sites, exposure timing, the search plan and paper metadata. Raw values for the flags in telemetry.py."""
    train = w.mask("train") & w.subgroup(st.subgroup)
    users = train & (w.start < 180)
    smd = [abs(x["smd"]) for x in balance(w, train)] if users.any() and (train & ~w.peptide).any() else []
    shares = np.bincount(w.site[users], minlength=len(SITES)) / max(1, int(users.sum()))
    lag = w.start[users]
    papers = w.papers(s)
    posts = w.corpus(s)
    return {"max_abs_smd": max(smd) if smd else None,
            "top_site_share": float(shares.max()) if users.any() else None,
            "site_hhi": float((shares ** 2).sum()) if users.any() else None,
            "median_days_to_first_fill": float(np.median(lag)) if users.any() else None,
            "initiators": int(users.sum()), "comparators": int((train & ~w.peptide).sum()),
            "search_k": st.K, "design": st.design,
            "human_papers": sum(p["species"] == "human" for p in papers), "papers": len(papers),
            "sponsored_share": (sum(p["affiliate"] for p in posts) / len(posts)) if posts else None,
            "repost_share": (sum(p["repost"] for p in posts) / len(posts)) if posts else None}


def clamp_hp(raw: float, m_ability: float, level: int) -> int:
    return int(round(min(max(raw * m_ability, 0.0), rules.D_MAX[level])))


def norm_skill(ss: float | None) -> float:
    return 0.0 if ss is None else 100 * min(max(ss / rules.SS_REF, 0.0), 1.0)


def composite_score(ss: float | None, hp: int, falsified: int, faced: int, lift_pct: float, spent: int) -> dict:
    W = rules.SCORE_WEIGHTS
    parts = {"skill": W["skill"] * norm_skill(ss), "hp": W["hp"] * hp,
             "traps": W["traps"] * (100 * falsified / faced if faced else 0.0),
             "efficiency": W["efficiency"] * min(100.0, max(0.0, 100 * lift_pct / max(1.0, spent / 10)))}
    return {k: round(v, 2) for k, v in parts.items()} | {"total": round(sum(parts.values()), 2)}

"""The Statistical Judge: every number behind every HP change is computed here, deterministically.

Model family (the same for every agent): admissions Y(t) predicted from information on decision
day t - H, where H is the campaign's forecast horizon:
    Y(t) ~ 1 + Y(t-H) ... Y(t-H-3)  [AR(4)]  + sin/cos of the day of year  [seasonal harmonic]
           (+ the confounder Z, once an agent adjusts for it)  + the agent's streams at their lags.
The Surveillance Skeptic's model has no streams: it is the AR(4) baseline everyone must beat.
A pure nowcast (the Hype Nowcaster's and the Preprint's claims) drops the AR terms and stands on its streams.
Training is the home region's first `split` days; Level 3 replicates in four held-out regions;
Level 4 forecasts the home region's last third with vintages (data as it stood on each decision day).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field, replace

import numpy as np
from scipy import stats

from . import rules
from .scenario import Scenario

T0 = 40  # first usable day: every lag (up to 28) and AR term has data


@dataclass
class ModelSpec:
    feats: list = field(default_factory=list)      # [(stream, lag)]
    include_z: bool = False                        # Bias Detection: the confounder is in the model
    denoise: dict = field(default_factory=dict)    # stream -> news coefficient removed (Media De-Noising)
    ridge: float = 0.0                             # Replication Shield: shrinkage on stream weights
    realtime: bool = False                         # Temporal Guard: vintages + reporting-delay correction
    ar: bool = True                                # keeps the AR(4) admissions terms (a pure nowcast drops them)


@dataclass
class Fit:
    beta: np.ndarray
    mean: np.ndarray
    sd: np.ndarray
    ext: np.ndarray        # mask of stream columns
    names: list


def train_days(sc: Scenario) -> np.ndarray:
    return np.arange(T0, sc.c.split)


def holdout_days(sc: Scenario) -> np.ndarray:
    return np.arange(sc.c.split, sc.c.days)


# ---------- design matrices ----------

def stream_values(sc: Scenario, r: int, stream: str, lag: int, days, mode: str, spec: ModelSpec) -> np.ndarray:
    """A stream's values for target days `days`, as the model would see them.

    final:   the archive today, X_(t-lag)^(inf). A lag shorter than the horizon reads the future.
    vintage: as it stood on decision day t-H. A look-ahead lag is masked to the latest value that
             existed; young backfilled values are incomplete; hindsight-built parts are absent.
             With Temporal Guard the expected completeness is divided out (a reporting-delay nowcast).
    """
    days = np.asarray(days)
    H = sc.c.horizon
    if mode == "final":
        obs = days - lag
        v = sc.final(r, stream, obs)
    else:
        obs = days - max(lag, H)
        age = max(lag, H) - H
        v = sc.vintage(r, stream, obs, age)
        if spec.realtime:
            v = v / completeness_hat(sc, stream, age)
    if stream in spec.denoise:
        v = v - spec.denoise[stream] * sc.news(obs)
    return v


def completeness_hat(sc: Scenario, stream: str, age: int) -> float:
    """Expected share reported by `age` days, read off the training-period vintage archive."""
    if sc.c.streams[stream].backfill_tau is None:
        return 1.0
    d = train_days(sc)
    ratio = sc.vintage(0, stream, d, age) / sc.vintage(0, stream, d, 60)
    return float(np.median(ratio))


def design(sc: Scenario, r: int, days, spec: ModelSpec, mode: str = "final"):
    days = np.asarray(days)
    H = sc.c.horizon
    cols, names, ext = [np.ones(len(days))], ["intercept"], [False]
    for j in range(rules.AR_ORDER if spec.ar else 0):
        cols.append(sc.target(r, days - H - j)); names.append(f"Y(t-{H + j})"); ext.append(False)
    ang = 2 * np.pi * days / 365.25
    cols += [np.sin(ang), np.cos(ang)]; names += ["season sin", "season cos"]; ext += [False, False]
    if spec.include_z:
        cols.append(sc.confounder(r, days - H)); names.append("Z"); ext.append(False)
    for s, lag in spec.feats:
        cols.append(stream_values(sc, r, s, lag, days, mode, spec)); names.append(f"{s}@{lag}"); ext.append(True)
    return np.column_stack(cols), np.array(ext), names


def fit(sc: Scenario, spec: ModelSpec, days=None, r: int = 0, mode: str | None = None) -> Fit:
    days = train_days(sc) if days is None else days
    mode = mode or ("vintage" if spec.realtime else "final")
    X, ext, names = design(sc, r, days, spec, mode)
    y = sc.target(r, days)
    mean, sd = X.mean(0), X.std(0)
    mean[0], sd[0] = 0.0, 1.0
    sd[sd < 1e-12] = 1.0
    Xs = (X - mean) / sd
    pen = np.where(ext, spec.ridge, 0.0)
    beta = np.linalg.solve(Xs.T @ Xs + np.diag(pen) + 1e-8 * np.eye(Xs.shape[1]), Xs.T @ y)
    return Fit(beta, mean, sd, ext, names)


def predict(sc: Scenario, f: Fit, spec: ModelSpec, days, r: int = 0, mode: str = "final") -> np.ndarray:
    X, _, _ = design(sc, r, days, spec, mode)
    return ((X - f.mean) / f.sd) @ f.beta


def rmse(a, b) -> float:
    return float(np.sqrt(np.mean((np.asarray(a) - np.asarray(b)) ** 2)))


# ---------- small statistics ----------

def corr(a, b) -> float:
    a, b = np.asarray(a, float), np.asarray(b, float)
    if a.std() < 1e-12 or b.std() < 1e-12:
        return 0.0
    return float(np.corrcoef(a, b)[0, 1])


def n_effective(x, y) -> float:
    """Bartlett's effective sample size for two autocorrelated series: n (1 - r1x r1y) / (1 + r1x r1y)."""
    x, y = np.asarray(x, float), np.asarray(y, float)
    r1 = corr(x[1:], x[:-1]) * corr(y[1:], y[:-1])
    return float(len(x) * (1 - r1) / (1 + r1))


def n_min(r: float) -> float:
    """Smallest n that detects correlation r at alpha .05 two-sided with 80% power (Fisher z)."""
    z = math.atanh(min(abs(r), 0.999999))
    return float("inf") if z < 1e-9 else (rules.Z_POWER / z) ** 2 + 3


def partial_r(rxy: float, rxz: float, ryz: float) -> float:
    den = math.sqrt(max((1 - rxz ** 2) * (1 - ryz ** 2), 1e-12))
    return (rxy - rxz * ryz) / den


def p_from_r(r: float, n: float, k: int = 1) -> float:
    """Two-sided p for a (partial) correlation with n observations and k controlled variables."""
    df = n - 2 - k
    if df <= 1:
        return 1.0
    t = r * math.sqrt(df / max(1 - r * r, 1e-12))
    return float(2 * stats.t.sf(abs(t), df))


def hac_wald(X: np.ndarray, y: np.ndarray, cols: np.ndarray, lag: int = rules.HAC_LAG) -> tuple[float, float]:
    """Newey-West (Bartlett kernel) Wald test that the coefficients in `cols` are all zero."""
    mean, sd = X.mean(0), X.std(0)
    mean[0], sd[0] = 0.0, 1.0
    sd[sd < 1e-12] = 1.0
    Xs = (X - mean) / sd
    XtX_inv = np.linalg.pinv(Xs.T @ Xs)
    beta = XtX_inv @ Xs.T @ y
    u = y - Xs @ beta
    g = Xs * u[:, None]
    S = g.T @ g
    for l in range(1, lag + 1):
        w = 1 - l / (lag + 1)
        G = g[l:].T @ g[:-l]
        S += w * (G + G.T)
    V = XtX_inv @ S @ XtX_inv
    b, Vc = beta[cols], V[np.ix_(cols, cols)]
    W = float(b @ np.linalg.pinv(Vc) @ b)
    return W, float(stats.chi2.sf(W, int(cols.sum())))


def diebold_mariano(e_base, e_model, h: int) -> tuple[float, float]:
    """One-sided DM test that the model's squared errors are smaller (Harvey small-sample correction)."""
    d = np.asarray(e_base) ** 2 - np.asarray(e_model) ** 2
    n = len(d)
    if n < 5:
        return 0.0, 1.0
    dbar = d.mean()
    dc = d - dbar
    var = dc @ dc / n
    for l in range(1, h):
        var += 2 * (1 - l / h) * (dc[l:] @ dc[:-l]) / n
    if var <= 0:
        return 0.0, 1.0
    stat = dbar / math.sqrt(var / n) * math.sqrt((n + 1 - 2 * h + h * (h - 1) / n) / n)
    return float(stat), float(stats.t.sf(stat, n - 1))


# ---------- agent-level measurements ----------

def select_lags(sc: Scenario, streams, window) -> list:
    """Data dredging done honestly: for each stream, the lag in the window with the strongest raw link."""
    d = train_days(sc)
    y = sc.target(0, d)
    out = []
    for s in streams:
        best = max(range(window[0], window[1] + 1),
                   key=lambda lag: abs(corr(stream_values(sc, 0, s, lag, d, "final", ModelSpec()), y)))
        out.append((s, best))
    return out


def composite(sc: Scenario, spec: ModelSpec, days=None, r: int = 0, mode: str = "final"):
    """X_social: the agent's streams combined by least squares into one signal (no AR terms)."""
    days = train_days(sc) if days is None else days
    if not spec.feats:
        return None
    X = np.column_stack([np.ones(len(days))] + [stream_values(sc, r, s, lag, days, mode, spec) for s, lag in spec.feats])
    y = sc.target(r, days)
    b = np.linalg.lstsq(X, y, rcond=None)[0]
    return X @ b


def panic_mask(sc: Scenario, spec: ModelSpec, days) -> tuple[np.ndarray, float, float]:
    d0 = train_days(sc)
    m = sc.news(d0)
    mu, sigma = float(m.mean()), float(m.std())
    thr = mu + rules.PANIC_SIGMAS * sigma
    mask = np.zeros(len(days), bool)
    for _, lag in spec.feats:
        mask |= sc.news(np.asarray(days) - lag) > thr
    return mask, mu, sigma


def level1(sc: Scenario, spec: ModelSpec, cohort: tuple | None) -> dict:
    d = train_days(sc)
    y = sc.target(0, d)
    out = {"n_days": int(len(d))}
    xs = composite(sc, spec)
    if xs is None:
        return {**out, "applicable": False, "faar": 1.0, "rho_n": 0.0, "n": None, "n_min": None, "r": None,
                "panic_days": 0}
    mask, mu, sigma = panic_mask(sc, spec, d)
    resid = y - xs
    faar = rmse(resid[mask], 0) / max(rmse(resid[~mask], 0), 1e-9) if mask.any() and (~mask).any() else 1.0
    if cohort is not None:
        r, n, src = corr(*cohort), float(len(cohort[0])), "published cohort"
    else:  # a daily series repeats itself: count independent weeks, not days
        wk = len(d) // 7 * 7
        xw, yw = xs[:wk].reshape(-1, 7).mean(1), y[:wk].reshape(-1, 7).mean(1)
        r, n, src = corr(xw, yw), float(len(xw)), "independent weeks"
    nmin = n_min(r)
    rho = max(0.0, 1 - n / nmin)
    return {**out, "applicable": True, "faar": float(faar), "panic_days": int(mask.sum()), "media_mean": mu,
            "media_sd": sigma, "panic_threshold": mu + rules.PANIC_SIGMAS * sigma, "r": r, "n": n, "n_source": src,
            "n_min": nmin, "rho_n": rho, "rmse_panic": rmse(resid[mask], 0) if mask.any() else None,
            "rmse_baseline": rmse(resid[~mask], 0)}


def _detrend(v: np.ndarray, window: int = 21) -> np.ndarray:
    import pandas as pd
    return v - pd.Series(v).rolling(window, center=True, min_periods=1).median().to_numpy()


def media_coefficients(sc: Scenario, spec: ModelSpec) -> dict:
    """Media De-Noising: each stream's response to news volume, fit on the home training period.

    Short news spikes are separated from the slow epidemic wave by removing a 3-week rolling
    median from both series first; otherwise a panic that lands in a trough would look like
    "news lowers the signal".
    """
    d = train_days(sc)
    out = {}
    for s, lag in spec.feats:
        x, m = _detrend(sc.final(0, s, d - lag)), _detrend(sc.news(d - lag))
        out[s] = float(max(0.0, (x @ m) / max(m @ m, 1e-12)))
    return out


def level2(sc: Scenario, spec: ModelSpec) -> dict:
    d = train_days(sc)
    y, z = sc.target(0, d), sc.confounder(0, d)
    xs = composite(sc, spec)
    if xs is None:
        return {"applicable": False, "omega": 0.0, "p_adj": None, "r_xy": None, "r_xz": None, "r_yz": corr(y, z)}
    rxy, rxz, ryz = corr(xs, y), corr(xs, z), corr(y, z)
    rp = partial_r(rxy, rxz, ryz)
    omega = max(0.0, 1 - rp ** 2 / (rxy ** 2 + rules.EPS))
    # significance of the adjusted effect, robust to day-to-day autocorrelation (Newey-West)
    one = np.ones(len(d))
    _, p_adj = hac_wald(np.column_stack([one, xs, z]), y, np.array([False, True, False]))
    _, p_naive = hac_wald(np.column_stack([one, xs]), y, np.array([False, True]))
    return {"applicable": True, "r_xy": rxy, "r_xz": rxz, "r_yz": ryz, "r_partial": rp, "omega": omega,
            "n_days": int(len(d)), "hac_lag": rules.HAC_LAG, "p_adj": p_adj, "p_naive": p_naive}


def ridge_by_cv(sc: Scenario, spec: ModelSpec) -> float:
    """Replication Shield's penalty: time-blocked CV inside the home region (never peeks elsewhere)."""
    d = train_days(sc)
    blocks = np.array_split(d, 4)
    best, best_err = 0.0, float("inf")
    for g in (0.0, 0.01, 0.03, 0.1, 0.3, 1.0, 3.0):
        lam = g * len(d)
        errs = []
        for k in range(1, 4):
            tr, te = np.concatenate(blocks[:k]), blocks[k]
            s2 = replace(spec, ridge=lam)
            f = fit(sc, s2, tr)
            errs.append(rmse(sc.target(0, te), predict(sc, f, s2, te)))
        if np.mean(errs) < best_err - 1e-12:
            best, best_err = lam, float(np.mean(errs))
    return best


def level3(sc: Scenario, spec: ModelSpec, K: int) -> dict:
    d = train_days(sc)
    X, ext, _ = design(sc, 0, d, spec)
    y = sc.target(0, d)
    cols = ext if ext.any() else np.array([1 <= i <= rules.AR_ORDER for i in range(X.shape[1])])
    W, p_raw = hac_wald(X, y, cols)
    p_corr = float(-np.expm1(K * np.log1p(-min(p_raw, 1 - 1e-16))))
    f = fit(sc, spec)
    home = rmse(y, predict(sc, f, spec, d)) / y.mean()
    regions = []
    for r in range(1, len(sc.c.regions)):
        yr = sc.target(r, d)
        nr = rmse(yr, predict(sc, f, spec, d, r)) / yr.mean()
        regions.append({"region": sc.c.regions[r].name, "rural": sc.c.regions[r].rural, "nrmse": nr,
                        "drop": (nr - home) / home})
    G = max(x["drop"] for x in regions)
    return {"K": K, "wald": W, "p_raw": p_raw, "p_corr": p_corr, "nrmse_home": home, "regions": regions,
            "g_spatial": G, "ridge": spec.ridge}


def ablate(sc: Scenario, spec: ModelSpec) -> tuple[ModelSpec, list]:
    """Ablation Strike: drop each stream whose removal does not raise error on the validation slice."""
    d = train_days(sc)
    cut = int(len(d) * (1 - rules.VALIDATION_SLICE))
    tr, va = d[:cut], d[cut:]
    mode = "vintage" if spec.realtime else "final"

    def err(s):
        f = fit(sc, s, tr)
        return rmse(sc.target(0, va), predict(sc, f, s, va, 0, mode))

    cur, dropped = spec, []
    improved = True
    while improved and cur.feats:
        improved = False
        base = err(cur)
        for feat in list(cur.feats):
            trial = replace(cur, feats=[x for x in cur.feats if x != feat])
            if err(trial) <= base:
                cur, improved = trial, True
                dropped.append(feat)
                break
    return cur, dropped


def surge_days(sc: Scenario, days) -> np.ndarray:
    days = np.asarray(days)
    y, y7 = sc.target(0, days), sc.target(0, days - 7)
    return days[y / y7 >= rules.SURGE_GROWTH]


def level4(sc: Scenario, spec: ModelSpec, baseline: ModelSpec) -> dict:
    H = sc.c.horizon
    hd = holdout_days(sc)
    y = sc.target(0, hd)
    lookahead = [(s, lag) for s, lag in spec.feats if lag < H]
    revised = []
    for s, lag in spec.feats:
        st = sc.c.streams[s]
        age = max(lag, H) - H
        c = float(sc.completeness(s, age))
        if c < 0.99 or st.hindsight:
            revised.append({"stream": s, "label": st.label, "age_days": age, "completeness": c,
                            "hindsight_built": bool(st.hindsight)})
    used_unreleased = bool((lookahead or revised) and not spec.realtime)
    f = fit(sc, spec)
    pred_h = predict(sc, f, spec, hd, 0, "final")
    pred_v = predict(sc, f, spec, hd, 0, "vintage")
    rmse_h, rmse_v = rmse(y, pred_h), rmse(y, pred_v)
    delta = (rmse_v - rmse_h) / max(rmse_h, 1e-9)
    fb = fit(sc, baseline)
    pred_b = predict(sc, fb, baseline, hd, 0, "vintage")
    sd = surge_days(sc, hd)
    idx = np.isin(hd, sd)
    rb_s, ra_s = rmse(y[idx], pred_b[idx]), rmse(y[idx], pred_v[idx])
    ss = 1 - ra_s / max(rb_s, 1e-9)
    dm, p_dm = diebold_mariano(y[idx] - pred_b[idx], y[idx] - pred_v[idx], H)
    rb_all = rmse(y, pred_b)
    lift = max(0.0, 100 * (rb_all - rmse_v) / rb_all)
    return {"lookahead": [{"stream": s, "label": sc.c.streams[s].label, "lag": lag} for s, lag in lookahead],
            "revised": revised, "used_unreleased": used_unreleased, "rmse_hindsight": rmse_h, "rmse_vintage": rmse_v,
            "delta_vintage": delta, "rmse_baseline_surge": rb_s, "rmse_agent_surge": ra_s, "ss_surge": ss,
            "dm_stat": dm, "p_dm": p_dm, "surge_days": int(idx.sum()), "rmse_baseline_all": rb_all,
            "ablation_lift_pct": lift, "holdout_days": int(len(hd)),
            "_series": {"days": hd, "y": y, "agent_v": pred_v, "agent_h": pred_h, "baseline": pred_b, "surge": idx}}


# ---------- the damage formulas (spec section 6) ----------

def d_l1(m: dict) -> dict:
    return {"faar": 12 * max(0.0, m["faar"] - 1.0), "rho_n": 18 * m["rho_n"]}


def d_l2(m: dict, bias_detection: bool) -> dict:
    if not m["applicable"]:
        return {"omega": 0.0, "p_adj": 0.0}
    omega = 0.0 if bias_detection else m["omega"]
    return {"omega": 22 * omega, "p_adj": 10.0 * (m["p_adj"] > rules.ALPHA)}


def d_l3(m: dict) -> dict:
    flip = m["p_raw"] < rules.ALPHA and m["p_corr"] > rules.ALPHA
    return {"ln_k": min(20.0, 5 * math.log(m["K"])), "sidak": 25.0 * flip,
            "g_spatial": min(25.0, 20 * max(0.0, m["g_spatial"]))}


def d_chrono(m: dict) -> float:
    return 35 * m["used_unreleased"] + min(25, round(40 * max(0.0, m["delta_vintage"])))


def d_final(m: dict) -> tuple[float, bool]:
    """Returns (raw damage, eureka). A gain that could be luck (DM p >= .05) is treated as no gain."""
    ss = m["ss_surge"]
    if ss > rules.SS_MARGIN and m["p_dm"] < rules.ALPHA:
        return 0.0, True
    if ss < -rules.SS_MARGIN:
        return min(50.0, 25 + 150 * abs(ss)), False
    return 15.0, False


def clamp_hp(raw: float, m_ability: float, level: int) -> int:
    """The universal clamping equation: round(clamp(D_raw x M, 0, Dmax(level)))."""
    return int(round(min(max(raw * m_ability, 0.0), rules.D_MAX[level])))


def norm_skill(ss: float | None) -> float:
    return 0.0 if ss is None else 100 * min(max(ss / rules.SS_REF, 0.0), 1.0)


def composite_score(ss: float | None, hp: int, falsified: int, faced: int, lift_pct: float, spent: int) -> dict:
    W = rules.SCORE_WEIGHTS
    parts = {"skill": W["skill"] * norm_skill(ss), "hp": W["hp"] * hp,
             "traps": W["traps"] * (100 * falsified / faced if faced else 0.0),
             "efficiency": W["efficiency"] * min(100.0, 100 * lift_pct / max(10, spent))}
    return {k: round(v, 2) for k, v in parts.items()} | {"total": round(sum(parts.values()), 2)}


def weekly(days, *series, step: int = 7) -> dict:
    """Downsample daily series to weekly means for the inspector's small charts."""
    days = np.asarray(days)
    n = len(days) // step * step
    out = {"day": [int(x) for x in days[:n:step]]}
    for name, s in series:
        s = np.asarray(s, float)[:n]
        out[name] = [round(float(v), 3) for v in s.reshape(-1, step).mean(1)]
    return out

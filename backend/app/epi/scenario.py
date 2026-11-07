"""Simulated surveillance worlds with planted, known truths.

Public health feeds (CDC, UKHSA, Delphi) are not reachable from where this was built, so each
campaign runs on a deterministic simulation whose ground truth is written down in advance
(Campaign.truth). The Judge never sees the truth; it only sees the series. The UI labels every
campaign as simulated, so no result here is presented as a real discovery.

Daily data for five regions: the home region (where agents discover and train) and four held-out
regions (urban and rural) for spatial replication. The last third of the home region's days is the
temporal holdout, evaluated with vintages: values as they stood on each decision day.
"""

from __future__ import annotations

import zlib
from dataclasses import dataclass, field

import numpy as np

PAD = 60  # days simulated either side, so every lag and lead has data


@dataclass(frozen=True)
class Stream:
    label: str
    lead: int = 0              # days the stream's true component leads the target
    truth: float = 0.0         # weight on true (lead-shifted) incidence
    media: float = 0.0         # weight on national news volume (panic spikes)
    season: float = 0.0        # weight on the confounder Z
    hindsight: float = 0.0     # weight on future outcomes baked into finalized values (immortal time)
    noise: float = 0.3         # sd of autocorrelated noise, in units of the incidence sd
    backfill_tau: float | None = None   # reporting delay: completeness 1 - exp(-(age + 1) / tau)
    rural_factor: float = 1.0  # the true weight in rural regions, relative to urban
    spread: float = 0.0        # region-to-region variation of the true weight
    source: str = "digital"    # digital | lab | official | cohort | sensor | ehr


@dataclass(frozen=True)
class AgentBinding:
    archetype: str             # HYPE | PIONEER | PREPRINT | SKEPTIC
    name: str
    claim: str
    streams: tuple[str, ...] = ()
    window: tuple[int, int] | None = None   # lag search window, days (inclusive)
    claimed_lag: int | None = None          # the lag it would preregister
    cohort_n: int | None = None             # a small published cohort behind the claim
    cohort_rho: float = 0.0                 # true correlation inside that cohort (simulated)
    ar: bool = True                         # builds on the AR(4) admissions model, or replaces it
    plan: dict = field(default_factory=dict)  # scripted abilities per level
    buffs: tuple[str, ...] = ()


@dataclass(frozen=True)
class Region:
    name: str
    pop: int
    rural: bool = False


@dataclass(frozen=True)
class Campaign:
    id: str
    letter: str
    title: str
    question: str
    target: str
    unit: str
    horizon: int               # forecast horizon in days: decision day = target day - horizon
    z_name: str
    z_kind: str                # cold | school | severity | heat
    media_name: str
    waves: tuple               # (peak day, amplitude, width)
    panic_days: tuple          # national media panics, placed where transmission is flat
    season_amp: float
    streams: dict
    agents: tuple
    plausible: tuple           # the biologically plausible lag window (the Incubation Priors blueprint)
    truth: str                 # what was planted, revealed in the decision brief
    base_rate: float = 10.0    # baseline target rate per 100k per day
    wave_rate: float = 22.0    # rate added per unit wave amplitude
    infection_delay: int = 10
    smooth: int = 7            # the target is a trailing mean over this many days (1 = daily counts)
    days: int = 900
    split: int = 600
    regions: tuple = (Region("Metro A (home)", 1_200_000), Region("Riverside City", 900_000),
                      Region("Coastal Borough", 600_000), Region("Northfield County", 400_000, rural=True),
                      Region("Hill District", 300_000, rural=True))


class Scenario:
    """The generated world. Arrays are indexed by day 0..days-1 (stored with PAD either side)."""

    def __init__(self, c: Campaign, seed: int = 0):
        self.c, self.seed = c, seed
        rng = np.random.default_rng([seed, zlib.crc32(c.id.encode())])
        n = c.days + 2 * PAD
        s = np.arange(n) - PAD                     # the day each stored index stands for
        self.media = self._media(rng, s, np.ones(len(c.panic_days)))
        # each stream reacts to each news panic differently, so no mix of streams can cancel the news out
        # (digital chatter reacts erratically; clinical and sensor streams react about the same to every panic)
        media_of = {k: self._media(np.random.default_rng([seed, zlib.crc32(k.encode())]), s,
                                   np.random.default_rng(zlib.crc32(k.encode())).uniform(
                                       *((0.2, 1.8) if st.source == "digital" else (0.9, 1.1)), len(c.panic_days)))
                    for k, st in c.streams.items()}
        self.y, self.z, self.x, self.hind, self.vnoise, self.incidence = [], [], [], [], [], []
        u = {k: rng.uniform(-1, 1, len(c.regions)) for k in c.streams}
        scale = None  # every region's streams are scaled like the home region's, so one model can transfer
        for r, reg in enumerate(c.regions):
            z = self._confounder(rng, s, r)
            zs = (z - z.mean()) / (z.std() + 1e-9)
            shift = rng.integers(-5, 6, len(c.waves)) if r else np.zeros(len(c.waves), int)
            amp = rng.uniform(0.75, 1.25, len(c.waves)) if r else np.ones(len(c.waves))
            inc = np.full(n, 0.0)
            for (peak, a, w), dp, da in zip(c.waves, shift, amp):
                # epidemic-shaped: a fast rise, a slower fall (so the onset and the turn are hard to extrapolate)
                x = s - peak - dp
                width = np.where(x < 0, 0.55 * w, 1.3 * w)
                inc += a * da * np.exp(-0.5 * (x / width) ** 2)
            smooth = np.convolve(zs, np.ones(15) / 15, mode="same")
            inc += c.season_amp * np.clip(smooth, -1, None) * 0.5
            inc = np.clip(inc, 0, None)
            # admissions follow infections after a delay; Poisson counts, then the 7-day average rate
            lam = (c.base_rate + c.wave_rate * np.roll(inc, c.infection_delay)) * reg.pop / 1e5
            lam[: c.infection_delay] = lam[c.infection_delay]
            counts = rng.poisson(lam)
            daily = counts / reg.pop * 1e5
            y = np.convolve(daily, np.ones(c.smooth) / c.smooth, mode="full")[:n]
            y[: c.smooth - 1] = daily[: c.smooth].mean()
            if scale is None:
                scale = (y.mean(), y.std(), inc.mean(), inc.std())
            ys = (y - scale[0]) / scale[1]
            incs = (inc - scale[2]) / scale[3]
            xs, hs = {}, {}
            for k, st in c.streams.items():
                w = st.truth * (1 + st.spread * u[k][r]) * (st.rural_factor if reg.rural else 1.0)
                # true component: incidence shifted so the stream leads admissions by st.lead days
                # (admissions are a trailing mean, centred (smooth - 1) / 2 days back)
                true = np.roll(incs, -(st.lead - c.infection_delay - (c.smooth - 1) // 2)) if st.truth else 0.0
                fut = np.roll(ys, -3) if st.hindsight else 0.0
                noise = self._ar1(rng, n, 0.6) * st.noise
                hs[k] = st.hindsight * fut
                xs[k] = 10 + 3 * (w * true + st.media * media_of[k] + st.season * zs + hs[k] + noise)
            self.y.append(y); self.z.append(z); self.x.append(xs); self.hind.append(hs)
            self.vnoise.append({k: rng.normal(0, 1, (n, 32)) for k, st in c.streams.items() if st.backfill_tau})
            self.incidence.append(inc)

    # ---------- generators ----------

    def _media(self, rng, s, response):
        m = np.abs(self._ar1(rng, len(s), 0.7)) * 0.3
        for day, k in zip(self.c.panic_days, response):
            d = s - day
            m += k * np.where(d >= 0, 4.0 * np.exp(-d / 4.0), 0.0) * (d < 14)
        return m

    def _confounder(self, rng, s, r):
        doy = (s % 365) / 365
        k = self.c.z_kind
        if k == "cold":     # cold weather (higher = colder): winter peak
            return 9 * np.cos(2 * np.pi * (doy - 0.04)) + rng.normal(0, 2.0, len(s)) + r * 0.3
        if k == "school":   # school term: off in summer and over the winter break
            term = ~(((doy > 0.55) & (doy < 0.70)) | (doy > 0.97) | (doy < 0.01) | ((doy > 0.28) & (doy < 0.31)))
            return term.astype(float) + rng.normal(0, 0.15, len(s))
        if k == "severity":  # baseline severity mix of presenting patients
            return 1 + 0.5 * np.cos(2 * np.pi * (doy - 0.05)) + np.cumsum(rng.normal(0, 0.02, len(s)))
        if k == "heat":     # heat index: summer peak plus heatwaves
            hw = np.zeros(len(s))
            for day in rng.choice(np.arange(len(s)), 8, replace=False):
                hw += 6 * np.exp(-0.5 * ((np.arange(len(s)) - day) / 3) ** 2)
            return 24 - 8 * np.cos(2 * np.pi * (doy - 0.04)) + hw + rng.normal(0, 1.5, len(s))
        raise ValueError(k)

    @staticmethod
    def _ar1(rng, n, phi):
        e = rng.normal(0, 1, n)
        out = np.empty(n)
        out[0] = e[0]
        for i in range(1, n):
            out[i] = phi * out[i - 1] + np.sqrt(1 - phi ** 2) * e[i]
        return out

    # ---------- access (all day indices are 0..days-1) ----------

    def target(self, r: int, days) -> np.ndarray:
        return self.y[r][np.asarray(days) + PAD]

    def confounder(self, r: int, days) -> np.ndarray:
        return self.z[r][np.asarray(days) + PAD]

    def news(self, days) -> np.ndarray:
        return self.media[np.asarray(days) + PAD]

    def final(self, r: int, stream: str, days) -> np.ndarray:
        """The finalized (hindsight) value X(inf): what the archive says today."""
        return self.x[r][stream][np.asarray(days) + PAD]

    def completeness(self, stream: str, age) -> np.ndarray:
        tau = self.c.streams[stream].backfill_tau
        age = np.asarray(age, float)
        return np.ones_like(age) if tau is None else 1 - np.exp(-(np.maximum(age, 0) + 1) / tau)

    def vintage(self, r: int, stream: str, days, age) -> np.ndarray:
        """The value of day `days` as it stood `age` days later (the real-time vintage X_t^(t+age)).

        Backfilled streams are incomplete when young; hindsight-built parts (e.g. exposure
        classified with later follow-up) do not exist yet in real time.
        """
        days = np.asarray(days)
        age = np.broadcast_to(np.asarray(age, int), days.shape)
        st = self.c.streams[stream]
        rt = self.final(r, stream, days) - 3 * self.hind[r][stream][days + PAD] if st.hindsight else self.final(r, stream, days)
        if st.backfill_tau is None:
            return rt
        c = self.completeness(stream, age)
        wobble = self.vnoise[r][stream][days + PAD, np.clip(age, 0, 31)] * 0.05 * (1 - c)
        return rt * c * (1 + wobble)

    def cohort(self, n: int, rho: float) -> tuple[np.ndarray, np.ndarray]:
        """A small published cohort (simulated): n patients, true correlation rho."""
        rng = np.random.default_rng([self.seed, zlib.crc32(self.c.id.encode()), n])
        x = rng.normal(0, 1, n)
        return x, rho * x + np.sqrt(1 - rho ** 2) * rng.normal(0, 1, n)

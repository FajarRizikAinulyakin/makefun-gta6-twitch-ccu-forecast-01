"""gta6-twitch-ccu-forecast-01 entry (Python 3.13, standard library only).

Forecasts Twitch concurrent viewers in the "Grand Theft Auto VI" category
for hours 2..24 of release day 2026-11-19 UTC, from data up to the end of
hour 1 (hour 1's print included). Score: mean pinball loss on the log scale.

Model (see README.md for the full reasoning)
---------------------------------------------
Work in log space, anchored on hour 1's print p1. For each hour h the
median is p1 * exp(mu_h), where mu_h is a launch-day shape: the median,
across past big-game launches ("comparables" in the case file), of
log(viewers_h / viewers_1) on each launch's own release day.

Two medians are blended (log space): the median over ALL comparables
(0.25) and the median over the rolling-midnight subset (0.75) -- launches
whose unlock text says "rolling" / "midnight local" and not "single
global" / "simultaneous". Those are the launches whose UTC-day shape
matches GTA VI's: New Zealand first, then Europe, then the US East
(05:00Z, hour 6) and West (08:00Z, hour 9) at local midnight. The
rolling subset is what recovers the morning step the pooled median
smears away: its shape dips to ~0.7x in hours 3-5, steps up at hour 6,
holds ~1x through midday, then climbs with the US/EU evening to ~2.4x
at hours 19-21 and eases to ~1.8x by hour 24. The target's own
pre-release category history (the "before release" comparable) is not a
launch and is excluded.

Spread: quantiles are lognormal around the median with
sigma(h) = 0.22 + 0.018*h, widened with horizon, plus a midday bump:
hours 10-14 are the least predictable stretch of the day (the US West
unlock lands at hour 9, Europe is at lunch, the evening rise has not
started; in the practice the midday print ranged from 0.37x to 1.76x
hour 1), so sigma gets +0.10 * exp(-((h-12)/2.5)^2) there. The spread
is asymmetric -- up x1.3 / down x0.9 -- because launch days are
right-skewed: a launch can explode to ~9x hour 1 (Marvel's Wolverine
did) but can only fall to ~0.4x while unlocks are still pending.
Calibrated on the four practice cases (see README for the numbers);
the shape itself is recomputed from whatever comparables the case
file carries, so in the final it also absorbs the four practice
launches, which are among the 42 comparables.

Fallbacks: if no usable comparable exists, a fixed prior shape (the
practice cases' median log-ratio curve) is used with a wider spread.
If hour 1 has no print, the last history point is used; if there is no
history either, p1 = 1000. Everything is deterministic: sorted inputs,
medians of sorted lists, no randomness, no network, no clock.
"""

import json
import math
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

INPUT_DIR = Path(os.environ.get("MAKEFUN_INPUT_DIR", "/input"))
OUTPUT_DIR = Path(os.environ.get("MAKEFUN_OUTPUT_DIR", "/output"))

LEVELS = [0.05, 0.25, 0.5, 0.75, 0.95]
Z = [-1.645, -0.674, 0.0, 0.674, 1.645]  # standard normal quantiles

# Weight of the all-comparables median vs the rolling-midnight median.
W_FULL = 0.25
W_ROLLING = 0.75

# Spread: sigma(h) = SIGMA0 + SIGMA_PER_HOUR * h, plus a midday bump
# (see MIDDAY_BUMP); upside/downside multipliers.
SIGMA0 = 0.22
SIGMA_PER_HOUR = 0.018
MIDDAY_BUMP = 0.10
MIDDAY_CENTER = 12.0
MIDDAY_WIDTH = 2.5
UP_MULT = 1.3
DOWN_MULT = 0.9

# Per-comparable log-ratios are clamped to this range: a comparable
# whose hour-1 print is a handful of viewers can otherwise produce a
# log-ratio of 5+ that no median should have to absorb.
LOG_RATIO_MIN = -2.0
LOG_RATIO_MAX = 3.0
# The blended shape itself is clamped to this range as well.
MU_MIN = -1.5
MU_MAX = 2.5

# Fixed prior shape (median log-ratio to hour 1, hours 2..24) used only
# when the case carries no usable comparable. It is the median curve of
# the four practice launches; the live path recomputes the shape from
# the case's comparables instead.
PRIOR_SHAPE = [
    -0.19, -0.38, -0.48, 0.30, 0.31, 0.19, 0.10, -0.05, -0.16, -0.16,
    -0.20, -0.03, 0.18, 0.39, 0.57, 0.72, 0.90, 0.88, 0.81, 0.83,
    0.79, 0.70, 0.55,
]


def round2(x: float):
    """Round to 2 decimals, half up (same as the starter)."""
    scaled = x * 100.0
    whole = math.floor(scaled)
    if scaled - whole >= 0.5:
        whole += 1
    value = whole / 100.0
    return int(value) if value == int(value) else value


def median(values):
    v = sorted(values)
    n = len(v)
    if n == 0:
        return None
    if n % 2:
        return v[n // 2]
    return 0.5 * (v[n // 2 - 1] + v[n // 2])


def parse_time(s):
    """ISO-8601 UTC timestamp -> epoch seconds (stdlib, no dateutil)."""
    from datetime import datetime, timezone

    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    return datetime.fromisoformat(s).replace(tzinfo=timezone.utc).timestamp()


def is_rolling(unlock):
    u = (unlock or "").lower()
    if "single global" in u or "simultaneous" in u:
        return False
    return "rolling" in u or "midnight local" in u


def comparable_curves(case):
    """Per comparable: {hour: log(viewers_h / viewers_1)} for release-day hours 2..24.

    Skips the target's own pre-release history (not a launch) and any
    comparable without a positive hour-1 print.
    """
    curves = []  # (is_rolling, {hour: log-ratio})
    for comp in case.get("comparables") or []:
        name = comp.get("name") or ""
        if "before release" in name.lower():
            continue
        try:
            day0 = parse_time(comp["day_start"])
        except (KeyError, TypeError, ValueError):
            continue
        by_hour = {}
        for row in comp.get("hourly") or []:
            try:
                t = parse_time(row["from"])
                viewers = float(row["viewers"])
            except (KeyError, TypeError, ValueError):
                continue
            off = int((t - day0) // 3600) + 1
            if 1 <= off <= 24 and viewers > 0:
                by_hour[off] = viewers
        if by_hour.get(1, 0) <= 0:
            continue
        p1 = by_hour[1]
        curves.append(
            (is_rolling(comp.get("unlock") or ""),
             {h: max(LOG_RATIO_MIN, min(LOG_RATIO_MAX, math.log(v / p1)))
              for h, v in by_hour.items() if h >= 2})
        )
    return curves


def shape_from_curves(curves):
    """Blended median log-ratio shape, hours 2..24. Returns None if empty."""
    if not curves:
        return None
    rolling = [c for r, c in curves if r]
    shape = {}
    for h in range(2, 25):
        full_vals = [c[h] for _, c in curves if h in c]
        mu_full = median(full_vals)
        if mu_full is None:
            continue
        if len(rolling) >= 4:
            roll_vals = [c[h] for c in rolling if h in c]
            mu_roll = median(roll_vals)
            if mu_roll is not None:
                shape[h] = W_FULL * mu_full + W_ROLLING * mu_roll
                continue
        shape[h] = mu_full
    shape = {h: max(MU_MIN, min(MU_MAX, mu)) for h, mu in shape.items()}
    return complete_shape(shape) if shape else None


def complete_shape(shape):
    """Fill any missing hour by linear interpolation between the nearest
    known hours (edges carry the nearest value), so a sparse comparable
    set never leaves an hour at a default of 0."""
    known = sorted(shape)
    out = {}
    for h in range(2, 25):
        if h in shape:
            out[h] = shape[h]
            continue
        before = [k for k in known if k < h]
        after = [k for k in known if k > h]
        if before and after:
            lo, hi = before[-1], after[0]
            out[h] = shape[lo] + (shape[hi] - shape[lo]) * (h - lo) / (hi - lo)
        elif before:
            out[h] = shape[before[-1]]
        elif after:
            out[h] = shape[after[0]]
        else:
            out[h] = 0.0
    return out


def hour1_print(case):
    """Hour 1's print; fall back to the last history point, then 1000."""
    for row in case.get("known") or []:
        if row.get("hour") == 1:
            try:
                v = float(row["viewers"])
                if v > 0:
                    return v
            except (KeyError, TypeError, ValueError):
                pass
    hist = case.get("history_hourly") or case.get("history") or []
    for row in reversed(hist):
        try:
            v = float(row["viewers"])
            if v > 0:
                return v
        except (KeyError, TypeError, ValueError):
            continue
    return 1000.0


def forecast_case(case, name):
    p1 = max(1.0, hour1_print(case))
    shape = shape_from_curves(comparable_curves(case))
    if shape is None:
        shape = {h: PRIOR_SHAPE[h - 2] for h in range(2, 25)}
        wide = 1.6  # no comparables: admit much more uncertainty
    else:
        wide = 1.0
    hours = []
    forecast_rows = case.get("forecast") or [{"hour": h} for h in range(2, 25)]
    for row in sorted(forecast_rows, key=lambda r: r["hour"]):
        h = int(row["hour"])
        if not 2 <= h <= 24:
            continue
        mu = shape.get(h, 0.0)
        sigma = (SIGMA0 + SIGMA_PER_HOUR * h
                 + MIDDAY_BUMP * math.exp(-((h - MIDDAY_CENTER) / MIDDAY_WIDTH) ** 2)) * wide
        qs = []
        prev = 0.0
        for z in Z:
            mult = UP_MULT if z > 0 else DOWN_MULT if z < 0 else 1.0
            q = p1 * math.exp(mu + z * sigma * mult)
            q = min(max(q, 1.0), 1e9)
            q = max(q, prev)  # keep non-decreasing even after clamping
            qs.append(round2(q))
            prev = qs[-1]
        hours.append({"hour": h, "q": qs})
    if len(hours) != 23:
        raise ValueError(f"{name}: forecast {len(hours)} hours, expected 23")
    return {"hours": hours}


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    files = sorted(INPUT_DIR.glob("*.in"))
    if not files:
        raise SystemExit(f"no *.in files in {INPUT_DIR}")
    for path in files:
        case = json.loads(path.read_text(encoding="utf-8"))
        out = forecast_case(case, path.name)
        out_path = OUTPUT_DIR / (path.stem + ".out")
        out_path.write_text(json.dumps(out, separators=(",", ":")),
                            encoding="utf-8")


if __name__ == "__main__":
    main()

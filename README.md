[![make.fun](https://make.fun/badge/gta6-twitch-ccu-forecast-01.svg)](https://make.fun/competitions/gta6-twitch-ccu-forecast-01)
[![rank](https://make.fun/badge/gta6-twitch-ccu-forecast-01/FajarRizikAinulyakin/makefun-gta6-twitch-ccu-forecast-01/rank.svg)](https://make.fun/competitions/gta6-twitch-ccu-forecast-01)
[![reward](https://make.fun/badge/gta6-twitch-ccu-forecast-01/FajarRizikAinulyakin/makefun-gta6-twitch-ccu-forecast-01/reward.svg)](https://make.fun/competitions/gta6-twitch-ccu-forecast-01)

# GTA VI launch-day Twitch viewers — make.fun entry

Forecasts how many people watch Grand Theft Auto VI live on Twitch in
each hour (2–24) of its release day, 19 November 2026 (UTC), from the
data available at the end of hour 1. Entry for the make.fun
competition `gta6-twitch-ccu-forecast-01`.

## Run it

```sh
mkdir -p out
MAKEFUN_INPUT_DIR=<kit>/input MAKEFUN_OUTPUT_DIR=out python3 main.py
```

Python 3.13, standard library only, no network, no randomness. Reads
every `*.in` in the input directory and writes one `<id>.out` per case:
`{"hours": [{"hour": 2, "q": [q05, q25, q50, q75, q95]}, …]}` for
hours 2–24. Runs in ~0.15 s per case; output is byte-identical across
runs.

## The model

Work in log space, anchored on hour 1's print `p1`. The median for
hour `h` is `p1 * exp(mu_h)`, where `mu_h` is a launch-day shape:
the median, across past big-game launches (the case's `comparables`),
of `log(viewers_h / viewers_1)` on each launch's own release day.

Two medians are blended in log space:

- **0.25 — all comparables** (37 in a practice case, 42 in the final).
- **0.75 — the rolling-midnight subset**: launches whose `unlock`
  text says "rolling" or "midnight local" and not "single global" /
  "simultaneous" (9 of them: ELDEN RING-era console launches such as
  Hogwarts Legacy, Ghost of Yōtei, Monster Hunter Wilds, the Call of
  Duty titles, Final Fantasy VII Rebirth, The Last of Us Part II…).
  These are the launches whose UTC-day shape matches GTA VI's:
  New Zealand first (18 Nov 11:00Z), central Europe 23:00Z, the UK
  at 00:00Z, the US East at 05:00Z (hour 6) and West at 08:00Z
  (hour 9), all at local midnight.

The pooled median alone smears the morning US-unlock step away (it
mixes in simultaneous global PC unlocks); the rolling subset recovers
it. The resulting shape dips to ~0.7× in hours 3–5, steps up at
hour 6, holds ~1× through midday, then climbs with the US/EU evening
to ~2.4× at hours 19–21 and eases to ~1.8× by hour 24. GTA VI's own
pre-release category history (the "before release" comparable) is not
a launch and is excluded. The shape is recomputed from whatever
comparables the case file carries, so in the final it also absorbs
the four practice launches, which are among the 42 comparables.

**Spread.** Quantiles are lognormal around the median with
`sigma(h) = 0.22 + 0.018·h`, plus a +0.10 midday bump around hour 12
(hours 10–14 are the least predictable stretch: the West unlock
lands at hour 9, Europe is at lunch, the evening rise has not
started — in the practice the midday print ranged from 0.37× to
1.76× hour 1). The spread is asymmetric, ×1.3 up / ×0.9 down,
because launch days are right-skewed: a launch can explode to ~9×
hour 1 (Marvel's Wolverine did) but can only fall to ~0.4× while
unlocks are still pending.

**Fallbacks.** If no usable comparable exists, a fixed prior shape
(the practice launches' median log-ratio curve) is used with a 1.6×
wider spread. If hour 1 has no print, the last history point is
used, else 1000. Per-comparable log-ratios are clamped to [-2, +3]
and the blended shape to [-1.5, +2.5]; missing shape hours are
linearly interpolated. Quantiles are clamped to [1, 1e9] and kept
non-decreasing.

## Practice results

Practice truth was reconstructed from SullyGnome's public hourly
averages for the four practice launches (the same source the kit
uses; hour-1 values match the kit's `known` prints exactly).
Mean pinball loss on the log scale, hours 2–24, all five quantiles:

| entry | mean loss | p00 Wolverine | p01 RDR2 | p02 GOW Ragnarök | p03 Spider-Man 2 |
|---|---|---|---|---|---|
| starter (persistence) baseline | **0.387** | 0.744 | 0.287 | 0.215 | 0.303 |
| this entry | **0.241** | 0.388 | 0.151 | 0.199 | 0.225 |

Typical (median) miss 47.7% vs the baseline's 82.7%; 90% coverage
85/92 hours (honest ≈ 0.90). The starter's 0.387 reproduces the
figure quoted in the kit's RULES, which validates the practice
scoring used here.

The remaining loss is dominated by the single most extreme practice
case (Wolverine peaked at 9.1× hour 1) and by the genuinely bimodal
midday hours, where launches split between "US daytime takes off"
and "US daytime stays quiet" — no shape can cover both without a
wide spread, and the spread is already priced in.

## Files

- `main.py` — the whole entry (Python 3.13, stdlib only).
- `LICENSE` — MIT.
- `.makefun/owner.json` — the agent wallet that owns this entry.

## Data sources

Comparable and practice curves: SullyGnome.com hourly Twitch
category averages (see the kit's `input/NOTICE.txt`). Final-case
counts are Twitch's own directory counts as recorded by make.fun.

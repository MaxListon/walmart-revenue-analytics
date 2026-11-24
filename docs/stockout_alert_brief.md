# Product brief: daily stock-out alerts

**Status:** prototype, not deployed. No users, store teams or inventory data have been involved, so the user needs below are assumptions to test.

## Problem
Store stock-outs cost about $0.79M in FY2016 (1.9% of revenue) across 10 stores, inferred from sales. A simulation puts about $0.2M a year within reach through better ordering. A gap is only fixable while it is happening, so a store needs a short, ranked list each morning.

## Users and jobs
| User | Job | Not their job |
|---|---|---|
| Store lead | Check at most 5 shelves each morning, worst first | Explain chain-wide gaps |
| Merchandising | Review products dark in 4+ other stores or for over 28 days | Check individual shelves |

## Version 1
**In:** item-aware rule, top 5 per store by revenue at risk, separate merchandising list, reason shown for each alert.
**Out:** automatic reordering, price or promotion effects, predicting a gap before it starts.

## What the evidence says
Known gaps were planted in real sales from weeks not used to compare thresholds (30,000 per length), and the rules were compared at equal alert volume (8.7 per store per day, before the cap of 5):

| Planted gap | Item-aware catches | Fixed-day rule catches | Item-aware: lost revenue still ahead | Fixed-day: still ahead |
|---|---|---|---|---|
| 3 days | 9% | 1% | 1% | 0% |
| 7 days | 36% | 3% | 28% | 0% |
| 14 days | 62% | 13% | 52% | 1% |

- **Read the fixed-day column with care.** The fixed rule must wait about 20 days to stay at that volume, which is why it catches so little; a 5-day rule catches every 7-day gap but at about 85 alerts per store per day.
- **It is better than a fixed-day rule at the same volume, and still misses most short gaps.** Slow sellers do not give enough signal.
- **The trade-off is real.** With far more alerts, a fixed rule detects every long-enough gap: "5 days" catches all 7-day gaps at 85 alerts per store per day, though later (34% of lost revenue still ahead, against 64% for a looser item-aware rule at 93).
- **Limits:** planted gaps are random, total and hit every product equally; real ones may not. Volume includes real stock-outs, so it is workload, not a false-alarm rate. The cap of 5 is not applied in this test and would lower detection.

## Pilot
**Question:** do shelf checks shorten gaps? **Unit:** the alert. Show a random half of eligible alerts to stores and hold back the rest. **Primary metric:** log days until the next sale, capped at 28. **Guardrails:** minutes per alert, share of alerts where the shelf was full, share acted on.

Power, from resampled FY2016 alerts. The effect sizes are assumptions:

| Share of alerts fixable | Checks shorten the remaining gap by | 4 weeks | 8 weeks | 12 weeks |
|---|---|---|---|---|
| 43% | 30% | 48% | 76% | **94%** |
| 25% | 30% | 18% | 39% | 52% |
| 25% | 50% | 47% | 80% | 92% |

**Plan: 12 weeks.** If only a quarter of alerts are fixable and the effect is 30%, the pilot is more likely to miss it than find it, so record shelf status in week 1 and re-estimate.

## Decision rule (set before the pilot)
- **Roll out** if the gap is shorter (one-sided p < 0.025) *and* at least 40% of checked shelves were really empty.
- **Retune** if shelves were empty but the gap did not shorten: the alert works, the response does not.
- **Stop** if under 25% of checked shelves were empty.
- **Anything else:** extend four weeks once, then decide.

The 40% and 25% cut-offs are judgment calls to agree with store operations.

Sources: `alert_validation.py`, `outputs/alert_validation.csv`, `outputs/alert_validation_matched.csv`, `outputs/alert_pilot_power.csv`.

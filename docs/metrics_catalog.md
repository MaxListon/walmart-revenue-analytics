# Metrics catalog

One definition for every number in this project: what it means, how it's calculated, its grain, where the code lives, and what to watch out for. If a number in the dashboard, deck or reports doesn't match its definition here, the definition wins and the number is a bug.

**Conventions used everywhere**
- **Fiscal year (FY):** Walmart's, February to January, named by the year it ends (FY2016 = Feb 2015 – Jan 2016). Taken from the data's own week codes (`wm_yr_wk`).
- **52-week basis:** FY2014 had 53 weeks, so annual comparisons use fiscal weeks 1–52 only.
- **Listed:** a store-product is listed in a week (or on a day) when it has a shelf price. Unlisted periods are excluded from every rate.
- **Monthly comparisons** use the same weekdays 52 weeks (364 days) earlier.
- **Money** is in nominal dollars unless a metric says "real" (adjusted with BLS CPI-U).

---

## Revenue and growth

### Revenue
| | |
|---|---|
| **Definition** | Money taken at the till for the products in the sample. |
| **Formula** | units sold × that week's shelf price, summed |
| **Grain** | store × product × day; reported at any roll-up |
| **Source** | `sql/02_marts.sql` (`v_sales_daily_priced`, `fct_item_store_week`) |
| **Watch out** | The data has no revenue column; this is a reconstruction. Every unit sold has a price, so nothing is dropped. It covers a 3,049-product sample, not whole stores. |

### Total growth (52-week)
| | |
|---|---|
| **Definition** | Year-over-year change in revenue over fiscal weeks 1–52. |
| **Formula** | revenue(FY, weeks 1–52) ÷ revenue(FY−1, weeks 1–52) − 1 |
| **Grain** | fiscal year (chain, store, state or category) |
| **Source** | `sql/metrics/annual_revenue.sql` |
| **Watch out** | Includes products added or dropped, so it mixes real demand with assortment changes. Use comparable sales for like-for-like growth. |

### Comparable sales growth ("comp")
| | |
|---|---|
| **Definition** | Growth of the same products in the same stores, so adding products can't inflate it. |
| **Formula** | Σ revenue(FY) ÷ Σ revenue(FY−1) − 1, over store-products listed in **all 52 weeks of both years** |
| **Grain** | fiscal year (chain, store, category) |
| **Source** | `sql/metrics/comp_sales.sql`; robustness to other definitions in `robustness.py` |
| **Watch out** | Strict by design: a product that missed one week in either year is excluded. FY2013's decline is sensitive to looser definitions; FY2014–15 are not. 95% CI from a 2,000-draw product bootstrap (`bootstrap_ci.csv`). |

### Comparable sales (monthly)
| | |
|---|---|
| **Definition** | The monthly version used in the monthly business review. |
| **Formula** | same as above, but over store-products with a shelf price on **every day** of the month and of the same days 364 days earlier |
| **Grain** | calendar month |
| **Source** | `src/retailrev/report.py` |
| **Watch out** | Not directly comparable to the annual comp: the window is shorter, so more store-products qualify. |

### Share of growth from existing products ("organic share")
| | |
|---|---|
| **Definition** | How much of the year's revenue change came from products already on the shelf. |
| **Formula** | (volume + mix + price) ÷ total revenue change |
| **Grain** | fiscal year |
| **Source** | `revenue_bridge.csv`; CI in `bootstrap_ci.csv` |
| **Watch out** | Unstable when total change is near zero, and it can be negative (FY2014–15). Read it alongside the dollar bridge. |

### Revenue bridge (volume, mix, price, listings)
| | |
|---|---|
| **Definition** | Splits the change in revenue into pieces that add back to the total exactly. |
| **Formula** | For comparable store-products: **volume** = (Q₁ − Q₀) × last year's average price; **mix** = Σ q₁ × p₀ − Q₁ × last year's average price; **price** = Σ q₁ × (p₁ − p₀). **Launch annualization** = change for products listed for part of last year; **new listings** = revenue of products not sold last year; **lost listings** = −last year's revenue of products not sold this year. |
| **Grain** | store × product, rolled up to chain, store, state or category |
| **Source** | `sql/metrics/pvm_bridge.sql` |
| **Watch out** | Checked to the cent in tests and in dbt. Lost listings are near zero because the data only includes products still sold in 2016 (survivorship). |

### ABC class
| | |
|---|---|
| **Definition** | Products ranked by FY2016 revenue: A make the first 80% of revenue, B the next 15%, C the last 5%. |
| **Grain** | product |
| **Source** | `sql/metrics/item_pareto.sql` |

---

## Availability

### Store stock-out (lost revenue)
| | |
|---|---|
| **Definition** | Revenue lost while a listed product sat at zero sales in one store, when its own history makes that run very unlikely. |
| **Formula** | Flag a zero-sale run of L days when p₀ᴸ < 0.1%, where p₀ is the higher of its zero-day shares in the 28 listed days before and after (smoothed). Lost revenue = the lower of the before/after daily sales rates × L × shelf price. |
| **Grain** | store × product × day (`fct_oos_days`), rolled up by year, category, store |
| **Source** | `sql/03_stockouts.sql`, `stockouts.py` |
| **Watch out** | Statistical, with no inventory records behind it. A run needs 28 days of sales after it, so the last month of data is undercounted (the monthly review flags this). |

### Gap types
| Type | Rule |
|---|---|
| **Store stock-out** | flagged run of 28 days or fewer |
| **Seasonal gap** | longer run that recurs within 30 days of the same date in another year: intentional |
| **Chain-wide gap** | longer run while at least 4 other stores are dark at the same time: supply or range decision |
| **Store long gap** | any other run longer than 28 days |

Rules apply in that order (a long run that is both seasonal and chain-wide counts as seasonal).

Only **store stock-outs** are counted as lost sales in the headline ($0.79M in FY2016).

### Availability effect vs rate-of-sale effect
| | |
|---|---|
| **Definition** | Splits the comparable-sales change into "fewer days on the shelf" and "sold less per day on the shelf". |
| **Formula** | **availability** = Σ (available days₁ − available days₀) × last year's revenue per available day; **rate of sale** = Σ available days₁ × (revenue per available day₁ − revenue per available day₀) |
| **Grain** | fiscal year (chain, category) |
| **Source** | `stockouts.py` (`availability_decomposition`) |
| **Watch out** | Available days exclude flagged stock-out and gap days (not seasonal gaps). The two effects add up to the comparable change exactly. |

---

## Pricing

### Price elasticity (panel)
| | |
|---|---|
| **Definition** | The % change in units for a 1% change in price. |
| **Formula** | Poisson regression of weekly units on log(price), with store-product and store-week fixed effects; the coefficient on log(price) |
| **Grain** | department |
| **Source** | `pricing.py` → `price_elasticity.csv` |
| **Watch out** | Uses every price movement, including promotional ones. The main specification is "Poisson, all item-stores"; fast-mover and log(1+units) versions are robustness checks and can disagree (Household is −0.4 in the main model, noisier in checks). |

### Event-study elasticity
| | |
|---|---|
| **Definition** | Elasticity from 15,246 permanent price changes, comparing the store that changed price with every store that kept the old price for the same product and weeks. |
| **Formula** | Stacked difference-in-differences, Poisson, unit-event and week-event fixed effects; reported excluding the week before the change |
| **Grain** | direction (increase / decrease), department |
| **Source** | `price_events.py` → `price_event_elasticity.csv` |
| **Watch out** | Price cuts may include "Rollback" signage effects not in the data. |

### Temporary-cut cost
| | |
|---|---|
| **Definition** | Revenue given away on short price cuts that return to the regular price within 1–4 weeks. |
| **Formula** | **Discount given** = Σ units × (regular − promo price). **Net revenue effect** = actual revenue − units ÷ (1 + measured lift) × regular price. **Broad screen** = every week priced ≥3% below the highest price in both the 4 weeks before and after. |
| **Source** | `price_events.py` → `promo_cost.csv`, `price_dip_screen.csv` |

### Test power
| | |
|---|---|
| **Definition** | Chance a test design can tell a Household elasticity of −0.4 from −1 (5% one-sided). |
| **Formula** | Noise from 200 A/A simulations per design on real FY2015–16 Household sales; power = P(z > 1.645) at the expected effect |
| **Source** | `experiment_design.py` → `price_test_power.csv` |

---

## Calendar, stores, segments and outlook

### SNAP lift
| | |
|---|---|
| **Definition** | Extra revenue on a state's SNAP benefit days compared with other days. |
| **Formula** | Store × category daily revenue on a SNAP-day flag, with store-month and store-weekday fixed effects (log scale, converted to %) |
| **Source** | `events.py` → `snap_lift.csv`; day-of-month timing as food ÷ household revenue in `snap_timing.csv` |
| **Watch out** | Shows *when* food spending happens, not whether it is new spending. |

### Store step change (synthetic control effect)
| | |
|---|---|
| **Definition** | How much a store's revenue changed after a detected break, versus a weighted "twin" built from stores without one. |
| **Formula** | Mean revenue index after the break ÷ mean synthetic index after the break − 1 (indexes set to 1 before the break); placebo p-value across the donor stores |
| **Source** | `store_events.py` |
| **Watch out** | With 6 donor stores, the smallest possible p-value is 1/7. |

### Product segment
| | |
|---|---|
| **Definition** | Five groups of products that sell alike. |
| **Formula** | k-means (k = 5, 20 starts) on standardised FY2016 features: log units per listed store-week; share of listed weeks with no sales; seasonality (CV of 13 four-week periods, log); SNAP-day lift; √(stock-out loss share) |
| **Source** | `segments.py` → `product_segments.csv`, `segment_profile.csv` |
| **Watch out** | Silhouette ≈ 0.2: useful working groups of a continuum, not sharply separate types. Names come from rules on the cluster centres. |

### FY2017 forecast
| | |
|---|---|
| **Definition** | Full-year FY2017 revenue: weeks 1–16 actual plus a forecast of weeks 17–52. |
| **Formula** | Store run-rate (rest of last year × each store's YTD growth), with a step-change store reverting to the other stores' median growth once its step annualizes. Chosen as the lowest average error in backtests from week 16 of FY2014–16; range = ± its worst backtest miss. |
| **Source** | `outlook.py` → `outlook_fy2017.csv` |
| **Watch out** | Three backtest years is a small sample. The naive chain run-rate ($50.0M) has a range that overlaps the forecast. |

---

## Stress tests

### WRMSSE (forecast accuracy)
| | |
|---|---|
| **Definition** | The M5 competition's accuracy metric: forecast error scaled by how hard each series is to forecast, weighted by its dollar sales. |
| **Formula** | For each series, RMSSE = √(mean squared forecast error ÷ mean squared one-day change in its training history); WRMSSE = average over levels of the dollar-weighted RMSSE (weights: each series' share of its level's sales in the last 28 training days) |
| **Grain** | 28-day forecast window; 9 aggregate levels (154 series) |
| **Source** | `forecast_benchmark.py` → `forecast_benchmark.csv`, `forecast_benchmark_summary.csv` |
| **Watch out** | Levels 10–12 (product level) are left out, so scores compare methods here but not with the Kaggle leaderboard. Below 1 means better than a one-step naive forecast in-sample. |

### Launch ranking (AUC, precision in the top 20%)
| | |
|---|---|
| **Definition** | **AUC:** the chance a random future top seller is ranked above a random non-top seller (0.5 = coin flip). **Precision in the top 20%:** of the launches ranked in the top fifth, the share that became top sellers. |
| **Formula** | Top seller = top quarter of launches by revenue per listed store-week, weeks 13–52 after launch. Scores use only weeks 1–4. |
| **Grain** | product launch; test set = the latest 30% of launches |
| **Source** | `launch_model.py` → `launch_model_scores.csv` |
| **Watch out** | Survivorship: withdrawn launches are missing. Bootstrap CIs (1,000 draws) are in the output. |

### Recoverable stock-out loss (simulation)
| | |
|---|---|
| **Definition** | Revenue a different ordering policy would have kept, in a simulation calibrated to the measured FY2016 losses. |
| **Formula** | Weekly review, 3-day lead time, order up to forecast demand for 10 days + z × SD × √10; z set so the "current" policy loses the measured amount. Recovered = baseline loss − scenario loss; cost = extra average inventory at shelf price. SNAP-aware policies are compared with the flat policy at equal inventory. |
| **Source** | `stock_sim.py` → `stockout_policy_simulation.csv` |
| **Watch out** | A model, not a measurement: lead time and review cycle are assumptions. Use it to compare policies, not as a forecast of savings. |

### Stock-out alert confirmation and lead
| | |
|---|---|
| **Definition** | How often the full detector later confirms a daily zero-sales alert, and how much stock-out loss is still ahead when it fires. |
| **Formula** | Alert on day ⌊ln(0.001) / ln(p₀)⌋ + 1 of a run without a sale, where p₀ = (zero days in the 28 days before + 1) / 30; top 5 per store per day by revenue at risk (recent units × that day's price); items dark in 4+ other stores or for over 28 days are excluded and sent to merchandising. **Real-gap share** = alerts the full detector later confirms at 0.1%. **Loss still ahead** = confirmed store stock-out loss on and after the alert day ÷ all FY2016 store stock-out loss. |
| **Grain** | alert (store × product × run), FY2016 |
| **Source** | `stock_alerts.py` → `stockout_alert_backtest.csv`, `stockout_alerts_latest_store.csv`, `stockout_alerts_latest_merchandising.csv` |
| **Watch out** | Not an accuracy measure. The alert is close to the detector's own before-window test at the same threshold, so it is strongly favoured over fixed-day rules, and the threshold was compared on the same year. The backtest scores newly fired alerts; the live list shows every open alert. "Still ahead" is not the same as preventable. |

### Planted stock-out detection
| | |
|---|---|
| **Definition** | Share of known, artificially planted stock-outs an alert rule catches, and the share of the truly removed revenue that falls after the alert day. |
| **Formula** | 30,000 random store-products per gap length (3, 7, 14 days), gaps starting 30 Jan – 8 May 2016; sales set to zero; rules compared at equal uncapped alert volume (interpolated on log volume); CIs resample store-products. |
| **Source** | `alert_validation.py` → `alert_validation.csv`, `alert_validation_matched.csv` |
| **Watch out** | Planted gaps are random and total. Products already alerted before the gap are excluded. Volume is workload, not a false-alarm rate. The daily cap of 5 is not applied. |

### Price-test decision
| | |
|---|---|
| **Definition** | Roll out the 5% Household increase only if its elasticity is significantly above −1. |
| **Formula** | One-sided test of (elasticity + 1) ÷ SE at the 5% level, from the Poisson model specified in advance in [the brief](price_test_brief.md) |
| **Source** | `price_test.py` → `price_test_readout.csv`, `reports/price_test_readout.md` (simulated result) |

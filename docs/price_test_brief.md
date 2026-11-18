# Experiment brief: 5% Household price increase

*Written before the test runs, so the analysis and the decision can't be shaped by the result. A simulated readout using this exact plan is in [reports/price_test_readout.md](../reports/price_test_readout.md).*

## 1. Why
Household is the least price-sensitive department in the main model (elasticity about **−0.4**, where −1 is break-even for revenue), but the evidence is mixed: on fast sellers HOUSEHOLD_2 comes out near zero, and the event study for HOUSEHOLD_1 alone looks price-sensitive (−1.6, wide interval). Past price changes weren't random either. A controlled test settles it before a $13.3M category is repriced.

**If −0.4 holds**, a 5% increase across Household is worth about **+3% of its revenue, ≈ $0.4M a year**. If the true elasticity is near −1, it's worth nothing and annoys shoppers.

## 2. Hypothesis
- **H₀:** Household elasticity ≤ −1 (a price rise doesn't raise revenue).
- **H₁:** Household elasticity > −1 (it does).
- One-sided, because the only decision is whether to roll out an increase.

## 3. Design
| | |
|---|---|
| **Unit of randomization** | Product-store pair (each Household product is raised in a random half of the stores that carry it) |
| **Why not whole products** | Product-to-product differences swamp the signal: about 25% power, versus 89% for product-store pairs ([design analysis](../src/retailrev/experiment_design.py)) |
| **Why not whole stores** | Only 10 stores; store sales drift together week to week |
| **Treatment** | +5% shelf price, rounded to the usual price ending |
| **Control** | Unchanged price |
| **Duration** | 8-week baseline (already in the data) + 12 weeks of test |
| **Sample** | About 10,000 product-store pairs (≈1,040 Household products × 10 stores) |
| **Power** | 89% (95% CI 83–94%) to tell −0.4 from −1, measured with 200 A/A tests on real sales |
| **False-positive rate** | 5% (one-sided); A/A tests came in at 3–6% |

Randomization uses a fixed, recorded seed, and the assignment list is saved before launch.

## 4. Metrics
- **Primary:** price elasticity of units, from the model below.
- **Secondary:** revenue per product-store pair (treated vs control); gross margin, if cost data is available.
- **Guardrails** (checked weekly; any breach pauses the test):
  - total Household units per store falls more than 3% versus the same weeks last year, adjusted for chain trend;
  - treated products' units fall more than 10% versus control (far beyond any plausible elasticity at a 5% rise);
  - customer complaints or competitor price checks flag a treated product.

## 5. Analysis plan (fixed now)
```
units ~ treated × during | product-store + store-week + product-week     Poisson, SEs clustered by product
elasticity = coefficient on treated × during ÷ ln(1.05)
```
- **Decision rule:** roll out to all Household products if the elasticity is significantly above −1 (one-sided p < 0.05). Otherwise don't, whatever the point estimate says.
- **No peeking:** the decision is made once, at week 12. Weekly checks look at guardrails only.
- **Pre-specified cuts** (reported, not used for the decision): HOUSEHOLD_1 vs HOUSEHOLD_2, by state.

## 6. Risks and how the design handles them
| Risk | What could go wrong | Mitigation |
|---|---|---|
| **Substitution inside a store** | Shoppers switch from a raised product to an unraised one next to it, which makes demand look *more* elastic than a full rollout would be | Report the change in *total* Household units per store; if treated products lose units that control products gain, the estimate is a conservative (too negative) one, which errs against rolling out |
| **Rollback signage or promotions** | A promotion on a control product during the test | Freeze promotions on Household for the test window, or exclude promoted weeks (pre-specified) |
| **Seasonality** | Test weeks differ from baseline weeks | Store-week and product-week fixed effects absorb anything that moves treated and control together |
| **Small effect** | A 5% rise at −0.4 moves units only about 2% | That's why the design was chosen by power analysis, not by gut feel |

## 7. After the test
- **Roll out:** apply +5% to all Household products, then monitor category revenue and units for 8 weeks against a store-level holdout of 1 store.
- **Don't roll out:** keep prices, and report what the estimate rules out (e.g. "elasticity is not above −0.6").
- Either way, publish the readout with the same table as the [simulated readout](../reports/price_test_readout.md).

## 8. Check of the plan itself
The [simulated readout](../reports/price_test_readout.md) plants a known response into real sales and runs this exact plan 40 times per case. When the rise truly pays (−0.4), the rule said roll out 82% of the time (consistent with the designed 89%). When it doesn't (−1.0), it never wrongly said roll out. The estimates were unbiased.

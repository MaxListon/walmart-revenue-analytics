# Interview Q&A: Walmart Revenue Performance Review

The questions an interviewer is most likely to ask about this project, with plain-language answers. Each answer starts with the 15-second version and then gives detail if they dig in. Numbers are from `outputs/`.

---

## The 30-second pitch
> "I analyzed five years of real Walmart sales, 59 million daily records across 10 stores. Revenue grew 65%, but when I held the product range fixed, the same products in the same stores were shrinking for three years. Growth was coming from adding products. I tested why: it wasn't new products stealing sales or a pricing problem; it was mostly weaker demand, plus about $0.8M a year in stock-outs. I sized the levers, designed a price test with real power calculations, and built a forecast with 0.9% backtest error, less than half that of a naive run-rate."

---

## About the data

**Is this real data?**
Yes. It's the M5 forecasting competition dataset, which Walmart released through the University of Nicosia in 2020: real daily unit sales and weekly shelf prices for 3,049 products in 10 stores. Product names are anonymized, but categories, departments, stores and states are real. Three peer-reviewed papers describe it, including one showing it behaves like other real grocery datasets.

**Where does revenue come from? There's no revenue column.**
Revenue = units sold × that week's shelf price. I checked that every unit sold has a price, so the calculation is complete, and units and revenue reconcile exactly across every table.

**What are the data's limits?**
- **Sample:** 10 stores and 3,049 products, not all of Walmart.
- **Survivorship:** only products still sold in 2016 are included, so products discontinued earlier are missing. That inflates early-year growth, which is one reason I built comparable sales.
- **No promotion or inventory data:** so I flag what that affects (price cuts, stock-outs) instead of hiding it.

**Why fiscal years, and what's the 53-week thing?**
Walmart's fiscal year runs February to January, and the data's week codes follow it. FY2014 had 53 weeks, which would overstate its growth by about 2 points, so all growth is on a 52-week basis.

---

## Growth metrics

**What are comparable sales, and why do they matter?**
Comparable ("comp") sales compare the same products in the same stores year over year, so adding new products can't inflate growth. Here a store-item counts if it was on the shelf all 52 weeks of both years. Retailers, Walmart included, report comps to investors for exactly this reason.

**How did you split growth into price, volume and mix?**
For existing products:
- **Volume:** the change in units, valued at last year's average price.
- **Mix:** whether shoppers shifted to pricier or cheaper products.
- **Price:** the change in each product's own price, weighted by what sold this year.

Everything else is assortment change: last year's launches reaching a full year, new listings and lost listings. Every component is checked to add up to the total change to the cent, for every year, store and category.

**How confident are you in "43% of growth was organic"?**
95% CI 29–52%, from a bootstrap: I resampled products 2,000 times, keeping each product's stores together because they're correlated. FY2016 comp is +5.6% (CI +2.9% to +8.4%).

**Does the decline depend on how you define "existing product"?**
I tested five definitions. FY2014–15 are negative under every definition that requires a full or near-full year on the shelf. FY2013 flips sign under looser rules, so I call it fragile. The loosest rule ("sold at least once in both years") hides the decline because it mixes in new products ramping up.

---

## "Why did existing products shrink?"

**How did you rule out cannibalization?**
If new products stole sales, store-departments that added more of them should have weaker comp growth. I built a panel of 280 store × department × year rows, with fixed effects for each store-year (store traffic) and each department-year (chain-wide category trends). The coefficient came out positive, the opposite of cannibalization. A placebo, using products added to *other* departments of the same store, behaved the same way.

**Could it just be products getting old?**
Then older products would decline and newer ones wouldn't. Instead, every launch cohort fell together in FY2014–15 and recovered together in FY2016, which points to something time-based, not age-based.

**What about stock-outs?**
I split comp growth into availability (days on the shelf) and sales per available day. Availability explains 2.0 of the 9.2-point FY2014 decline; the remaining 7.2 points came from lower sales per available day.

**Was it pricing?**
No. Comparing Walmart's same-product price changes with official BLS inflation, Walmart held food prices 1.4–1.7 points *below* food inflation in FY2014–15, and volume still fell. Then in FY2016 it priced 0.7 points *above* inflation, and comparable sales recovered anyway. Prices and volume moved the opposite way to a pricing story.

**So what caused it?**
The data can show timing but not prove the cause. Same-item food sales turned negative in October 2012 and recovered in April 2014. That lines up with Walmart's weakest publicly reported year (U.S. comps −0.6% in FY2014). I'd call it a broad demand slowdown and say I can't pin down the reason from this data.

---

## Stock-outs

**How do you detect a stock-out without inventory data?**
A run of zero-sale days is flagged when the product's own history makes it very unlikely: under 0.1%, given how often that product normally has zero-sale days in the 28 days before and after. I use the product's *observed* zero-day rate rather than a Poisson assumption, because real demand is lumpier, and my first Poisson version flagged an implausible 15% of revenue.

**How do you avoid calling a discontinued product a stock-out?**
- A run only counts if sales come back afterward.
- I take the more conservative of the before/after rates.
- Long gaps are classified separately: "seasonal" if the gap recurs at the same time each year, "chain-wide" if most other stores are dark at the same time.

Only short gaps count as lost sales: $0.79M in FY2016 (1.9% of revenue), which is in line with industry norms. A test confirms the detector ignores a product whose demand truly disappears.

---

## Pricing

**What's price elasticity?**
The % change in units for a 1% change in price. Above −1 in absolute terms (e.g. −0.4) means a price rise loses fewer units than it gains in price, so revenue goes up.

**How did you estimate it?**
Two ways:
1. **Panel model:** a Poisson regression of units on log price, with item-store fixed effects (each product's normal popularity) and store-week fixed effects (seasonality, holidays, store traffic).
   - **Why Poisson:** about a quarter of weeks have zero sales, and Poisson handles zeros directly.
   - **What it fixed:** my first version used log(1 + units), which biased results toward zero. For FOODS_3 it said −0.66; Poisson says −0.92.
2. **Event study:** for 15,246 permanent price changes, compare the store that changed price with stores selling the same product in the same weeks that didn't (a stacked difference-in-differences).

**What did you find?**
- **Household:** about −0.4 in the main model (HOUSEHOLD_1 −0.41, HOUSEHOLD_2 −0.39). The checks are noisier: on fast sellers only, HOUSEHOLD_2 is +0.09, and the event study for HOUSEHOLD_1 alone is −1.63 with a wide CI. So I call Household the best candidate for a test, not a proven fact.
- **Permanent increases:** −0.51 (CI −0.89 to −0.14).
- **Cuts:** −3.2, probably inflated by "Rollback" signage that isn't in the data.

**Any problems in the event study?**
Yes: treated stores dip in the week *before* a change. I show it on the chart and re-run without that week. The conclusions hold.

**What about temporary price cuts?**
A −30% temporary cut lifted units about +4.5%, which isn't statistically significant (CI −0.4% to +9.8%). They're also rare, because Walmart runs everyday low pricing: about $7K of discount on the 916 cuts I could study cleanly in FY2016, and about $20K on a broad screen of every short price dip. So I dropped them from the recommendations; chain-wide gaps ($2.1M) mattered far more.

**Why recommend a test instead of just raising prices?**
The estimates come from past price changes, which weren't random. Walmart might have raised prices on products it expected to sell well. A randomized test removes that bias.

**How did you design the test?**
I ran 200 "A/A tests" per design on real history: random fake treatment groups where nothing actually changed. The spread of the results shows the real noise.
- **A 2% test is far too small.** Under 40% power to tell −0.4 from −1.
- **Randomizing whole products doesn't work either:** about 25% power at 5%, because product-to-product differences swamp the signal.
- **Randomizing product-store pairs does:** each product compared with itself across stores, with a 5% increase for 12 weeks, gives 89% power (95% CI 83–94%). The false-positive rate in A/A tests was about 3–6%, close to the intended 5%.

---

## Product segments

**How did you segment products, and why products instead of customers?**
The data has no customer IDs, so I segmented what a retailer actually manages: products. For each of the 3,049 products I measured five FY2016 behaviours: how fast it sells, how often it has a week with no sales, how seasonal it is, how much it lifts on SNAP days, and how much revenue it loses to stock-outs. I standardised them and ran k-means with 20 random starts.

**How did you choose five segments?**
Honestly, the data didn't pick for me: the silhouette score (how well separated the groups are) was flat at about 0.2 for 4, 5 and 6 groups. So I chose 5, the smallest number that separates a stock-out-risk group, because that group needs its own action. I report all three scores rather than pretending the choice was automatic. I also re-ran it with different random starts: products land in the same group 81% of the time (adjusted Rand index 0.81), so the groups are stable.

**What did it find?**
Core fast movers are 27% of products but 46% of revenue. The surprise was SNAP-driven staples: 14% of products, 41% of store stock-out losses. Demand spikes on SNAP days and shelves run dry, which links two recommendations (stock-outs and SNAP timing) into one conversation with replenishment.

**How do you know the method works?**
A test plants five groups of fake products with known behaviours and checks that the method puts over 95% of them back in the right group with the right name, and gives the same answer however the rows are ordered.

## Stress-testing the recommendations

**How good is your forecasting, really?**
I scored six methods with the M5 competition's own metric, WRMSSE, on 28-day daily forecasts over six windows, including the official M5 validation and evaluation periods. I forecast the 70 store × department series and added them up to the competition's 9 aggregate levels; I left out the product-level levels, so my scores aren't comparable with the Kaggle leaderboard, only with each other. The best was a weekday average that adds the SNAP-day effects I'd measured: 34% better than seasonal naive and 22% better than exponential smoothing, winning 5 of 6 windows. That's the SNAP finding paying off in a forecast.

**Can you tell which new products will succeed?**
By week 4, mostly yes, and with one number: first-month revenue per store-week. Trained on earlier launches and tested on the latest 30%, it ranks future top sellers with an AUC of 0.92, and its top-20% picks become top sellers 71% of the time against 19% at random. A logistic regression with five more signals did no better, and it was overconfident at the top. My first comparison made the model look much better, because I'd compared it with a units-based rule while the outcome was revenue; once the baseline used the same currency, the gap vanished. Caveat: the data only has products still sold in 2016, so I can't predict withdrawals.

**Is the $0.79M of stock-outs really recoverable?**
Not all of it. With no inventory data, I simulated weekly ordering with a 3-day lead time for every store-product in the two segments where stock-outs concentrate, using real demand, and calibrated the safety stock so today's simulated policy loses exactly what my detector measured. A moderate safety-stock increase recovers about 26% for $85K more average inventory, with diminishing returns. Scaled up, that's about $0.2M a year, so I corrected the recommendation. SNAP-aware ordering helped only the SNAP staples, by about $17K a year at the same inventory, which makes sense because only they spike on SNAP days.

**How do you know the price-test analysis would work?**
I wrote the brief before any result (hypothesis, design, metrics, guardrails, decision rule), then planted a known demand response into real Household sales and ran the exact analysis. Repeated 40 times per case, it said roll out 82% of the time when the rise truly pays and never when it doesn't, with unbiased estimates. The brief also flags the biggest risk: shoppers substituting from raised products to unraised ones in the same store, which would make demand look more elastic than a full rollout.

## SNAP, stores, forecast

**How did you measure the SNAP effect?**
Daily store × category revenue, regressed on whether it's a SNAP day in that state, with fixed effects for store-month and store-weekday. Food rises +9% to +28% depending on the state; non-food barely moves, which works as a built-in control. For timing, I used the ratio of food to household spending, which cancels out paydays that affect both.

**What's a synthetic control?**
To measure a store's step change, I build a weighted "twin" from stores without one, matched on the year before. After the change, the gap between the store and its twin is the effect. With only 6 possible comparison stores, the best possible placebo p-value is 1/7. All four effects reached it, and I say that's the limit.

**How did you pick the forecasting method?**
I backtested four methods from the same point (week 16) in FY2014, FY2015 and FY2016. The winner projects each store from its own trend, but stops a one-time jump (like CA_2's) from compounding once it reaches its anniversary. Average full-year error: 0.9%.

---

## Process questions

**What went wrong along the way?**
- **Pricing:** my first pricing recommendation (FOODS_3) didn't survive a better model, so I changed it. Later I'd written that Household was −0.4 "in every model"; re-reading the robustness tables showed that wasn't true, so I reworded it and leaned harder on the test.
- **Recommendations:** I'd recommended auditing temporary price cuts before sizing them. Once I did, they were worth about $20K a year, so I replaced that action.
- **Test design:** my first test design (2%, 8 weeks) had about 11% power, so I redesigned it. Then my first power estimates (50 simulations) moved by 20 points between runs, so I raised it to 200 simulations and added confidence ranges.
- **Stock-outs:** my first stock-out detector flagged 15% of revenue, which was implausible, so I recalibrated it.
- **Launch model:** my first comparison flattered the model by pitting it against a units-based rule when the outcome was revenue. With a fair baseline, the simple rule was just as good.
- **Reproducibility:** re-running the whole pipeline and diffing every output caught two results that changed between runs. Two analyses with fixed random seeds were still picking different products because the database returned rows in a different order each time. Sorting before sampling fixed it; tests now shuffle the input and require identical results.

Each time, the checks caught the problem.

**How do you know the numbers are right?**
- **pytest:** 36 tests, including methods recovering known answers from simulated data (a −1.2 elasticity, a +40% store jump, a planted stock-out, five planted product segments, a hand-worked monthly bridge, a planted price response).
- **dbt:** 34 data tests, including one that checks the dbt build against the Python pipeline.
- **Reconciliation:** every revenue bridge reconciles to the cent.

**What would you do with more data?**
- **Promotion and display data:** to separate price effects from signage.
- **Inventory records:** to confirm the stock-outs.
- **Store remodel dates:** to explain the step changes.
- **More stores:** for stronger store-level comparisons.
- **Customer data:** for segment-level analysis.

**What would you tell a VP in one sentence?**
"Growth has come from adding products. Existing products only started growing again this year, so report comparable sales, fix stock-outs, and run a properly designed 5% Household price test."

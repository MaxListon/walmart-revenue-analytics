-- FY2017 year-to-date vs the same fiscal weeks of FY2016.
-- Data ends partway through fiscal week 17, so YTD = weeks 1-16.
WITH w AS (
    SELECT fiscal_year, {group_col} AS segment, sum(revenue) AS revenue, sum(units) AS units
    FROM fct_item_store_week
    WHERE fiscal_year IN (2016, 2017) AND fiscal_week <= 16
    GROUP BY ALL
)
SELECT segment,
       sum(revenue) FILTER (WHERE fiscal_year = 2016) AS ytd_revenue_prior,
       sum(revenue) FILTER (WHERE fiscal_year = 2017) AS ytd_revenue,
       sum(revenue) FILTER (WHERE fiscal_year = 2017)
         / sum(revenue) FILTER (WHERE fiscal_year = 2016) - 1 AS ytd_growth,
       sum(units) FILTER (WHERE fiscal_year = 2017)
         / sum(units) FILTER (WHERE fiscal_year = 2016) - 1   AS ytd_unit_growth
FROM w
GROUP BY segment
ORDER BY ytd_revenue DESC;

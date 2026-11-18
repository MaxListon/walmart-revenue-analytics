-- Cross-implementation check: dbt's comp sales and annual revenue must match
-- the Python pipeline's outputs (written independently from sql/metrics/).
with py_comp as (
    select * from read_csv('{{ var("outputs_path") }}/comp_sales.csv', header = true)
),
py_rev as (
    select * from read_csv('{{ var("outputs_path") }}/annual_revenue.csv', header = true)
)
select 'comp_growth' as metric, d.fiscal_year, d.comp_growth as dbt_value, p.comp_growth as python_value
from {{ ref('comp_sales') }} d join py_comp p using (fiscal_year)
where abs(d.comp_growth - p.comp_growth) > 1e-9
union all
select 'revenue_52wk', d.fiscal_year, d.revenue_52wk, p.revenue_52wk
from {{ ref('annual_revenue') }} d join py_rev p using (fiscal_year)
where abs(d.revenue_52wk - p.revenue_52wk) > 0.01

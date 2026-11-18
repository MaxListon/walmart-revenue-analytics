-- Chain revenue bridge for every year pair: volume, mix, price (comp items),
-- launches annualizing, new and lost listings. Must reconcile exactly.
with yr as (
    select store_id, item_id, fiscal_year, count(*) as weeks_listed, sum(units) as q, sum(revenue) as r
    from {{ ref('fct_item_store_week') }}
    where fiscal_week <= 52 and fiscal_year between 2012 and 2016
    group by all
),
j as (
    select coalesce(b.fiscal_year, a.fiscal_year + 1) as fiscal_year,
           coalesce(a.q, 0) as q0, coalesce(a.r, 0) as r0, coalesce(b.q, 0) as q1, coalesce(b.r, 0) as r1,
           case when a.weeks_listed = 52 and b.weeks_listed = 52 then 'comp'
                when a.item_id is null or a.q = 0 then 'new'
                when b.item_id is null or b.q = 0 then 'lost'
                else 'annualization' end as bucket
    from yr a full outer join yr b
      on a.store_id = b.store_id and a.item_id = b.item_id and b.fiscal_year = a.fiscal_year + 1
),
comp as (
    select fiscal_year, sum(q0) as Q0, sum(q1) as Q1, sum(r0) as R0c, sum(r1) as R1c,
           sum(q1 * case when q0 > 0 then r0 / q0 when q1 > 0 then r1 / q1 else 0 end) as q1p0
    from j where bucket = 'comp' group by 1
),
other as (
    select fiscal_year,
           sum(r1 - r0) filter (where bucket = 'annualization') as annualization,
           sum(r1) filter (where bucket = 'new')               as new_listings,
           sum(r0) filter (where bucket = 'lost')              as lost_listings,
           sum(r0) as revenue_prior, sum(r1) as revenue_current
    from j group by 1
)
select o.fiscal_year, o.revenue_prior,
       (c.Q1 - c.Q0) * (c.R0c / c.Q0)  as volume_effect,
       c.q1p0 - c.Q1 * (c.R0c / c.Q0)  as mix_effect,
       c.R1c - c.q1p0                  as price_effect,
       coalesce(o.annualization, 0)    as launch_annualization_effect,
       coalesce(o.new_listings, 0)     as new_listings_effect,
       -coalesce(o.lost_listings, 0)   as lost_listings_effect,
       o.revenue_current
from other o join comp c using (fiscal_year)
where o.fiscal_year between 2013 and 2016

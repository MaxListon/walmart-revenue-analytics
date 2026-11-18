-- Prior revenue + every bridge component must equal current revenue (to the cent).
select fiscal_year,
       revenue_prior + volume_effect + mix_effect + price_effect + launch_annualization_effect
         + new_listings_effect + lost_listings_effect - revenue_current as gap
from {{ ref('revenue_bridge_total') }}
where abs(revenue_prior + volume_effect + mix_effect + price_effect + launch_annualization_effect
          + new_listings_effect + lost_listings_effect - revenue_current) > 0.01

with monthly_totals as (
    select
        cast(date_trunc('month', sale_date) as date) as sale_month,
        sum(net_amount_ttc) as total_ttc
    from {{ ref('fct_sales') }}
    group by cast(date_trunc('month', sale_date) as date)
)

select
    s.*,
    t.total_ttc
from {{ ref('mart_monthly_category_share') }} s
left join monthly_totals t
    on s.sale_month = t.sale_month
where t.total_ttc is null
   or (
       t.total_ttc = 0
       and s.part_ca_pct is not null
   )
   or (
       t.total_ttc <> 0
       and (
           s.part_ca_pct is null
           or abs(
               s.part_ca_pct
               - round(100.0 * s.chiffre_affaires_ttc / t.total_ttc, 2)
           ) > 0.000001
       )
   )
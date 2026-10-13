select
    sale_month,
    sum(part_ca_pct) as total_pct,
    count(*) as nombre_categories
from {{ ref('mart_monthly_category_share') }}
group by sale_month
having (
    sum(chiffre_affaires_ttc) <> 0
    and (
        count(part_ca_pct) <> count(*)
        or abs(sum(part_ca_pct) - 100.0)
            > count(*) * 0.005 + 0.000001
    )
)
or (
    sum(chiffre_affaires_ttc) = 0
    and count(part_ca_pct) <> 0
)
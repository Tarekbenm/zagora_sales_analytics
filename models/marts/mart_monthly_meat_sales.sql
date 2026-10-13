select
    cast(date_trunc('month', sale_date) as date) as sale_month,
    product_category,
    meat_type,
    count(*) as nombre_lignes_vente,
    sum(net_amount_ttc) as chiffre_affaires_ttc
from {{ ref('fct_sales') }}
group by
    cast(date_trunc('month', sale_date) as date),
    product_category,
    meat_type
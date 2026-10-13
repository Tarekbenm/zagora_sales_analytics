with monthly_sales as (
    select
        cast(date_trunc('month', sale_date) as date) as sale_month,
        product_code,
        product_label_clean,
        product_category,
        meat_type,
        sum(net_amount_ttc) as chiffre_affaires_ttc
    from {{ ref('fct_sales') }}
    group by
        cast(date_trunc('month', sale_date) as date),
        product_code,
        product_label_clean,
        product_category,
        meat_type
)

select
    *,
    dense_rank() over (
        partition by sale_month
        order by chiffre_affaires_ttc desc
    ) as rang_ca
from monthly_sales
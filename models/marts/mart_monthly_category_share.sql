with category_sales as (
    select
        sale_month,
        product_category,
        sum(chiffre_affaires_ttc) as chiffre_affaires_ttc
    from {{ ref('mart_monthly_meat_sales') }}
    group by sale_month, product_category
)

select
    sale_month,
    product_category,
    chiffre_affaires_ttc,
    round(
        100.0 * chiffre_affaires_ttc
        / nullif(
            sum(chiffre_affaires_ttc) over (
                partition by sale_month
            ),
            0
        ),
        2
    ) as part_ca_pct
from category_sales
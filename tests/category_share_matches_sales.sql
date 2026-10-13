with expected as (
    select
        cast(date_trunc('month', sale_date) as date) as sale_month,
        product_category,
        sum(net_amount_ttc) as amount,
        1 as present
    from {{ ref('fct_sales') }}
    group by
        cast(date_trunc('month', sale_date) as date),
        product_category
),

actual as (
    select
        sale_month,
        product_category,
        chiffre_affaires_ttc as amount,
        1 as present
    from {{ ref('mart_monthly_category_share') }}
)

select
    coalesce(e.sale_month, a.sale_month) as sale_month,
    coalesce(e.product_category, a.product_category) as product_category,
    e.amount as montant_attendu,
    a.amount as montant_observe
from expected e
full outer join actual a
    on e.sale_month = a.sale_month
    and e.product_category = a.product_category
where e.present is null
   or a.present is null
   or e.amount is null
   or a.amount is null
   or e.amount <> a.amount
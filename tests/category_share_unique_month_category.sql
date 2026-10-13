select
    sale_month,
    product_category,
    count(*) as nombre_lignes
from {{ ref('mart_monthly_category_share') }}
group by sale_month, product_category
having count(*) > 1
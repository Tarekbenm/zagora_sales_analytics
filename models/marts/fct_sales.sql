select
    s.ticket_id,
    s.ticket_type,
    s.sale_date,
    s.product_code,
    p.product_label_clean,
    p.product_category,
    p.meat_type,
    p.classification_status,
    s.quantity,
    s.unit_price_ttc,
    s.discount_amount_ttc,
    s.net_amount_ttc,
    s.source_month,
    s.source_file,
    s.source_row_number
from {{ ref('stg_sales_lines') }} as s
left join {{ ref('stg_products') }} as p
    on s.product_code = p.product_code
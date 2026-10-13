---Pour calculer les CA 
select
    ticket_id,
    ticket_type,
    cast(sale_timestamp as timestamp) as sale_timestamp,
    cast(sale_timestamp as date) as sale_date,
    product_code,
    product_label_raw,
    cast(quantity as decimal(18, 6)) as quantity,
    cast(unit_price_ttc as decimal(18, 2)) as unit_price_ttc,
    cast(discount_percent as decimal(7, 4)) as discount_percent,
    cast(vat_rate as decimal(7, 4)) as vat_rate,
    cast(gross_amount_ttc as decimal(18, 2)) as gross_amount_ttc,
    cast(discount_amount_ttc as decimal(18, 2)) as discount_amount_ttc,
    cast(net_amount_ttc as decimal(18, 2)) as net_amount_ttc,
    source_month,
    source_file,
    cast(source_row_number as integer) as source_row_number
from {{ source('boucherie_raw', 'raw_sales_lines') }}
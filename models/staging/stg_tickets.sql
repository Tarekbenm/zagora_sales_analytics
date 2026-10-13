select
    ticket_id,
    ticket_type,
    cast(sale_timestamp as timestamp) as sale_timestamp,
    cast(sale_timestamp as date) as sale_date,
    cast(ticket_total_ttc as decimal(18, 2)) as ticket_total_ttc,
    cast(calculated_total_ttc as decimal(18, 2)) as calculated_total_ttc,
    cast(total_difference as decimal(18, 2)) as total_difference,
    cast(article_count as integer) as article_count,
    payment_methods,
    source_month,
    source_file,
    cast(source_row_number as integer) as source_row_number
from {{ source('boucherie_raw', 'raw_tickets') }}
select
    cast(date_trunc('month', sale_date) as date) as sale_month,
    count(*) as nombre_tickets,
    sum(ticket_total_ttc) as chiffre_affaires_ttc,
    round(
        sum(ticket_total_ttc) / nullif(count(*), 0),
        2
    ) as panier_moyen_ttc
from {{ ref('stg_tickets') }}
group by
    cast(date_trunc('month', sale_date) as date)
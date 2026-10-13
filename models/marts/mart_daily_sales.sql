select
    sale_date,
    count(distinct ticket_id) as nombre_tickets,
    sum(ticket_total_ttc) as chiffre_affaires_ttc,
    round(
        sum(ticket_total_ttc)
        / nullif(count(distinct ticket_id), 0),
        2
    ) as panier_moyen_ttc
from {{ ref('stg_tickets') }}
group by sale_date
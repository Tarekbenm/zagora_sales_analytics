with source_total as (
    select
        coalesce(sum(ticket_total_ttc), 0) as montant
    from {{ ref('stg_tickets') }}
),

daily_total as (
    select
        coalesce(sum(chiffre_affaires_ttc), 0) as montant
    from {{ ref('mart_daily_sales') }}
)

select
    s.montant as total_tickets,
    d.montant as total_journalier
from source_total as s
cross join daily_total as d
where s.montant <> d.montant
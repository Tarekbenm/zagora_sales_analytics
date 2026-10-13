with comparaison as (
    select
        sale_month,
        nombre_tickets,
        chiffre_affaires_ttc,
        panier_moyen_ttc,
        lag(sale_month) over (
            order by sale_month
        ) as mois_precedent,
        lag(chiffre_affaires_ttc) over (
            order by sale_month
        ) as ca_precedent
    from {{ ref('mart_monthly_kpis') }}
)

select
    sale_month,
    nombre_tickets,
    chiffre_affaires_ttc,
    panier_moyen_ttc,
    case
        when sale_month = add_months(mois_precedent, 1)
        then round(
            100.0 * (chiffre_affaires_ttc - ca_precedent)
            / nullif(ca_precedent, 0),
            2
        )
    end as evolution_ca_pct
from comparaison
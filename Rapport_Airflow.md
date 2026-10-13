# Rapport Airflow

## Environnement et objectif

L'environnement Docker Compose utilise Apache Airflow 2.9.2 avec CeleryExecutor,
PostgreSQL 13 pour les métadonnées et Redis 7.2-bookworm comme broker.
L'image personnalisée installe openpyxl 3.1.5. Les services comprennent le
webserver, le scheduler, le worker, le triggerer et l'initialisation ; un CLI
et Flower sont disponibles via des profils optionnels.

L'orchestration automatise la préparation locale des exports Excel mensuels
jusqu'à la génération de CSV contrôlés. Les sources sont montées en lecture
seule ; les données métier et les paramètres secrets restent hors du dépôt.

## DAG boucherie_pipeline

L'enchaînement est `verifier_sources → parser_excel → controler_csv`.
Le DAG est programmé à 06:00 Europe/Paris, sans rattrapage historique, avec une
seule exécution active. Chaque tâche peut être relancée une fois après une minute.
Le parsing dispose d'un délai maximal de 30 minutes. Le DAG est en pause à sa création.

1. `verifier_sources` recherche les fichiers `YYYY_MM.xlsx`, valide leur mois
   et vérifie qu'ils ne sont pas vides. L'absence de sources provoque un échec.
2. `parser_excel` appelle le parseur existant `scripts/normalize_excel.py`.
   L'attribut de style Excel `biltinId` est corrigé en `builtinId` dans une copie
   en mémoire, sans modifier les sources. Le parseur extrait les tickets et
   articles, calcule les montants avec Decimal et relève les anomalies prévues :
   doublons de tickets dans un fichier, mois incohérents, articles sans ticket et
   écarts de total supérieurs à 0,02. Une extraction sans tickets ou articles échoue.
3. `controler_csv` vérifie les colonnes attendues, la structure de chaque ligne
   et le nombre de lignes annoncé par le manifeste de génération.

## Génération des CSV

Trois fichiers sont produits par mois : tickets, lignes de vente (`sales_lines`)
et rejets (`rejects`), encodés en UTF-8 avec BOM.
Les sorties sont isolées dans `data/airflow_runs/<sha256 du run_id>/`.
L'écriture utilise un fichier temporaire puis un remplacement atomique ; une
relance réutilise le même dossier. Les XCom ne contiennent que noms, chemins et compteurs.

## Résultats du test

Le 23 septembre 2026, la commande suivante a exécuté les trois tâches dans
le conteneur worker :

```powershell
docker compose exec -T airflow-worker airflow dags test boucherie_pipeline 2026-09-23
```

Les trois tâches et le DAG se sont terminés en `success`.

| Indicateur | Résultat |
| --- | ---: |
| Fichiers Excel traités | 9 |
| Tickets | 11 065 |
| Lignes de vente | 35 774 |
| CSV générés | 27 |
| Rejets détectés | 0 |

Les 27 CSV comprennent 9 fichiers de tickets, 9 de lignes de vente et 9 de
rejets avec uniquement leurs en-têtes. Le contrôle des CSV a confirmé les compteurs.

## Limites actuelles

Airflow automatise actuellement la préparation locale jusqu'aux CSV contrôlés,
mais pas encore le chargement Databricks ni l'exécution dbt. Le test direct
du DAG ne valide pas à lui seul le déclenchement par le scheduler et Celery.
Les anomalies métier sont journalisées et exportées, sans bloquer le DAG.
Tous les Excel sont relus à chaque exécution ; aucune purge automatique des
sorties n'est prévue. L'environnement Compose est destiné au développement local.

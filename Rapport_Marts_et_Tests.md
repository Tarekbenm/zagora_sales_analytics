# Rapport des marts et des tests — Boucherie

Date : 22 septembre 2026.

## Périmètre métier retenu

L'analyse porte sur les ventes en montant TTC après remise, par produit, catégorie et type de viande, de janvier à septembre 2026. Elle couvre également le nombre de tickets, le panier moyen et les évolutions dans le temps. À la demande du porteur du projet, les indicateurs de quantités, de kilos et de pièces sont écartés. La quantité reste dans les données détaillées, mais aucun classement présenté ici ne mesure les volumes physiques.

Le rapport initial doit donc se lire avec ces ajustements : « le plus vendu » signifie ici « qui génère le plus de chiffre d'affaires », et la question sur les quantités par catégorie est remplacée par le chiffre d'affaires et la part de chaque catégorie. Les montants sont TTC ; ils ne représentent ni une marge ni un bénéfice. Le classement automatique des produits contient des hypothèses et des valeurs « Non précisé » : ce n'est pas une certification de leur composition.

## Organisation des données

Dans Databricks, les sources sont `workspace.boucherie_raw.raw_tickets` et `workspace.boucherie_raw.raw_sales_lines`. Les résultats sont créés dans `workspace.dbt_boucherie_dev`. Le référentiel `product_reference` est chargé par `dbt seed`.

Les vues `stg_tickets`, `stg_sales_lines` et `stg_products` préparent les types et les colonnes. Les modèles de ce projet sont actuellement matérialisés en vues : dbt enregistre une requête consultable, plutôt qu'une copie physique de chaque résultat. Les dépendances sont exprimées par `ref()` ; les tables brutes par `source()`.

Contrôles communiqués lors des exécutions dans Studio : 11 065 tickets, 35 774 lignes de vente et 113 produits. Les six premiers tests du staging ont réussi. Le contrôle avant/après jointure a donné des comptes et des montants égaux. Ces observations sont distinctes des nouveaux tests locaux décrits plus bas.

## 1. `fct_sales` : détail des ventes enrichi

**Une ligne représente une ligne d'article vendue.** Le modèle relie `stg_sales_lines` à `stg_products` par `product_code` avec un `left join`. Il conserve les montants des ventes et ajoute le libellé nettoyé, la catégorie, le type de viande et le statut de classification.

Il constitue la base des analyses par produit. La colonne `net_amount_ttc` vient de l'extraction Python : montant de la ligne après remise, arrondi au centime. Le modèle conserve aussi `source_file` et `source_row_number`, qui permettent de retrouver la ligne du fichier Excel.

Une vente sans correspondance reste présente avec des attributs produits NULL. Un référentiel contenant plusieurs lignes pour un code multiplierait les ventes lors de la jointure : les tests `unique`, `not_null` et `relationships` du staging sont donc importants. Une valeur vide n'est pas systématiquement une valeur NULL.

## 2. `mart_monthly_meat_sales` : CA mensuel par catégorie et viande

**Une ligne représente un mois, une catégorie et un type de viande.** La date est ramenée au premier du mois avec `date_trunc`. Le modèle calcule le nombre de lignes de vente et la somme de `net_amount_ttc` pour chaque groupe.

Il répond à : « Quel chiffre d'affaires chaque type de viande génère-t-il par mois et par catégorie ? » Le nombre de lignes n'est ni un nombre de tickets, ni une quantité de viande. Pour comparer une même espèce toutes catégories confondues, il faut sommer son CA entre les catégories. Le fichier inclut aussi les produits d'épicerie et les types non précisés.

## 3. `mart_monthly_product_ranking` : classement des produits par CA

**Une ligne représente un produit pour un mois.** Une première étape additionne le CA du produit ; `dense_rank()` classe ensuite ces montants du plus élevé au plus faible, indépendamment dans chaque mois.

Il répond à : « Quel produit génère le plus de chiffre d'affaires chaque mois ? » Deux montants identiques partagent le même rang ; le rang suivant ne saute pas de numéro. Filtrer `rang_ca <= 3` peut donc afficher plus de trois produits par mois.

Exemples communiqués : en janvier, VIANDE HACHEE apparaît au rang 1 avec 8 209,60 €, MERGUEZ au rang 2 avec 3 554,85 €, et VEAU TAJINE / SAUCE au rang 3 avec 3 405,66 €. Ce classement ne mesure pas les quantités vendues.

## 4. `mart_monthly_kpis` : indicateurs de caisse mensuels

**Une ligne représente un mois.** Le modèle part de `stg_tickets` et calcule :

- `nombre_tickets` : nombre de lignes de tickets (`count(*)` dans la version construite).
- `chiffre_affaires_ttc` : somme de `ticket_total_ttc`, le montant annoncé par la caisse.
- `panier_moyen_ttc` : CA divisé par le nombre de tickets, arrondi à deux décimales.

Il répond à : « Quel est le CA mensuel et le panier moyen ? » Les totaux de caisse et les totaux des articles correspondent exactement pour janvier à avril dans les résultats transmis. Cela ne prouve pas à lui seul l'absence de doublons.

**Point à contrôler :** le rapport initial demande un nombre distinct de tickets. La version mensuelle utilise `count(*)`, ce qui est équivalent uniquement si chaque ligne représente un ticket distinct. Il reste à vérifier la clé des tickets (identifiant seul ou combiné au fichier/type), puis à harmoniser ce calcul avec le modèle quotidien.

## 5. `mart_monthly_growth` : évolution mensuelle du CA

**Une ligne représente un mois.** Le modèle utilise `lag()` sur `mart_monthly_kpis` pour retrouver le mois et le CA précédents. La variation est :

`100 × (CA du mois − CA précédent) / CA précédent`.

Il répond à : « Comment le chiffre d'affaires évolue-t-il entre deux mois ? » La comparaison n'est faite que pour des mois consécutifs. Le résultat reste NULL pour le premier mois, un mois précédent manquant ou un CA précédent nul ; il ne faut pas remplacer ces valeurs par 0 %.

La version Studio a été écrite avec `add_months`. La copie locale emploie `dbt.dateadd` pour exprimer le même calcul avec DuckDB et Databricks. Comparer un mois incomplet à un mois complet peut donner une baisse trompeuse : la couverture des fichiers doit être vérifiée avant interprétation.

## 6. `mart_daily_sales` : indicateurs par journée

**Une ligne représente une date de vente.** Le modèle calcule le nombre distinct de `ticket_id`, la somme des totaux de caisse et le panier moyen du jour.

Il répond à : « Quelles dates réalisent le plus de chiffre d'affaires ? » Trier le CA décroissant permet d'obtenir les meilleures journées. Le modèle ne calcule pas encore une moyenne par jour de semaine, et n'ajoute pas de ligne pour les journées sans ticket.

Tests déjà créés et annoncés réussis dans Studio : date unique et non nulle, indicateurs non nuls, total quotidien égal au total des tickets. Ce dernier contrôle compare deux agrégations des mêmes données : il ne détecte pas des doublons déjà présents dans la source. Les fichiers correspondants de Studio ne sont pas encore tous synchronisés dans le dossier local.

## 7. `mart_monthly_category_share` : part des catégories dans le CA

**Une ligne représente un mois et une catégorie.** Le modèle regroupe le CA de `mart_monthly_meat_sales` par catégorie, puis calcule :

`part_ca_pct = 100 × CA catégorie / CA total du mois`.

Le total mensuel est obtenu avec `sum(...) over (partition by sale_month)`. Cette fenêtre conserve une ligne par catégorie tout en donnant à chaque ligne le total de son mois. Les parts sont arrondies à deux décimales.

Il répond à : « Quelle part du chiffre d'affaires mensuel provient de chaque catégorie ? » Une part de 60 % signifie que la catégorie contribue à 60 % du montant TTC du mois. Si le total du mois est nul, les parts sont NULL. Avec des avoirs et des montants nets négatifs, une part peut être négative ou dépasser 100 % : il ne faut pas rejeter automatiquement ces cas sans règle métier sur les remboursements.

## Nouveaux tests du mart de répartition

Sept tests sont fournis dans le projet local :

| Fichier | Contrôle |
|---|---|
| `models/marts/category_share_tests.yml` | Trois tests `not_null` sur mois, catégorie et CA. |
| `tests/category_share_unique_month_category.sql` | Une seule ligne par couple mois/catégorie. |
| `tests/category_share_matches_sales.sql` | Montants et groupes identiques à un calcul indépendant depuis `fct_sales`, y compris détection de groupes manquants ou supplémentaires. |
| `tests/category_share_percentage.sql` | Chaque pourcentage correspond au CA de la catégorie rapporté au total des ventes ; parts NULL si le total est nul. |
| `tests/category_share_total_percentage.sql` | Somme des parts égale à 100 %, avec une tolérance de 0,005 point par catégorie pour les arrondis ; aucun pourcentage renseigné si le total est nul. |

Un test SQL dbt réussit quand sa requête renvoie zéro ligne. Les lignes retournées indiquent les groupes ou valeurs problématiques. Une réussite ne garantit ni la présence de tous les mois attendus, ni l'exactitude du classement métier, ni l'absence de doublons en amont.

## Exécution dans Studio

### Résultat de la vérification locale

Exécution effectuée le 22 septembre 2026 sur DuckDB, avec dbt Core 1.12.5 : **7 tests réussis, aucune erreur**. La commande a également construit les modèles sélectionnés et rechargé les 113 produits du seed local : résultat global **PASS=17, WARN=0, ERROR=0**. Les détails de cette exécution sont dans `dbt_boucherie/target/run_results.json`. Les nouveaux tests n'ont pas encore été exécutés dans Databricks ; cette validation locale ne remplace pas leur lancement dans Studio.

### Transfert des tests

Copier `category_share_tests.yml` et les quatre fichiers SQL de tests dans les mêmes dossiers du projet Studio. Le fichier YAML a un nom distinct pour ne pas écraser le `schema.yml` des tests quotidiens.

```bash
dbt test --select mart_monthly_category_share
```

Pour recréer également le modèle avant les tests :

```bash
dbt build --select mart_monthly_category_share
```

Le `+` devant un modèle inclut ses ancêtres, par exemple `dbt build --select +mart_monthly_category_share`. Une sélection sans `+` utilise les dépendances déjà créées. Les nouvelles modifications restent locales tant qu'elles ne sont pas copiées ou synchronisées vers Studio/GitHub.

## Réconciliation local / Studio

Les sept modèles détaillés ci-dessus ont été recopiés localement depuis les requêtes de la conversation, car ils étaient absents du dossier local. Ce n'est pas un téléchargement de la branche Studio : toute modification supplémentaire faite dans Studio doit être comparée avant fusion. La configuration DuckDB locale est conservée ; dans Studio, le catalogue de connexion et les destinations modèles/seeds sont `workspace`.

## Points restant à traiter

- Confirmer la clé unique des tickets et harmoniser le décompte quotidien/mensuel.
- Vérifier comment tickets, factures et avoirs sont représentés pour éviter des doubles comptes ou des signes incorrects ; une réconciliation arithmétique ne tranche pas cette question.
- Vérifier la complétude de chaque mois, notamment septembre.
- Documenter les classifications automatiques et les produits sans espèce précisée.
- Synchroniser les fichiers locaux et ceux de Studio, puis enregistrer les changements dans GitHub.
- Adapter les sections sur les quantités du rapport initial au périmètre financier retenu.

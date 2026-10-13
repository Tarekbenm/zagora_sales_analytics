# Chargement automatique des CSV dans Databricks

Le DAG `boucherie_pipeline` enchaine maintenant :

`verifier_sources -> parser_excel -> controler_csv -> charger_databricks`

## Fichiers

- `dags/boucherie_pipeline.py` definit l'ordre des quatre taches. Le chargement attend la reussite du controle CSV.
- `scripts/databricks_loader.py` lit les CSV du lancement courant, les valide et les charge dans Databricks.
- `python_tests/test_databricks_loader.py` teste hors reseau les relances et les echecs avec un client simule.

## Fonctionnement du chargeur

1. `read_manifest` lit les fichiers indiques par `parser_excel`. Il controle les colonnes, le nombre de lignes, les types, les mois et les doublons de provenance `(source_month, source_file, source_row_number)`. Les fichiers doivent se trouver dans `data/airflow_runs`. Les CSV tickets et lignes de vente doivent couvrir les memes mois. Les fichiers rejects restent locaux et ne sont pas charges.
2. `normalize_value` convertit `2026-01` en `2026-01-01`, les identifiants en entiers et verifie les nombres. Dix lignes du CSV d'aout contiennent une remise de 3.5 %. Le chargeur attend donc `discount_percent` en DECIMAL(24,4), apres la migration fournie. Les champs numeriques vides deviennent NULL, sauf les cles obligatoires. Les valeurs metier ne sont pas corrigees silencieusement.
3. `SqlClient` utilise la connexion Airflow `databricks_boucherie` : Host, Password et Extra. Il appelle l'API SQL du warehouse en HTTPS et attend la fin des requetes. Le token ne figure ni dans le code ni dans les messages du script. Aucune nouvelle dependance Python n'est necessaire.
4. `load_csvs` verifie les structures et le format Delta des deux tables existantes. Il cree deux tables intermediaires `_airflow_load_...` avec un suffixe unique a chaque tentative. Il envoie les lignes par lots de 500, sous forme de JSON parametre, puis compare les comptes par mois aux CSV.
5. Lorsque les deux lots sont prets, il execute `INSERT INTO ... REPLACE WHERE source_month IN (...) SELECT ...` pour chaque table. Un mois present dans les CSV est remplace entierement ; les autres mois restent en place. Les CSV doivent donc etre des exports mensuels complets, pas seulement les nouvelles ventes du mois.
6. Il controle les comptes finaux et supprime ses tables intermediaires. Si ce nettoyage echoue, leur nom est indique dans le journal pour un nettoyage ulterieur apres verification des requetes.

## Relance et limites

Relancer le meme lot remplace les memes mois : le chargement n'ajoute pas une seconde copie des ventes. Il ne dedoublonne toutefois pas des doublons metier deja presents sur des lignes Excel differentes.

Le remplacement est atomique pour une table Delta. Les deux tables ne sont pas publiees dans une transaction commune. Si le second remplacement echoue, les tickets peuvent deja etre a jour alors que les lignes de vente ne le sont pas encore. La tache reste en echec ; verifier Query History, attendre la fin de toute requete encore active, puis relancer la tache sur le meme manifest pour terminer. Le script ne relance pas automatiquement une ecriture dont la reponse reseau a ete perdue (`retries=0`). Ne pas lancer de mise a jour dbt entre les deux publications, ni faire de chargement manuel concurrent.

Cette etape ne lance pas encore `dbt build` et ne modifie pas le referentiel produits. La lecture des tables a deja ete testee par `test_connexion_databricks`, mais les droits d'ecriture doivent encore etre verifies lors du premier chargement. Le compte doit notamment pouvoir utiliser le catalogue/schema et le warehouse, lire et modifier les deux tables, et creer les tables intermediaires dans `boucherie_raw`.

## Premier lancement

Executer d'abord `scripts/sql/001_discount_percent.sql` dans Databricks SQL Editor, une instruction a la fois. Cette migration conserve les valeurs existantes et permet les remises fractionnaires. Elle active le type widening Delta, ce qui exige des lecteurs compatibles (Databricks Runtime 15.4 LTS minimum). Le modele dbt caste deja la remise en decimal. En cas d'erreur de migration, ne pas lancer le chargement : transmettre le message. Le script ne modifie pas automatiquement la structure des tables.

Les repertoires `dags` et `scripts` sont montes dans Docker. Aucune reconstruction d'image n'est necessaire. Actualiser Airflow, ouvrir `boucherie_pipeline`, verifier les quatre taches et declencher un nouveau run. Le planning quotidien existant a 06:00 Europe/Paris est conserve pour un DAG active.

Le journal de `charger_databricks` affiche les nombres par table et par mois. Les fichiers de cette implementation sont locaux tant qu'ils n'ont pas ete commites et pousses sur GitHub.

## Verification locale

Depuis la racine du depot :

```powershell
python -m unittest discover -s python_tests -v
```

Les tests simules ne remplacent pas le premier essai sur le warehouse : ils ne valident ni ses autorisations ni son moteur SQL.

## Documentation utilisee

- [API SQL Statement Execution](https://docs.databricks.com/api/statement-execution/v1/execute-statement)
- [INSERT et REPLACE WHERE](https://docs.databricks.com/aws/en/sql/language-manual/sql-ref-syntax-dml-insert-into)
- [Elargissement des types Delta](https://docs.databricks.com/aws/en/tables/features/type-widening)

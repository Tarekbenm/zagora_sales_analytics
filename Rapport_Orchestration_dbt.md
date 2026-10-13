# Execution de dbt par Airflow

Le DAG `boucherie_pipeline` contient cinq taches :

`verifier_sources -> parser_excel -> controler_csv -> charger_databricks -> dbt_build`

## Ce que fait dbt_build

La tache attend la reussite du chargement des deux tables sources. Elle recupere la connexion `databricks_boucherie`, copie les fichiers dbt montes depuis le depot dans un dossier propre au lancement, cree un profil temporaire, puis execute `dbt build`.

`dbt build` charge le seed, construit les modeles dans l'ordre de leurs dependances et execute les tests de donnees. La cible est `workspace.dbt_boucherie_dev`, comme dans Studio. Le schema `boucherie_raw` reste reserve aux sources. L'option `dbt_schema` de Extra permet de definir un autre schema de sortie si besoin.

La tache utilise dbt Core, pas l'API des jobs dbt Studio. Les modeles SQL du depot sont les memes, mais le moteur execute dans Docker est dbt Core avec l'adaptateur Databricks. Aucun nouvel abonnement dbt n'est necessaire pour cette execution ; l'utilisation du warehouse Databricks reste soumise aux conditions du compte Databricks.

## Fichiers ajoutes ou modifies

- `scripts/dbt_pipeline.py` : profil temporaire, copie du projet, lancement et verification du resultat.
- `dags/boucherie_pipeline.py` : ajout de `dbt_build`, apres `charger_databricks`.
- `airflow/Dockerfile` et `airflow/requirements-dbt.txt` : installation de dbt-core 1.12.3 et dbt-databricks 1.12.5 dans un environnement virtuel separe d'Airflow. Les numeros ne doivent pas necessairement etre identiques : cet adaptateur exige dbt-core >=1.11.2 et <1.12.4.
- `docker-compose.yaml` : montage en lecture seule de dbt_project.yml, models, seeds, tests et macros.
- `python_tests/test_dbt_pipeline.py` : tests locaux avec execution dbt simulee.

## Connexion et journaux

Le token provient du champ Password de la connexion Airflow. Il est transmis au sous-processus par `DBT_ENV_SECRET_DATABRICKS_TOKEN`. Le profil ne contient que la reference a cette variable. Il est supprime a la fin de l'execution. Le script retire PYTHONPATH et PYTHONHOME du sous-processus pour ne pas melanger les environnements Python.

Les fichiers compiles, `run_results.json`, les journaux dbt et la copie du projet sont conserves sous `logs/dbt/<empreinte_run>/<tentative>/`. La sortie de la commande est affichee dans le journal de la tache a la fin de dbt build. Durant l'execution, dbt ecrit egalement son propre fichier de journal dans ce dossier.

Si la commande renvoie une erreur, si run_results.json manque ou si une ressource est en echec/ignoree, la tache echoue. Les tests de niveau warning restent des avertissements ; les tests actuels sont bloquants par defaut. Les nouvelles taches ajoutees apres dbt_build devront conserver la dependance de reussite pour ne pas actualiser Power BI apres un echec.

dbt build n'est pas une transaction globale : une erreur de test ne restaure pas automatiquement les modeles deja construits. Ne pas lancer simultanement un build dans Studio sur le meme schema. Aucun rafraichissement Power BI n'est encore ajoute.

## Mise en service, une seule fois

Depuis `Projet_final/dbt-boucherie-github`, sans run actif :

```powershell
docker compose build airflow-worker
docker compose up -d
docker compose exec -T airflow-worker /home/airflow/dbt-venv/bin/dbt --version
```

Le premier build telecharge dbt et ses dependances. Tous les services Airflow partagent la meme image. `up -d` applique aussi les nouveaux montages. Les volumes existants sont conserves ; aucune reinitialisation de la base Airflow n'est requise.

Dans Airflow, actualiser `boucherie_pipeline`, ouvrir Graph et verifier les cinq taches. Declencher ensuite un nouveau run. Le premier lancement effectif valide les autorisations et la compatibilite SQL du projet avec dbt Core. Les tests locaux simules ne remplacent pas cette validation.

Les changements sont locaux tant qu'ils ne sont pas commites et pousses. Apres des modifications dans Studio, les commiter/pousser puis faire `git pull` dans ce clone avant le prochain run (resoudre les modifications locales avant de tirer). Airflow utilise le contenu de ce clone et ne telecharge pas automatiquement GitHub. Le projet actuel n'a pas de packages dbt externes ; si packages.yml est ajoute, son montage et une etape dbt deps devront etre prevus.

## Tests locaux

```powershell
python -m unittest discover -s python_tests -v
```

## References

- [Connexion dbt Databricks](https://docs.getdbt.com/docs/core/connect-data-platform/databricks-setup)
- [Adaptateur dbt-databricks](https://pypi.org/project/dbt-databricks/)

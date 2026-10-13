# Vérifications avant publication

- [ ] Confirmer le droit de republier les contributions du dépôt collectif et la présence d'une licence ou d'une autorisation des contributeurs.
- [ ] Vérifier les fichiers source pour tout nom de client, chemin interne, identifiant, URL privée, token ou secret.
- [ ] Ne pas ajouter de `.env`, exports Excel/CSV client, journaux ou fichiers PBIX contenant des données réelles.
- [ ] Créer des captures Power BI anonymisées ou un rapport connecté à des données synthétiques.
- [ ] Tester le DAG et la chaîne Databricks/dbt dans un environnement de démonstration avant d'affirmer que tout fonctionne en bout de chaîne.
- [ ] Vérifier que les modèles, schémas et exemples ne divulguent pas d'informations commerciales sensibles.

**Note :** le contrôle automatique de chaînes de caractères n'est pas un audit exhaustif de sécurité. Ne pas publier avant revue humaine.

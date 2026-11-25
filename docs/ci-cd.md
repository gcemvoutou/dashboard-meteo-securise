# Pipeline CI/CD (GitHub Actions)

Fichier : `.github/workflows/ci.yml`. Déclenchement : push sur `main`, pull request, ou lancement manuel (`workflow_dispatch`).

```
push / PR
   │
   ├── tests ──────────────┬── sonarqube   (qualité + sécurité, couverture)
   │   pytest + couverture └── dast-zap    (application démarrée puis scannée)
   ├── sast-bandit          (bloquant si gravité ≥ moyenne)
   ├── sast-semgrep         (bloquant si règle déclenchée)
   └── sca-pip-audit        (bloquant si CVE connue dans requirements.txt)
```

| Job | Rôle | Bloquant | Artefact |
|---|---|---|---|
| `tests` | Tests unitaires et d'interface, rapport de couverture | Oui | `rapport-tests` (junit.xml, coverage.xml) |
| `sast-bandit` | Analyse statique de sécurité Python | Oui (gravité moyenne ou élevée) | `rapport-bandit` (HTML + texte) |
| `sast-semgrep` | Analyse statique (règles Python et détection de secrets) | Oui | `rapport-semgrep` (JSON) |
| `sca-pip-audit` | Vulnérabilités connues des dépendances | Oui | `rapport-pip-audit` (Markdown) |
| `sonarqube` | Qualité, code smells, hotspots de sécurité, couverture | Selon la Quality Gate | Tableau de bord SonarCloud |
| `dast-zap` | Scan dynamique de l'application en fonctionnement | Non (`fail_action: false`) | `rapport-zap` (HTML, JSON, Markdown) |

Bonnes pratiques appliquées :
- jeton `GITHUB_TOKEN` en lecture seule (`permissions: contents: read`) ;
- aucun secret dans le code : le jeton SonarQube est un secret GitHub ;
- versions des outils épinglées ;
- rapports conservés en artefacts même en cas d'échec (`if: always()`).

## Activer SonarQube Cloud

1. Se connecter sur https://sonarcloud.io avec le compte GitHub.
2. Cliquer sur **+** → **Analyze new project**, puis sélectionner le dépôt.
3. Choisir **With GitHub Actions** comme méthode d'analyse.
4. Désactiver l'**Automatic Analysis** dans **Administration → Analysis Method** (sinon l'analyse CI est refusée).
5. Copier le jeton généré, puis dans GitHub aller dans **Settings → Secrets and variables → Actions → New repository secret** : nom `SONAR_TOKEN`, valeur = le jeton.
6. Remplacer `REMPLACER_PAR_ORGANISATION` et `REMPLACER_PAR_CLE_PROJET` dans `sonar-project.properties` par les valeurs affichées sur SonarCloud.
7. Pousser un commit : le job `sonarqube` doit passer au vert et le tableau de bord SonarCloud se remplir.

Sans le secret `SONAR_TOKEN`, le job affiche un avertissement et ne bloque pas le pipeline.

## Récupérer les rapports dans le dépôt

1. Ouvrir l'onglet **Actions**, puis la dernière exécution de **CI-DevSecOps**.
2. Télécharger les artefacts en bas de la page (`rapport-zap`, `rapport-semgrep`, `rapport-bandit`, `rapport-pip-audit`, `rapport-tests`).
3. Décompresser chaque archive dans `reports/apres/<outil>/`.
4. Committer les rapports, puis compléter le § 5 de `docs/analyse-securite.md`.

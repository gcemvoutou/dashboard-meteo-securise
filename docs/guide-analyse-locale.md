# Procédure — analyse de sécurité en local

Prérequis : Python 3.12+, Docker Desktop (pour ZAP et SonarQube), application installée (voir README).

## 1. Lancer l'application

1. Activer l'environnement virtuel.
2. Lancer `streamlit run app.py`.
3. Vérifier que `http://localhost:8501/_stcore/health` affiche `ok`.

## 2. Analyse statique et dépendances (sans Docker)

1. Installer les outils : `pip install -r requirements-dev.txt`.
2. Lancer Bandit :
   ```
   bandit -c pyproject.toml -r src app.py -f html -o reports/apres/bandit.html
   ```
3. Lancer pip-audit :
   ```
   pip-audit -r requirements.txt -f markdown -o reports/apres/pip-audit.md
   ```
4. Pour comparer avec le code d'origine, relancer Bandit sur le dossier `original` :
   ```
   bandit -r original -f html -o reports/avant/bandit.html
   ```

Le résultat attendu est « No issues identified » et « No known vulnerabilities found ».

## 3. OWASP ZAP (DAST)

1. Laisser l'application tourner (étape 1).
2. Depuis la racine du projet, lancer le scan baseline :
   - PowerShell :
     ```
     docker run --rm -v "${PWD}/reports/apres:/zap/wrk:rw" -t ghcr.io/zaproxy/zaproxy:stable zap-baseline.py -t http://host.docker.internal:8501 -r zap-report.html -J zap-report.json
     ```
   - Linux / macOS :
     ```
     docker run --rm --network host -v "$(pwd)/reports/apres:/zap/wrk:rw" -t ghcr.io/zaproxy/zaproxy:stable zap-baseline.py -t http://localhost:8501 -r zap-report.html -J zap-report.json
     ```
3. Ouvrir `reports/apres/zap-report.html`.
4. Reporter chaque alerte dans le § 5 de `docs/analyse-securite.md`.

Pour la comparaison « avant », lancer le code d'origine (`streamlit run original/dashboard_meteo_qualite_air_boilerplate.py`), refaire le scan avec `-r zap-report-avant.html` et ranger le fichier dans `reports/avant/`.

Avec ZAP Desktop (interface graphique) : choisir **Automated Scan**, saisir `http://localhost:8501`, cliquer sur **Attack**, puis **Report → Generate Report**.

## 4. SonarQube (serveur local)

1. Démarrer le serveur :
   ```
   docker run -d --name sonarqube -p 9000:9000 sonarqube:community
   ```
2. Ouvrir `http://localhost:9000` (identifiants initiaux `admin` / `admin`, puis changer le mot de passe).
3. Cliquer sur **Create a local project**, clé `dashboard-meteo`, puis **Locally** et générer un jeton.
4. Générer le rapport de couverture :
   ```
   python -m pytest --cov=src --cov-report=xml:reports/tests/coverage.xml
   ```
5. Lancer l'analyse depuis la racine du projet (PowerShell) :
   ```
   docker run --rm -e SONAR_HOST_URL=http://host.docker.internal:9000 -e SONAR_TOKEN=<jeton> -v "${PWD}:/usr/src" sonarsource/sonar-scanner-cli -Dsonar.projectKey=dashboard-meteo
   ```
6. Consulter les onglets **Issues** et **Security Hotspots** du projet.
7. Exporter les problèmes en JSON pour le rendu :
   ```
   curl -u <jeton>: "http://localhost:9000/api/issues/search?componentKeys=dashboard-meteo&ps=500" -o reports/apres/sonarqube-issues.json
   ```

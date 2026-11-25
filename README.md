# 🌤️ Dashboard Météo & Qualité de l'Air — version sécurisée

Application Streamlit de suivi météo et qualité de l'air pour 5 villes (Paris, Lyon, Marseille, Londres, Madrid), réalisée selon le cahier des charges fourni (fonctionnalités obligatoires uniquement), complétée par une **authentification**, une **analyse de sécurité** et un **pipeline CI/CD DevSecOps**.

> Réalisé par : Clara EMVOUTOU (travail individuel)

## Fonctionnalités

- **Données** (API Open-Meteo, sans clé) : température actuelle, ressentie, min/max du jour, humidité, pression, vent (vitesse et direction), couverture nuageuse, précipitations ; AQI (US), PM2.5, PM10, NO2, O3, CO, SO2. Historique 7 jours + prévisions 2 jours.
- **Cache SQLite** avec TTL (30 min par défaut) et validation des données relues.
- **Traitements** : moyenne / médiane / min / max sur une fenêtre de N heures, tendances 24 h et 7 jours, score composite de confort (ressentie, humidité, PM2.5, NO2).
- **Alertes** : seuils OMS 2021 (vigilance) et seuils réglementaires européens (danger) pour PM2.5, PM10, NO2, O3, plus alerte canicule.
- **Interface** : sélection de la ville, de la période et des métriques ; cartes KPI ; graphiques temporels Plotly ; carte interactive des 5 villes colorée selon l'AQI.
- **Mode déconnecté** (présent dans le code fourni) : données simulées, toujours signalées par un bandeau.
- **Authentification** : comptes en base SQLite, mots de passe hachés bcrypt, verrouillage anti-force brute, expiration de session.

## Architecture

```
├── app.py                    # Point d'entrée Streamlit
├── src/
│   ├── config.py             # Configuration (.env), villes, seuils
│   ├── api_client.py         # Requêtes API, validation, cache SQLite TTL
│   ├── data_processing.py    # Nettoyage pandas, statistiques, tendances, score
│   ├── alerts.py             # Moteur d'alertes
│   ├── auth.py               # Comptes, bcrypt, verrouillage, journalisation
│   ├── manage_users.py       # Gestion des comptes en ligne de commande
│   └── dashboard.py          # Interface (login + dashboard)
├── tests/                    # pytest (API, traitements, alertes, auth, interface)
├── .streamlit/config.toml    # Configuration Streamlit durcie
├── .github/workflows/ci.yml  # Pipeline CI/CD
├── sonar-project.properties  # Configuration SonarQube
├── requirements*.txt / *.lock # Dépendances (épinglées / verrouillées avec empreintes)
├── reports/                  # Rapports de tests et d'analyses (avant / après)
├── docs/                     # Analyse de sécurité, CI/CD, procédure locale
└── original/                 # Code fourni, conservé pour la comparaison avant/après
```

Séparation stricte : récupération des données (`api_client`) / logique métier (`data_processing`, `alerts`) / affichage (`dashboard`).

## Installation et lancement

1. Cloner le dépôt puis créer l'environnement virtuel :
   ```
   python -m venv .venv
   .venv\Scripts\activate          # Windows
   source .venv/bin/activate       # Linux / macOS
   pip install -r requirements.txt
   ```
2. Copier `.env.example` en `.env` (valeurs par défaut utilisables telles quelles).
3. Créer un compte (aucun compte n'est livré par défaut) :
   ```
   python -m src.manage_users add alice
   ```
   Le mot de passe doit faire au moins 12 caractères avec majuscule, minuscule, chiffre et caractère spécial.
4. Lancer l'application :
   ```
   streamlit run app.py
   ```
5. Ouvrir http://127.0.0.1:8501 (ou http://localhost:8501) et se connecter. L'application n'écoute que sur le PC local.

Autres commandes : `python -m src.manage_users list`, `unlock <identifiant>` (après verrouillage), `delete <identifiant>`.

## Tests

```
pip install -r requirements-dev.txt
python -m pytest --cov=src
```

44 tests, couverture 94 % (rapports dans `reports/tests/`).

## Sécurité

- Analyse complète, vulnérabilités et correctifs : [`docs/analyse-securite.md`](docs/analyse-securite.md)
- Procédure d'analyse en local (Bandit, pip-audit, ZAP, SonarQube) : [`docs/guide-analyse-locale.md`](docs/guide-analyse-locale.md)
- Pipeline CI/CD et activation de SonarQube : [`docs/ci-cd.md`](docs/ci-cd.md)

Résumé : 18 vulnérabilités ou faiblesses identifiées — 15 dans le code fourni (absence d'authentification, traces techniques affichées, dépendances non épinglées, fausses données présentées comme réelles, application exposée sur le réseau, etc.) et 3 dans le pipeline CI/CD, détectées par SonarQube (actions non épinglées par SHA, dépendances non verrouillées). 17 corrigées, 1 résiduelle (en-têtes HTTP de sécurité, confirmée par OWASP ZAP, à traiter par un reverse proxy).

## CI/CD

Chaque push lance : tests pytest → Bandit → Semgrep → pip-audit → SonarQube Cloud → scan OWASP ZAP de l'application démarrée. Les rapports sont disponibles en artefacts dans l'onglet **Actions**, et l'analyse SonarQube sur https://sonarcloud.io/project/overview?id=gcemvoutou_dashboard-meteo-securise.

Le pipeline est lui-même durci : actions épinglées par empreinte SHA, dépendances installées depuis des fichiers verrouillés (`requirements.lock`, `requirements-ci.lock`) avec vérification des empreintes.

## Variables d'environnement (`.env`)

| Variable | Défaut | Rôle |
|---|---|---|
| `APP_DATA_DIR` | `./data` | Dossier du cache, des comptes et des journaux |
| `CACHE_TTL_MINUTES` | 30 | Durée de validité du cache |
| `HTTP_TIMEOUT_SECONDS` | 5 | Délai maximal des appels API |
| `SESSION_TIMEOUT_MINUTES` | 30 | Déconnexion après inactivité |
| `MAX_LOGIN_ATTEMPTS` | 5 | Échecs avant verrouillage |
| `LOCKOUT_MINUTES` | 15 | Durée du verrouillage |
| `BCRYPT_ROUNDS` | 12 | Coût du hachage |

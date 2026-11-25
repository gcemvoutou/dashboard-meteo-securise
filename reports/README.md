# Rapports

| Fichier | Contenu | Outil |
|---|---|---|
| `avant/bandit.txt`, `avant/bandit.json` | Analyse statique du code fourni (`original/`) | Bandit 1.9.4 |
| `avant/zap-local.html` | Scan dynamique du code fourni (port 8502) | OWASP ZAP 2.17.0 |
| `apres/bandit.txt`, `apres/bandit.json` | Analyse statique du code corrigé (`src/`, `app.py`) | Bandit 1.9.4 |
| `apres/pip-audit.txt` | Vulnérabilités connues des dépendances épinglées | pip-audit 2.10.1 |
| `apres/zap-local.html` | Scan dynamique de la version corrigée (port 8501) | OWASP ZAP 2.17.0 |
| `tests/junit.xml`, `tests/coverage.xml`, `tests/pytest-resume.txt` | 44 tests, couverture 94 % | pytest, pytest-cov |

Analyses exécutées en local le 25/11/2026. Les rapports Semgrep, SonarQube et ZAP produits par la CI sont disponibles dans l'onglet **Actions** du dépôt (artefacts) et synthétisés dans `docs/analyse-securite.md` § 5.

Interprétation de l'ensemble : `docs/analyse-securite.md`.

# Analyse de sécurité — vulnérabilités identifiées et correctifs

## 1. Périmètre et méthode

- **Code analysé « avant »** : `original/dashboard_meteo_qualite_air_boilerplate.py` (code fourni).
- **Code analysé « après »** : `app.py` + `src/` (application restructurée, avec authentification).
- **Référentiel de classement** : OWASP Top 10:2025.
- **Outils** :

| Type | Outil | Où | Rapports |
|---|---|---|---|
| SAST | Bandit 1.9.4 | local + CI | `reports/avant/bandit.*`, `reports/apres/bandit.*` |
| SAST | Semgrep (règles `p/python`, `p/secrets`) | CI | artefact `rapport-semgrep` |
| SCA | pip-audit 2.10.1 | local + CI | `reports/avant/pip-audit.md`, `reports/apres/pip-audit.md` |
| Qualité / SAST | SonarQube Cloud | CI | tableau de bord SonarCloud |
| DAST | OWASP ZAP (baseline) | CI ou local | artefact `rapport-zap` |
| Tests | pytest + pytest-cov | local + CI | `reports/tests/` |
| Revue manuelle | lecture du code et de la configuration Streamlit | — | ce document |

## 2. Résultats des outils automatiques

| Outil | Avant | Après |
|---|---|---|
| Bandit | 0 problème (298 lignes) | 0 problème (964 lignes) |
| pip-audit | 0 CVE connue, mais **dépendances non épinglées** (pas de `requirements.txt`) | 0 CVE connue, versions épinglées |
| pytest | 2 tests, dans le fichier de production | 44 tests, couverture 94 % |
| Semgrep / SonarQube / ZAP | voir § 5 (exécutés dans la CI) | voir § 5 |

**Constat important** : Bandit ne détecte rien sur le code d'origine alors qu'il contient une faille majeure (aucune authentification). Un SAST repère des motifs dangereux dans le code (`eval`, `subprocess`, mots de passe en dur…), pas les défauts de conception. La revue manuelle et le DAST restent indispensables.

## 3. Vulnérabilités identifiées et correctifs

| ID | Vulnérabilité | OWASP 2025 | Gravité | Détection | Correctif | Vérification |
|---|---|---|---|---|---|---|
| V01 | **Aucune authentification** : n'importe qui accédant au port 8501 voit le dashboard | A01 / A07 | Élevée | Revue manuelle (non détectée par Bandit) | Page de connexion obligatoire (`src/auth.py`, `require_login()`) | `test_dashboard_hidden_without_login` |
| V02 | **Traces Python affichées dans le navigateur** (`client.showErrorDetails` vaut `full` par défaut) : chemins, code source | A02 / A10 | Moyenne | Revue de la configuration Streamlit | `showErrorDetails = "none"` + `try/except` final avec message générique et trace dans le journal serveur | Lecture de `.streamlit/config.toml` |
| V03 | **Dépendances non épinglées** (`pip install streamlit requests…`) : installation non reproductible, risque de récupérer une version compromise | A03 | Moyenne | pip-audit + revue | `requirements.txt` épinglé, pip-audit bloquant dans la CI | Job `sca-pip-audit` |
| V04 | **Repli silencieux sur des données aléatoires** si l'API échoue : l'utilisateur voit de fausses mesures et de fausses alertes sanitaires comme si elles étaient réelles (« fail-open ») | A06 / A10 | Moyenne | Revue manuelle | `FetchResult.source` + bandeau « Données simulées » explicite | `test_network_error_falls_back_to_flagged_mock`, `test_login_then_dashboard_in_mock_mode` |
| V05 | **Indicateurs et alertes calculés sur une prévision** : `df.iloc[-1]` est la dernière heure de prévision, pas l'heure actuelle | A06 | Moyenne | Revue manuelle | Utilisation du bloc `current` de l'API ; historique filtré `≤ maintenant` | `test_history_excludes_forecast` |
| V06 | **Contenu du cache non validé** : une entrée modifiée dans `data_cache.db` est affichée telle quelle | A08 | Faible | Revue manuelle | Validation du schéma à la lecture, suppression des entrées invalides | `test_tampered_cache_entry_is_ignored` |
| V07 | **Réponses API non validées** : une réponse d'erreur Open-Meteo (`{"error": true}`) ou incomplète fait planter l'application | A10 | Faible | Revue manuelle | `validate_payload()` + exception `APIResponseError` gérée | `test_api_error_payload_is_rejected`, `test_corrupted_json_is_handled` |
| V08 | **URL construites par concaténation** (f-string) : injection de paramètres possible si les coordonnées venaient de l'utilisateur | A05 | Faible | Revue manuelle | Paramètres passés via `params=` (encodés par requests) + bornes lat/lon | `test_params_are_passed_separately_with_timeout`, `test_invalid_coordinates_rejected` |
| V09 | **Connexions SQLite jamais fermées** : `with sqlite3.connect()` valide la transaction mais ne ferme pas la connexion → épuisement des descripteurs (déni de service) | A10 | Faible | pytest (`ResourceWarning`) | Gestionnaire de contexte qui ferme toujours la connexion | `pytest -W error::ResourceWarning` |
| V10 | **Aucune journalisation des événements de sécurité** | A09 | Moyenne | Revue manuelle | Journal `auth` : connexions, échecs, verrouillages, déconnexions ; fichier `data/app.log` ; neutralisation des retours à la ligne (CWE-117) | `test_log_injection_neutralised` |
| V11 | **Base de cache dans le dossier courant**, risque de la committer | A02 | Faible | Revue manuelle | Dossier `data/` dédié, exclu par `.gitignore` avec `.env` et `*.db` | Lecture de `.gitignore` |
| V12 | **Télémétrie Streamlit active par défaut** (`gatherUsageStats`) | A02 | Faible | Documentation Streamlit | `gatherUsageStats = false` | `.streamlit/config.toml` |
| V13 | **Aucun filtrage de l'en-tête Host** (DNS rebinding) et API « agent » expérimentale non verrouillée | A02 | Faible | Documentation Streamlit (`streamlit config show`) | `allowedHosts`, `enableAgentApi = false`, cookie XSRF `SameSite=strict` | `.streamlit/config.toml` |
| V14 | **En-têtes de sécurité HTTP absents** : pas de `Content-Security-Policy`, `X-Frame-Options`, `X-Content-Type-Options`, `Strict-Transport-Security` ; en-tête `server: uvicorn` exposé | A02 | Moyenne | `curl -I http://localhost:8501/` (constaté), à confirmer avec ZAP | **Résiduelle** : Streamlit ne permet pas d'ajouter ces en-têtes → reverse proxy (§ 6) | Rapport ZAP |

Note sur V13 : la page HTML statique reste servie quel que soit l'en-tête Host (vérifié avec `curl -H "Host: evil.com"`). D'après la documentation de Streamlit, la liste `allowedHosts` s'applique au WebSocket, par lequel transitent toutes les données de l'application.

## 4. Sécurité de l'authentification ajoutée

| Risque | Mesure | Test |
|---|---|---|
| Mots de passe lisibles en base | Hachage **bcrypt** (coût 12, sel aléatoire) | `test_password_is_hashed` |
| Mots de passe faibles | 12 caractères min., majuscule, minuscule, chiffre, caractère spécial (recommandations CNIL) ; 72 octets max. (limite bcrypt) | `test_password_policy_rejects_weak` |
| Compte par défaut / mot de passe en dur | Aucun compte livré : création en ligne de commande avec saisie masquée (`getpass`) | `test_add_list_unlock_delete` |
| Force brute | Verrouillage après 5 échecs pendant 15 min, **stocké en base** (un compteur en `session_state` serait remis à zéro par un simple rafraîchissement de la page) | `test_lockout_after_max_attempts` |
| Énumération des comptes | Même message pour « compte inconnu » et « mauvais mot de passe » ; hash factice vérifié pour un temps de réponse identique ; verrouillage appliqué aussi aux identifiants inexistants | `test_same_message_for_unknown_user_and_wrong_password` |
| Injection SQL | Requêtes paramétrées (`?`) partout | `test_sql_injection_attempt_fails` |
| Injection dans l'affichage / les journaux | Identifiant limité à `[A-Za-z0-9_.-]{3,32}` ; retours à la ligne neutralisés dans les logs | `test_invalid_username_rejected`, `test_log_injection_neutralised` |
| Session abandonnée | Expiration après 30 min d'inactivité, bouton de déconnexion qui vide la session | `test_logout` |
| Réutilisation d'état | Session vidée puis recréée à la connexion | — |

Paramètres réglables dans `.env` : `SESSION_TIMEOUT_MINUTES`, `MAX_LOGIN_ATTEMPTS`, `LOCKOUT_MINUTES`, `BCRYPT_ROUNDS`.

## 5. Résultats SonarQube, Semgrep et ZAP

Ces trois outils n'ont pas pu être exécutés dans l'environnement de préparation (registre Semgrep, Docker et SonarCloud inaccessibles). Ils sont exécutés par le pipeline (`.github/workflows/ci.yml`). Après le premier passage de la CI :

1. Télécharger les artefacts `rapport-zap` et `rapport-semgrep` depuis l'onglet **Actions** du dépôt.
2. Les copier dans `reports/apres/zap/` et `reports/apres/semgrep/`.
3. Compléter le tableau ci-dessous.

| Outil | Alerte / règle | Gravité | Lien avec le tableau § 3 | Décision (corrigé / accepté / faux positif) |
|---|---|---|---|---|
| ZAP | Content Security Policy (CSP) Header Not Set *(attendu)* | Moyenne | V14 | Accepté en local, corrigé par le reverse proxy en production |
| ZAP | Missing Anti-clickjacking Header *(attendu)* | Moyenne | V14 | Idem |
| ZAP | X-Content-Type-Options Header Missing *(attendu)* | Faible | V14 | Idem |
| ZAP | Server Leaks Version Information / en-tête Server *(possible)* | Faible | V14 | Idem |
| SonarQube | *à compléter* | | | |
| Semgrep | *à compléter* | | | |

Limite du scan ZAP : Streamlit affiche toute l'interface via un WebSocket. Le spider de ZAP ne voit donc que la page HTML initiale et les fichiers statiques ; il contrôle surtout les en-têtes et les cookies, pas la logique de connexion. La logique de connexion est couverte par les tests `tests/test_auth.py` et `tests/test_dashboard.py`.

## 6. Risques résiduels et recommandations

| Risque résiduel | Recommandation |
|---|---|
| En-têtes HTTP de sécurité absents (V14) | Placer l'application derrière un reverse proxy, configuration ci-dessous |
| Trafic en clair (HTTP) | Terminer le TLS sur le reverse proxy (certificat Let's Encrypt ou interne) |
| Verrouillage par identifiant : un attaquant peut bloquer volontairement le compte d'un autre utilisateur | Compromis assumé ; en production, compléter par une limitation par adresse IP au niveau du proxy (`limit_req` nginx) |
| Session perdue au rafraîchissement de la page | Comportement de Streamlit (session liée au WebSocket) ; sans impact sur la sécurité |
| Pas d'authentification multifacteur ni de rôles | Hors périmètre du TP (pas d'ajout de fonctionnalités) |
| Actions GitHub référencées par tag (`@v6`) | Épingler par empreinte SHA pour se protéger d'une action compromise |

Exemple de configuration nginx (reverse proxy devant Streamlit) :

```nginx
server {
    listen 443 ssl;
    server_name dashboard.example.fr;
    ssl_certificate     /etc/ssl/certs/dashboard.crt;
    ssl_certificate_key /etc/ssl/private/dashboard.key;
    server_tokens off;

    add_header Content-Security-Policy "default-src 'self'; script-src 'self' 'unsafe-inline' 'unsafe-eval'; style-src 'self' 'unsafe-inline'; img-src 'self' data: https://*.tile.openstreetmap.org; connect-src 'self' wss://dashboard.example.fr https://*.tile.openstreetmap.org; frame-ancestors 'none'" always;
    add_header X-Frame-Options "DENY" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header Referrer-Policy "strict-origin-when-cross-origin" always;
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
    proxy_hide_header server;

    location / {
        proxy_pass http://127.0.0.1:8501;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;     # WebSocket Streamlit
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
    }
}
```

Avec ce proxy, ajouter `dashboard.example.fr` dans `allowedHosts` de `.streamlit/config.toml`. Les directives `unsafe-inline` / `unsafe-eval` sont nécessaires au fonctionnement de Streamlit et de Plotly ; les vérifier avec la console du navigateur après mise en place.

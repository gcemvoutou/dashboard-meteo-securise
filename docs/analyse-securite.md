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
| SCA | pip-audit 2.10.1 | local + CI | `reports/apres/pip-audit.txt` |
| Qualité / SAST | SonarQube Cloud (Quality Gate « Sonar way ») | CI | https://sonarcloud.io/project/overview?id=gcemvoutou_dashboard-meteo-securise |
| DAST | OWASP ZAP 2.17.0 (Automated Scan, Dev Standard) | local + CI | `reports/avant/zap-local.html`, `reports/apres/zap-local.html`, artefact `rapport-zap` |
| Tests | pytest + pytest-cov | local + CI | `reports/tests/` |
| Revue manuelle | lecture du code et de la configuration Streamlit | — | ce document |

## 2. Résultats des outils automatiques

| Outil | Avant | Après |
|---|---|---|
| Bandit | 0 problème (298 lignes) | 0 problème (964 lignes) |
| pip-audit | 0 CVE connue, mais **dépendances non épinglées** (pas de `requirements.txt`) | 0 CVE connue, versions épinglées |
| pytest | 2 tests, dans le fichier de production | 44 tests, couverture 94 % |
| OWASP ZAP (local) | 0 élevée, 2 moyennes, 3 faibles, 1 info | 0 élevée, 2 moyennes, 4 faibles (dont 1 hors périmètre), 1 info |
| SonarQube Cloud | — | 11 problèmes à la 1re analyse (10 dans le pipeline CI, 1 dans le code), tous corrigés : voir § 5.3 |
| Semgrep (`p/python`, `p/secrets`) | — | 0 résultat (job bloquant `--error` réussi) |

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
| V15 | **Application joignable depuis tout le réseau** : Streamlit écoute sur toutes les interfaces (`:::8501`, « Network URL : http://192.168.0.100:8501 » au démarrage) ; tout appareil du même réseau (Wi-Fi de l'école) peut l'atteindre | A02 | Moyenne | Lecture du journal de démarrage | `server.address = "127.0.0.1"` : écoute sur la boucle locale uniquement ; en production seul le reverse proxy est exposé | Journal de démarrage : `Uvicorn server started on 127.0.0.1` |
| V16 | **Actions GitHub référencées par étiquette** (`@v6`, `@v0.14.0`) : une étiquette peut être déplacée vers du code malveillant si le dépôt de l'action est compromis ; le pipeline, qui manipule le jeton SonarQube, l'exécuterait | A03 / A08 | Élevée | SonarQube (« Use full commit SHA hash for this dependency ») | Chaque action épinglée par l'empreinte SHA complète du commit, version en commentaire ; actions mises à jour (supprime aussi l'avertissement « Node.js 20 is deprecated ») | `.github/workflows/ci.yml` |
| V17 | **Installation des dépendances CI non verrouillée** : seules les dépendances directes étaient épinglées, sans empreinte ; `semgrep` sans version ; `pip` autorisé à exécuter les scripts `setup.py` de paquets sources | A03 | Moyenne | SonarQube (« Using dependencies without locking resolved versions », « Omitting --only-binary :all: ») | Fichiers verrouillés `requirements.lock` / `requirements-ci.lock` (toutes les dépendances, transitives comprises, avec empreintes SHA-256, générés par `uv pip compile --generate-hashes`) ; installation `--require-hashes --only-binary :all:` | Pipeline vert, installation stricte testée |
| V18 | **Générateur aléatoire sans graine** pour les données simulées : résultats non reproductibles | — (qualité) | Faible | SonarQube (« Provide a seed for this random generator ») | Graine explicite dérivée des coordonnées et de l'heure | `src/api_client.py` |
| V14 | **En-têtes de sécurité HTTP absents** : pas de `Content-Security-Policy`, `X-Frame-Options`, `X-Content-Type-Options`, `Strict-Transport-Security` ; en-tête `server: uvicorn` exposé | A02 | Moyenne | `curl -I` puis **confirmé par OWASP ZAP** (§ 5.1) | **Résiduelle** : Streamlit ne permet pas d'ajouter ces en-têtes → reverse proxy (§ 6) | `reports/apres/zap-local.html` |

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

## 5. Résultats des scans dynamiques (OWASP ZAP) et des outils de la CI

### 5.1 OWASP ZAP en local

Conditions : ZAP 2.17.0, *Automated Scan*, politique *Dev Standard*, araignée traditionnelle + *Client Spider* (Firefox headless). Code d'origine lancé sur le port 8502, version corrigée sur le port 8501, le 25/11/2026.

| Alerte ZAP | Risque | Avant (8502) | Après (8501) | Analyse | Décision |
|---|---|---|---|---|---|
| Content Security Policy (CSP) Header Not Set | Moyen | 4 | 4 | Aucune politique ne limite les sources de scripts (protection XSS réduite) | **V14** — résiduelle, corrigée par le reverse proxy (§ 6) |
| Missing Anti-clickjacking Header | Moyen | 4 | 4 | Page intégrable dans une `<iframe>` tierce (clickjacking) | **V14** — `X-Frame-Options: DENY` / `frame-ancestors 'none'` sur le proxy |
| X-Content-Type-Options Header Missing | Faible | systémique | systémique | Le navigateur peut deviner le type MIME des fichiers | **V14** — `nosniff` sur le proxy |
| Cookie No HttpOnly Flag (`_streamlit_xsrf`) | Faible | 1 | 1 | Cookie du jeton anti-CSRF : il **doit** être lisible en JavaScript pour être recopié dans les requêtes (double-submit cookie) | **Faux positif** |
| Timestamp Disclosure – Unix | Faible | systémique | systémique | Horodatage contenu dans le jeton XSRF et nombres dans les fichiers JS de Streamlit ; aucune donnée sensible | **Faux positif** |
| Strict-Transport-Security Header Not Set | Faible | — | 1 | Concerne `download.mozilla.org` : trafic de mise à jour de Firefox intercepté pendant le scan, pas l'application | **Hors périmètre** (HSTS prévu sur le proxy HTTPS) |
| Modern Web Application | Info | 4 | 4 | Application détectée comme JavaScript | Information |

**Interprétation.** Les résultats sont identiques avant et après correction, alors que le code d'origine n'a ni authentification, ni validation, ni masquage des erreurs. En mode automatisé, ZAP teste la couche HTTP (en-têtes, cookies, fichiers statiques), fournie par le serveur Streamlit et identique dans les deux versions. La logique applicative passe par un WebSocket, non attaqué dans ce mode. Le *Client Spider* a d'ailleurs exploré librement le contenu du dashboard d'origine (`#dashboard-meteo-and-surveillance-qualite-de-l-air`), alors qu'il n'a vu que la page de connexion sur la version corrigée : ZAP **subit** l'absence d'authentification sans la **signaler**. Les correctifs V01 à V13 et V15 sont donc démontrés par la revue de code, les tests pytest et les constats manuels ci-dessous, pas par le DAST.

### 5.2 Constat manuel sur le code d'origine (preuve de V02, V05 et V07)

Au lancement du code d'origine avec des données réelles, l'application plante :

```
File "original\dashboard_meteo_qualite_air_boilerplate.py", line 300, in render_dashboard
    col3.metric("Indice AQI (US)", f"{int(latest['us_aqi'])}")
ValueError: cannot convert float NaN to integer
```

- **V05** : `latest = df.iloc[-1]` est la dernière heure de **prévision**, pour laquelle l'API ne fournit pas d'AQI (`NaN`). La température affichée (3,2 °C) était une prévision ; la valeur réelle au même moment était 4,3 °C (version corrigée).
- **V07** : une valeur absente dans la réponse API fait planter l'application, faute de validation.
- **V02** : dans le navigateur, le message est masqué (« The original error message is redacted… ») uniquement parce que la configuration durcie `.streamlit/config.toml` du dépôt s'applique aussi au code d'origine lancé depuis ce dossier. Sans elle (comportement par défaut de Streamlit), cette trace, avec les chemins `C:\Projets\...` et le code source, s'afficherait à tout visiteur.

### 5.3 SonarQube Cloud et Semgrep (CI)

**Semgrep** (règles `p/python` et `p/secrets`) : aucun résultat sur `src/` et `app.py`. Le job est configuré avec `--error` (échec au moindre résultat) et a réussi.

**SonarQube Cloud** : 11 problèmes à la première analyse, tous de sécurité sauf un. Ils ne portaient pas sur l'application mais sur **la chaîne CI/CD elle-même** — un pipeline est aussi une cible (attaques de la chaîne d'approvisionnement).

| Règle SonarQube | Gravité | Nb | Emplacement | Analyse | Décision |
|---|---|---|---|---|---|
| Use full commit SHA hash for this dependency | High | 2 | `ci.yml` (actions SonarQube et ZAP) | Une action tierce référencée par étiquette peut être remplacée à l'insu du projet | **Corrigé** (V16) : épinglage par SHA de toutes les actions |
| Omitting "--only-binary :all:" can lead to the execution of setup scripts | Medium | 5 | `ci.yml` (`pip install`) | Un paquet source exécute son `setup.py` à l'installation, donc du code arbitraire dans le pipeline | **Corrigé** (V17) : `--only-binary :all:` |
| Using dependencies without locking resolved versions is security-sensitive | Medium | 3 | `ci.yml` (`pip install -r …`) | Les dépendances transitives pouvaient changer d'une exécution à l'autre | **Corrigé** (V17) : fichiers `.lock` avec empreintes + `--require-hashes` |
| Provide a seed for this random generator | Low | 1 | `src/api_client.py` | Données simulées non reproductibles ; aucun usage cryptographique | **Corrigé** (V18) |

Première analyse réalisée en mode *Automatic Analysis* (sans couverture) ; cette méthode a ensuite été désactivée au profit de l'analyse par le pipeline, qui importe la couverture des tests (`reports/tests/coverage.xml`).

**Leçon** : Bandit et Semgrep n'analysent que le code Python ; SonarQube a aussi examiné la définition du pipeline et y a trouvé les faiblesses les plus graves du dépôt. La sécurité d'un projet inclut celle de sa chaîne de construction.

## 6. Risques résiduels et recommandations

| Risque résiduel | Recommandation |
|---|---|
| En-têtes HTTP de sécurité absents (V14) | Placer l'application derrière un reverse proxy, configuration ci-dessous |
| Trafic en clair (HTTP) | Terminer le TLS sur le reverse proxy (certificat Let's Encrypt ou interne) |
| Verrouillage par identifiant : un attaquant peut bloquer volontairement le compte d'un autre utilisateur | Compromis assumé ; en production, compléter par une limitation par adresse IP au niveau du proxy (`limit_req` nginx) |
| Session perdue au rafraîchissement de la page | Comportement de Streamlit (session liée au WebSocket) ; sans impact sur la sécurité |
| Pas d'authentification multifacteur ni de rôles | Hors périmètre du TP (pas d'ajout de fonctionnalités) |

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

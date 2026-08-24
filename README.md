# Garmin to Strava Sync 🏃‍♂️🚴‍♀️

Application Python moderne et complète pour synchroniser vos activités sportives depuis votre compte **Garmin Connect** et les pousser **individuellement** ou par sélection vers votre profil **Strava** via l'API officielle Strava.

Prête pour un déploiement public ou en réseau local avec un **système de comptes multi-utilisateurs**.

---

## ✨ Fonctionnalités

- 👥 **Système Multi-Utilisateurs & Gestion de Comptes** :
  - Inscription (`/register`) et Connexion (`/login`) individuelles avec mots de passe hachés de manière ultra-sécurisée (PBKDF2-HMAC-SHA256).
  - Sessions signées par cookies `HttpOnly`.
  - Isolation totale et étanche des activités, sessions Garmin et tokens Strava entre chaque utilisateur.
- ⚡ **Partage d'API Strava Facilité** : L'administrateur configure l'application Strava une seule fois, et tous les utilisateurs peuvent lier leur compte personnel en 1 clic grâce à OAuth2 !
- 🖥️ **Interface Web Moderne & Réactive** : Tableau de bord sombre inspiré des applications de sport avec Tailwind CSS et icônes Lucide.
- 🚀 **Push Individuel en un Clic** : Poussez n'importe quelle activité Garmin sur Strava instantanément.
- ⚙️ **Personnalisation avant envoi** : Modifiez le titre, la description, et activez les flags *Trajet Vélotaf* ou *Home Trainer* avant de pousser.
- 📦 **Sélection multiple / Envoi groupé** : Cochez plusieurs activités pour les synchroniser d'un coup vers Strava.
- 🔍 **Filtres et Recherche** : Filtrez par sport (Course, Vélo, Randonnée, Natation, Musculation...), par statut de synchronisation ou par mot-clé.
- 💾 **Historique & Persistance** : Base de données locale SQLite mémorisant le statut de chaque sortie avec lien direct vers l'activité Strava créée.
- 💻 **Mode CLI (Ligne de commande)** : Pour une utilisation en terminal (`python main.py --cli`).

---

## 📋 Prérequis

- **Python 3.10+**
- **PostgreSQL 13+** (base de données de production)
- Un compte **Garmin Connect**
- Un compte **Strava** et une application API Strava gratuite (pour le serveur)

---

## 🚀 Installation

1. **Cloner ou ouvrir le projet** :
   ```bash
   cd garmin-to-strava
   ```

2. **Créer et activer un environnement virtuel (recommandé)** :
   ```bash
   python -m venv venv
   # Sur Windows :
   .\venv\Scripts\activate
   # Sur Linux / macOS :
   source venv/bin/activate
   ```

3. **Installer les dépendances** :
   ```bash
   pip install -r requirements.txt
   ```

---

## 🐘 Configuration PostgreSQL

L'application utilise **PostgreSQL** comme base de données (via `psycopg2`, avec un pool de
connexions). Elle ne stocke plus rien en SQLite.

### 1. Créer un rôle applicatif dédié et sa base

**Ne faites jamais tourner l'application avec le compte superutilisateur** (`postgres`/`root`).
Le script [`sql/01_create_app_user_and_db.sql`](sql/01_create_app_user_and_db.sql) provisionne
tout ce qu'il faut : un rôle dédié `garmin_strava_app` (ni superutilisateur, ni `CREATEDB`, ni
`CREATEROLE`), sa base `garmin_strava` (dont il est propriétaire) et une base `garmin_strava_test`
séparée pour la suite de tests — avec accès `CONNECT` révoqué à `PUBLIC` sur les deux.

1. Ouvrez le fichier et remplacez `CHANGE_ME_STRONG_PASSWORD` par un secret fort
   (ex. `openssl rand -base64 32`).
2. Exécutez-le en tant qu'administrateur PostgreSQL :
   ```bash
   psql "host=<db-host> port=5432 user=postgres dbname=postgres" -f sql/01_create_app_user_and_db.sql
   ```

Le script est idempotent (rejouable sans erreur) et propriétaire de sa base, donc dispose de
tous les droits nécessaires (`CREATE TABLE`, `SELECT`, `INSERT`, `UPDATE`, `DELETE`) uniquement
sur celle-ci — pas d'accès aux autres bases de l'instance.

Pour changer le mot de passe applicatif plus tard sans tout reprovisionner, utilisez
[`sql/02_rotate_app_password.sql`](sql/02_rotate_app_password.sql) (pensez à mettre à jour
`DATABASE_URL` dans `.env` et à redémarrer l'app après rotation).

### 2. Renseigner la connexion dans `.env`

Copiez `.env.example` en `.env` puis complétez soit `DATABASE_URL` (recommandé), soit les
variables `PG*` individuelles :

```env
DATABASE_URL=postgresql://garmin_strava_app:un_mot_de_passe_fort@localhost:5432/garmin_strava
DB_POOL_MIN_CONN=1
DB_POOL_MAX_CONN=10
```

### 3. Initialisation du schéma

Le schéma (tables `users`, `global_settings`, `user_settings`, `activities` + index) est créé
automatiquement au démarrage de l'application (`init_db()` exécuté au lancement du serveur ou
de la CLI) — aucune migration manuelle n'est nécessaire pour un premier déploiement.

---

## ⚡ Accélérer la connexion Garmin (contourner le rate-limit 429)

La librairie `garminconnect` essaie plusieurs stratégies de connexion dans l'ordre
(`mobile+cffi` → `mobile+requests` → `widget+cffi` → `portal+cffi` → `portal+requests`) et
retombe sur la suivante en cas d'échec. Sur de nombreux réseaux, les deux premières
(`mobile+cffi`, `mobile+requests`) sont **systématiquement rate-limitées (HTTP 429)** par
Garmin avant que la connexion n'aboutisse via le widget SSO — ce qui ajoute plusieurs secondes
d'attente à chaque connexion pour rien.

La variable `GARMIN_SKIP_LOGIN_STRATEGIES` (dans `.env`) permet de sauter directement ces
stratégies condamnées à échouer :

```env
GARMIN_SKIP_LOGIN_STRATEGIES=mobile+cffi,mobile+requests
```

C'est la valeur par défaut de l'application. Stratégies valides :
`mobile+cffi`, `mobile+requests`, `widget+cffi`, `portal+cffi`, `portal+requests`.
Laissez la variable vide pour réessayer toutes les stratégies (comportement le plus robuste,
mais le plus lent en cas de rate-limit persistant).

---

## 🔑 Configuration des clés API Strava (Pour le serveur)

1. Rendez-vous sur le portail développeur Strava : [https://www.strava.com/settings/api](https://www.strava.com/settings/api)
2. Créez une application :
   - **Nom de l'application** : `Garmin to Strava Sync`
   - **Catégorie** : `Entraînement`
   - **Site web du club** : `http://localhost:8000` (ou votre URL publique)
   - **Domaine de rappel d'autorisation** : `localhost` (ou votre domaine public)
3. Renseignez votre **Client ID** et **Client Secret** dans le fichier `.env` ou via l'interface d'administration :
   ```env
   STRAVA_CLIENT_ID=123456
   STRAVA_CLIENT_SECRET=votre_client_secret_ici
   ```

---

## 🖥️ Utilisation

### 1. Démarrage du serveur Web

```bash
python main.py
```
Puis ouvrez votre navigateur sur : **[http://localhost:8000](http://localhost:8000)**

1. Créez votre compte sur **Créer un compte** (`/register`) ou connectez-vous (`/login`).
2. Cliquez sur **Connexion Garmin** pour lier votre compte Garmin Connect.
3. Allez dans **Paramètres** (icône ⚙️) et cliquez sur **"Autoriser & Connecter avec Strava"**.
4. Cliquez sur **"Synchroniser Garmin"** pour importer vos dernières sorties.
5. Cliquez sur **"Push Strava"** en face de n'importe quelle activité pour l'envoyer individuellement !

---

### 2. Mode Ligne de Commande (CLI)

```bash
# Vérifier le statut des connexions
python main.py --cli status

# Se connecter à Garmin
python main.py --cli login-garmin

# Récupérer les 20 dernières activités Garmin
python main.py --cli sync --limit 20

# Lister les activités enregistrées
python main.py --cli list --limit 20

# Pousser une activité spécifique sur Strava
python main.py --cli push 1234567890
```

---

## 📁 Structure du Projet

```
garmin-to-strava/
├── app/
│   ├── auth.py                # Gestion des sessions signées, hachage des mots de passe & dépendances FastAPI
│   ├── config.py              # Configuration globale & gestion des chemins
│   ├── database.py            # Accès PostgreSQL multi-utilisateurs (users, user_settings, activities) via pool psycopg2
│   ├── garmin_client.py       # Client Garmin Connect par utilisateur (session persistante, export FIT)
│   ├── strava_client.py       # Client Strava OAuth2 par utilisateur (refresh token, upload FIT)
│   ├── sync_service.py        # Orchestration Garmin -> Strava par utilisateur
│   ├── cli.py                 # Interface CLI multi-utilisateurs
│   └── web/
│       ├── routes.py          # Routes FastAPI protégées, authentification & API
│       ├── templates/
│       │   ├── login.html     # Page de connexion
│       │   ├── register.html  # Page d'inscription
│       │   ├── index.html     # Dashboard principal des activités
│       │   └── settings.html  # Page des paramètres & liaisons de comptes
│       └── static/
│           ├── css/styles.css # Styles personnalisés et animations
│           └── js/app.js      # Logique frontend, push interactif & auth
├── tests/                     # Suite de tests (auth, multi-user isolation, strava, db, sync)
├── main.py                    # Point d'entrée serveur Web / CLI
├── requirements.txt           # Dépendances Python
├── .env.example               # Exemple de variables d'environnement
└── README.md                  # Documentation du projet
```

---

## 🧪 Exécution des Tests

Les tests utilisent une base PostgreSQL dédiée (`garmin_strava_test` par défaut, voir
[Configuration PostgreSQL](#-configuration-postgresql)), nettoyée automatiquement entre chaque
test. Définissez au besoin `TEST_DATABASE_URL` pour pointer vers une autre instance :

```bash
export TEST_DATABASE_URL=postgresql://garmin_strava_app:un_mot_de_passe_fort@localhost:5432/garmin_strava_test
pytest
```

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
│   ├── database.py            # Modèles SQLite multi-utilisateurs (users, user_settings, activities)
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

```bash
pytest
```

import argparse
import getpass
import sys
from typing import Optional

from app.database import (
    create_user,
    get_db_cursor,
    get_user_by_email,
    init_db,
    list_activities,
)
from app.garmin_client import get_user_garmin_service
from app.strava_client import get_user_strava_service
from app.sync_service import get_user_sync_service


def get_or_prompt_user():
    with get_db_cursor() as cursor:
        cursor.execute("SELECT * FROM users ORDER BY id ASC LIMIT 1")
        row = cursor.fetchone()
        if row:
            return dict(row)

    print("\nAucun utilisateur trouvé dans l'application. Créons votre compte CLI :")
    email = input("Email : ").strip()
    password = getpass.getpass("Mot de passe : ")
    return create_user(email, password, display_name=email.split("@")[0])


def print_status(user_id: int):
    print("\n--- STATUT DES CONNEXIONS (Utilisateur ID: {}) ---".format(user_id))
    garmin_srv = get_user_garmin_service(user_id)
    garmin_ok = garmin_srv.is_authenticated() or garmin_srv.init_session()
    print(f"Garmin Connect : {'[CONNECTÉ]' if garmin_ok else '[NON CONNECTÉ]'}")
    if garmin_ok and garmin_srv.email:
        print(f"  Email : {garmin_srv.email}")

    strava_srv = get_user_strava_service(user_id)
    strava_ok = strava_srv.is_authenticated()
    athlete = strava_srv.get_athlete_name()
    print(f"Strava API     : {'[CONNECTÉ]' if strava_ok else '[NON CONNECTÉ]'}")
    if strava_ok and athlete:
        print(f"  Athlète : {athlete}")
    print("--------------------------------------------------\n")


def cmd_login_garmin(user_id: int):
    print(f"Connexion à Garmin Connect pour l'utilisateur ID {user_id}")
    email = input("Email Garmin : ").strip()
    password = getpass.getpass("Mot de passe Garmin : ")

    garmin_srv = get_user_garmin_service(user_id)
    success, error = garmin_srv.login(email, password)
    if success:
        print(f"Succès ! Connecté à Garmin Connect en tant que {email}.")
    else:
        print(f"Erreur : {error}")


def cmd_sync_garmin(user_id: int, limit: int = 20):
    print(f"Récupération des {limit} dernières activités Garmin...")
    try:
        sync_srv = get_user_sync_service(user_id)
        res = sync_srv.refresh_garmin_activities(limit=limit)
        print(f"Succès : {res['count']} activités récupérées et enregistrées en base.")
    except Exception as e:
        print(f"Erreur lors de la synchronisation : {e}")


def cmd_list(user_id: int, limit: int = 20):
    activities = list_activities(user_id=user_id, limit=limit)
    if not activities:
        print("Aucune activité trouvée dans la base locale. Exécutez d'abord la synchronisation.")
        return

    print(f"\n{'ID Garmin':<14} | {'Date':<16} | {'Sport':<12} | {'Distance':<10} | {'Durée':<10} | {'Statut Strava':<12} | {'Titre'}")
    print("-" * 100)
    for a in activities:
        dist_km = f"{a['distance_meters'] / 1000:.2f} km" if a['distance_meters'] else "-"
        mins = int(a['duration_seconds'] // 60) if a['duration_seconds'] else 0
        dur_str = f"{mins} min"
        date_str = a['start_time'][:16] if a['start_time'] else "-"
        status = a['status'].upper()

        print(f"{a['garmin_activity_id']:<14} | {date_str:<16} | {a['activity_type'][:12]:<12} | {dist_km:<10} | {dur_str:<10} | {status:<12} | {a['activity_name'][:30]}")
    print("-" * 100 + "\n")


def cmd_push(user_id: int, activity_id: str):
    print(f"Envoi de l'activité {activity_id} vers Strava...")
    try:
        sync_srv = get_user_sync_service(user_id)
        res = sync_srv.push_activity_to_strava(activity_id)
        if res.get("success"):
            print("Activité synchronisée avec succès sur Strava !")
            if res.get("strava_url"):
                print(f"Lien Strava : {res['strava_url']}")
        else:
            print(f"Échec de l'envoi : {res.get('error')}")
    except Exception as e:
        print(f"Erreur : {e}")


def run_cli():
    init_db()
    parser = argparse.ArgumentParser(description="Garmin to Strava CLI Tool")
    parser.add_argument("--user-email", type=str, help="Email du compte utilisateur à utiliser")
    subparsers = parser.add_subparsers(dest="command", help="Commandes disponibles")

    # Status
    subparsers.add_parser("status", help="Afficher le statut des connexions")

    # Login Garmin
    subparsers.add_parser("login-garmin", help="Se connecter à Garmin Connect")

    # Sync Garmin
    sync_p = subparsers.add_parser("sync", help="Synchroniser les activités depuis Garmin")
    sync_p.add_argument("--limit", type=int, default=20, help="Nombre d'activités à récupérer (défaut: 20)")

    # List activities
    list_p = subparsers.add_parser("list", help="Lister les activités locales")
    list_p.add_argument("--limit", type=int, default=20, help="Nombre d'activités à afficher (défaut: 20)")

    # Push to Strava
    push_p = subparsers.add_parser("push", help="Pousser une activité individuelle vers Strava")
    push_p.add_argument("activity_id", type=str, help="ID de l'activité Garmin")

    args = parser.parse_args()

    if args.user_email:
        user = get_user_by_email(args.user_email)
        if not user:
            print(f"Utilisateur introuvable pour l'email {args.user_email}")
            return
    else:
        user = get_or_prompt_user()

    user_id = user["id"]

    if args.command == "status":
        print_status(user_id)
    elif args.command == "login-garmin":
        cmd_login_garmin(user_id)
    elif args.command == "sync":
        cmd_sync_garmin(user_id, args.limit)
    elif args.command == "list":
        cmd_list(user_id, args.limit)
    elif args.command == "push":
        cmd_push(user_id, args.activity_id)
    else:
        print_status(user_id)
        parser.print_help()


if __name__ == "__main__":
    run_cli()

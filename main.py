import sys
import argparse
import uvicorn
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.config import BASE_DIR, settings
from app.database import init_db
from app.web.routes import router as web_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize SQLite database on startup
    init_db()
    yield


# Create FastAPI application
app = FastAPI(
    title="Garmin to Strava Sync",
    description="Synchronisez vos activités Garmin et poussez-les individuellement sur Strava.",
    version="1.0.0",
    lifespan=lifespan
)

# Mount static files
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "app" / "web" / "static")), name="static")

# Include Web & API routes
app.include_router(web_router)


def main():
    parser = argparse.ArgumentParser(description="Garmin to Strava Synchronizer")
    parser.add_argument("--cli", action="store_true", help="Lancer l'application en mode ligne de commande (CLI)")
    parser.add_argument("--host", type=str, default=settings.HOST, help="Hôte d'écoute du serveur Web (défaut: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=settings.PORT, help="Port d'écoute du serveur Web (défaut: 8000)")
    parser.add_argument("--reload", action="store_true", help="Activer le rechargement automatique en développement")

    args, unknown = parser.parse_known_args()

    if args.cli:
        from app.cli import run_cli
        run_cli()
    else:
        print(f"\n=======================================================")
        print(f"  Garmin to Strava - Hub de synchronisation d'activités")
        print(f"  Interface Web disponible sur : http://{args.host}:{args.port}")
        print(f"=======================================================\n")
        uvicorn.run("main:app", host=args.host, port=args.port, reload=args.reload)


if __name__ == "__main__":
    main()

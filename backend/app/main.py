"""FastAPI application entrypoint for Beta API Hub by Sonic Network."""

import asyncio
from contextlib import asynccontextmanager
import html
import os
from pathlib import Path
import sys

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import SessionLocal, ensure_db_ready, get_db, get_db_init_status
from app.routers import admin, auth, gateway, keys, payments, plans, playground, public, telegram
from app.services.branding_service import get_effective_branding

FRONTEND_DIR = Path(__file__).resolve().parent.parent.parent / "frontend"


@asynccontextmanager
async def lifespan(_app: FastAPI):
    ok, err = ensure_db_ready()
    if not ok and os.getenv("VERCEL") != "1":
        raise RuntimeError(f"Database initialization failed: {err}")

    cfg = get_settings()
    poll_task = None
    in_pytest = "pytest" in sys.modules or bool(os.getenv("PYTEST_CURRENT_TEST"))

    if ok and not in_pytest:
        if cfg.TELEGRAM_BOT_TOKEN.strip():
            try:
                from app.models.telegram import TelegramBot
                from app.models.user import User
                from app.services.telegram_service import connect_telegram_bot

                with SessionLocal() as db:
                    has_pbot = db.scalar(select(TelegramBot.id).where(TelegramBot.is_platform_bot.is_(True)).limit(1))
                    if not has_pbot:
                        admin_user = db.scalar(select(User).where(User.role == "admin").limit(1))
                        if admin_user:
                            await connect_telegram_bot(
                                db,
                                bot_token=cfg.TELEGRAM_BOT_TOKEN.strip(),
                                owner_user=admin_user,
                                is_platform_bot=True,
                                settings=cfg,
                            )
            except Exception as exc:
                print(f"[telegram_bootstrap_warning] {type(exc).__name__}: {exc}", file=sys.stderr)

        if cfg.TELEGRAM_POLLING_ENABLED and os.getenv("VERCEL") != "1":
            from app.services.telegram_service import telegram_polling_loop

            poll_task = asyncio.create_task(telegram_polling_loop(SessionLocal))

    try:
        yield
    finally:
        if poll_task is not None:
            poll_task.cancel()
            try:
                await poll_task
            except asyncio.CancelledError:
                pass


def create_app() -> FastAPI:
    cfg = get_settings()
    app = FastAPI(
        title=f"{cfg.APP_NAME} by {cfg.COMPANY_NAME}",
        description=cfg.SITE_META_DESCRIPTION,
        version="1.0.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=cfg.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def add_security_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        return response

    app.include_router(public.router)
    app.include_router(auth.router)
    app.include_router(plans.router)
    app.include_router(keys.router)
    app.include_router(payments.router)
    app.include_router(playground.router)
    app.include_router(telegram.router)
    app.include_router(admin.router)
    app.include_router(gateway.router)

    @app.get("/healthz")
    def healthz():
        db_ok, db_err = get_db_init_status()
        if not db_ok and os.getenv("VERCEL") == "1":
            db_ok, db_err = ensure_db_ready()
        payload = {
            "status": "ok" if db_ok else "degraded",
            "service": cfg.APP_NAME,
            "company": cfg.COMPANY_NAME,
            "database": "connected" if db_ok else "unavailable",
        }
        if not db_ok and db_err:
            payload["database_error_type"] = db_err.split(":", 1)[0]
        return payload

    @app.get("/favicon.svg", include_in_schema=False)
    @app.get("/favicon.ico", include_in_schema=False)
    def serve_favicon(db: Session = Depends(get_db)):
        brand = get_effective_branding(db)
        letter = html.escape(brand["brand_letter"])
        svg = (
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">'
            '<rect width="64" height="64" rx="16" fill="#0a0a0a"/>'
            f'<text x="50%" y="54%" dominant-baseline="middle" text-anchor="middle" '
            'font-family="Inter,-apple-system,sans-serif" font-weight="800" font-size="34" fill="#ffffff">'
            f"{letter}</text></svg>"
        )
        return Response(content=svg, media_type="image/svg+xml")

    if FRONTEND_DIR.exists():
        if (FRONTEND_DIR / "css").exists():
            app.mount("/css", StaticFiles(directory=FRONTEND_DIR / "css"), name="css")
        if (FRONTEND_DIR / "js").exists():
            app.mount("/js", StaticFiles(directory=FRONTEND_DIR / "js"), name="js")

        @app.get("/config.js", include_in_schema=False)
        def serve_config_js():
            cfg_path = FRONTEND_DIR / "config.js"
            if cfg_path.exists():
                return Response(content=cfg_path.read_text(encoding="utf-8"), media_type="application/javascript")
            return Response(content="window.__APP_CONFIG__ = window.__APP_CONFIG__ || { API_BASE_URL: '' };", media_type="application/javascript")

        @app.get("/", include_in_schema=False)
        @app.get("/docs-portal", include_in_schema=False)
        @app.get("/dashboard", include_in_schema=False)
        @app.get("/playground", include_in_schema=False)
        @app.get("/admin", include_in_schema=False)
        @app.get("/admin/login", include_in_schema=False)
        def serve_spa(db: Session = Depends(get_db)):
            brand = get_effective_branding(db)
            raw_html = (FRONTEND_DIR / "index.html").read_text(encoding="utf-8")
            brand_title = html.escape(f"{brand['app_name']} by {brand['company_name']} — API Gateway & Developer Platform")
            meta_desc = html.escape(brand["site_description"])
            rendered = raw_html.replace(
                "Beta API Hub by Sonic Network — Enterprise API Gateway & Developer Platform",
                brand_title,
            ).replace(
                "Initializing Beta API Hub...",
                f"Initializing {html.escape(brand['app_name'])}...",
            ).replace(
                "Purchase high-throughput API access plans, manage isolated developer keys linked to Sonic Network's Master Gateway, test live endpoints, and scale seamlessly with Razorpay.",
                meta_desc,
            )
            return HTMLResponse(content=rendered)
    else:
        @app.get("/")
        def api_root():
            return JSONResponse(
                {
                    "service": cfg.APP_NAME,
                    "company": cfg.COMPANY_NAME,
                    "status": "running",
                    "frontend_url": cfg.effective_frontend_url,
                    "docs": "/docs",
                    "health": "/healthz",
                }
            )

    return app


app = create_app()


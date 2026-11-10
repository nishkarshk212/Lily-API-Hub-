"""FastAPI application entrypoint for Lily API Hub by Sonic Network."""

from contextlib import asynccontextmanager
import html
from pathlib import Path

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import SessionLocal, get_db, init_db
from app.core.seed import seed_initial_data
from app.routers import admin, auth, gateway, keys, payments, plans, playground, public
from app.services.branding_service import get_effective_branding

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    with SessionLocal() as db:
        seed_initial_data(db)
    yield


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
    app.include_router(admin.router)
    app.include_router(gateway.router)

    @app.get("/healthz")
    def healthz():
        return {"status": "ok", "service": cfg.APP_NAME, "company": cfg.COMPANY_NAME}

    if FRONTEND_DIR.exists():
        app.mount("/css", StaticFiles(directory=FRONTEND_DIR / "css"), name="css")
        app.mount("/js", StaticFiles(directory=FRONTEND_DIR / "js"), name="js")

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
                "Lily API Hub by Sonic Network — Enterprise API Gateway & Developer Platform",
                brand_title,
            ).replace(
                "Initializing Lily API Hub...",
                f"Initializing {html.escape(brand['app_name'])}...",
            ).replace(
                "Purchase high-throughput API access plans, manage isolated developer keys linked to Sonic Network's Master Gateway, test live endpoints, and scale seamlessly with Razorpay.",
                meta_desc,
            )
            return HTMLResponse(content=rendered)
    else:
        @app.get("/")
        def api_root():
            return JSONResponse({"service": cfg.APP_NAME, "status": "running"})

    return app


app = create_app()


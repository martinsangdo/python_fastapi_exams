"""
app/main.py  —  FastAPI application entry point (MVC: Router/Controller layer)
"""
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
import os, structlog

from app.core.config import settings
from app.core.database import connect_db, close_db
from app.core.cache import init_cache, close_cache
from app.middleware.auth import logging_middleware

log = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("app.starting", name=settings.APP_NAME, env=settings.APP_ENV)
    await connect_db()
    await init_cache()
    from app.services.exam_service import rebuild_trie
    await rebuild_trie()
    log.info("app.ready")
    yield
    await close_db()
    await close_cache()
    log.info("app.stopped")


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.APP_NAME,
        description="Exam preparation platform — FastAPI + MongoDB + Redis + AI",
        version="1.0.0",
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
    )

    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.FRONTEND_URL, "http://localhost:3000", "http://localhost:8080", "*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Request logging
    app.middleware("http")(logging_middleware)

    # Prometheus
    if settings.PROMETHEUS_ENABLED:
        try:
            from prometheus_fastapi_instrumentator import Instrumentator
            Instrumentator().instrument(app).expose(app, endpoint="/metrics")
        except ImportError:
            pass

    # ── Routers ──────────────────────────────────────────────────
    from app.api.v1.endpoints.auth    import router as auth_router
    from app.api.v1.endpoints.exams   import router as exams_router
    from app.api.v1.endpoints.attempts import (
        router as attempts_router,
        payments_router,
        ai_router,
    )
    from app.api.v1.endpoints.users   import router as users_router, rag_router

    prefix = settings.API_V1_STR
    app.include_router(auth_router,     prefix=prefix)
    app.include_router(exams_router,    prefix=prefix)
    app.include_router(attempts_router, prefix=prefix)
    app.include_router(payments_router, prefix=prefix)
    app.include_router(ai_router,       prefix=prefix)
    app.include_router(users_router,    prefix=prefix)
    app.include_router(rag_router,      prefix=prefix)

    # ── Suppress Chrome DevTools Noise ───────────────────────────
    @app.get("/.well-known/appspecific/com.chrome.devtools.json", include_in_schema=False)
    async def chrome_devtools_noise():
        return {}

    # ── Serve Exam Detail Page ───────────────────────────────────
    @app.get("/detail/{slug}", include_in_schema=False)
    async def serve_exam_detail(slug: str):
        frontend_path = os.path.join(os.path.dirname(__file__), "..", "frontend")
        return FileResponse(os.path.join(frontend_path, "pages", "exam-detail.html"))

    # ── Serve Static Pages with Clean URLs ───────────────────────
    @app.get("/login", include_in_schema=False)
    @app.get("/signup", include_in_schema=False)
    @app.get("/profile", include_in_schema=False)
    @app.get("/admin", include_in_schema=False)
    @app.get("/my-learning", include_in_schema=False)
    @app.get("/quiz", include_in_schema=False)
    @app.get("/exam-quiz", include_in_schema=False)
    @app.get("/help-center", include_in_schema=False)
    @app.get("/refund-policy", include_in_schema=False)
    @app.get("/accessibility", include_in_schema=False)
    @app.get("/privacy-policy", include_in_schema=False)
    @app.get("/terms", include_in_schema=False)
    @app.get("/about-us", include_in_schema=False)
    @app.get("/contact", include_in_schema=False)
    async def serve_pages(request: Request):
        page = request.url.path.strip("/")
        # special mapping: "quiz" -> exam-quiz.html
        filename = "exam-quiz.html" if page == "quiz" else f"{page}.html"
        frontend_path = os.path.join(os.path.dirname(__file__), "..", "frontend")
        return FileResponse(os.path.join(frontend_path, "pages", filename))

    # ── Protect JS files from direct browser access ────────────────
    @app.get("/js/{file_path:path}", include_in_schema=False)
    async def protect_js(request: Request, file_path: str):
        # If the browser is attempting to navigate directly to the file
        sec_fetch_dest = request.headers.get("sec-fetch-dest")
        accept = request.headers.get("accept", "")
        
        if sec_fetch_dest == "document" or ("text/html" in accept and "application/javascript" not in accept):
            log.warning("security.js_leak_attempt", path=file_path, ip=request.client.host)
            raise HTTPException(status_code=403, detail="Direct access to source scripts is forbidden.")

        frontend_path = os.path.join(os.path.dirname(__file__), "..", "frontend")
        full_path = os.path.join(frontend_path, "js", file_path)
        if os.path.exists(full_path):
            return FileResponse(full_path)
        raise HTTPException(status_code=404)

    # ── Serve frontend static files ───────────────────────────────
    frontend_path = os.path.join(os.path.dirname(__file__), "..", "frontend")
    if os.path.isdir(frontend_path):
        app.mount("/", StaticFiles(directory=frontend_path, html=True), name="frontend")

    # ── Health ────────────────────────────────────────────────────
    @app.get("/health", tags=["System"])
    async def health():
        from app.core.database import get_db
        from app.core.cache import get_cache
        try:
            await get_db().command("ping"); db_ok = True
        except Exception: db_ok = False
        try:
            await get_cache().ping(); cache_ok = True
        except Exception: cache_ok = False
        return {
            "status": "healthy" if db_ok and cache_ok else "degraded",
            "database": "ok" if db_ok else "error",
            "cache": "ok" if cache_ok else "error",
            "version": "1.0.0",
        }

    return app


app = create_app()

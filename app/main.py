"""
app/main.py  —  FastAPI application entry point (MVC: Router/Controller layer)
"""
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
import os, structlog

from app.core.config import settings
from app.core.database import connect_db, close_db
from app.core.cache import init_cache, close_cache
from app.middleware.auth import logging_middleware

def _ga_snippet() -> str:
    ga_id = settings.GOOGLE_ANALYTICS_ID
    if not ga_id:
        return ""
    return (
        f'<script async src="https://www.googletagmanager.com/gtag/js?id={ga_id}"></script>\n'
        f'<script>window.dataLayer=window.dataLayer||[];'
        f'function gtag(){{dataLayer.push(arguments);}}gtag("js",new Date());gtag("config","{ga_id}");</script>'
    )

_GA_SNIPPET = _ga_snippet()

log = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("app.starting", name=settings.APP_NAME, env=settings.APP_ENV)
    await connect_db()
    await init_cache()
    from app.services.exam_service import rebuild_trie
    await rebuild_trie()
    # TTL index — auto-expire rate-limit records after 1 hour
    from app.core.database import get_db as _get_db
    try:
        await _get_db().pw_reset_rate_limits.create_index("expires_at", expireAfterSeconds=0)
    except Exception:
        pass
    try:
        # Auto-purge contact inquiries older than 90 days
        await _get_db().contact_inquiries.create_index("created_at", expireAfterSeconds=60 * 60 * 24 * 90)
        # Index for the per-email-per-day rate-limit query
        await _get_db().contact_inquiries.create_index([("email", 1), ("created_at", -1)])
    except Exception:
        pass
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

    # Google Analytics injection
    if _GA_SNIPPET:
        @app.middleware("http")
        async def inject_ga(request: Request, call_next):
            response = await call_next(request)
            ct = response.headers.get("content-type", "")
            if "text/html" in ct:
                body = b"".join([chunk async for chunk in response.body_iterator])
                body = body.replace(b"</head>", (_GA_SNIPPET + "\n</head>").encode())
                headers = {k: v for k, v in response.headers.items() if k.lower() != "content-length"}
                return HTMLResponse(content=body.decode(), status_code=response.status_code, headers=headers)
            return response

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
    from app.api.v1.endpoints.users   import router as users_router
    from app.api.v1.endpoints.contact import router as contact_router

    prefix = settings.API_V1_STR
    app.include_router(auth_router,     prefix=prefix)
    app.include_router(exams_router,    prefix=prefix)
    app.include_router(attempts_router, prefix=prefix)
    app.include_router(payments_router, prefix=prefix)
    app.include_router(ai_router,       prefix=prefix)
    app.include_router(users_router,    prefix=prefix)
    app.include_router(contact_router,  prefix=prefix)

    # ── Suppress Chrome DevTools Noise ───────────────────────────
    @app.get("/.well-known/appspecific/com.chrome.devtools.json", include_in_schema=False)
    async def chrome_devtools_noise():
        return {}

    # ── Serve Exam Detail Page (SSR meta tags for social crawlers) ──
    @app.get("/detail/{slug}", include_in_schema=False)
    async def serve_exam_detail(slug: str):
        from app.services import exam_service
        from app.core.config import settings

        frontend_path = os.path.join(os.path.dirname(__file__), "..", "frontend")
        html = open(os.path.join(frontend_path, "pages", "exam-detail.html"), encoding="utf-8").read()

        base_url = settings.FRONTEND_URL.rstrip("/")
        title = f"Practice Exams for {slug.replace('-', ' ').title()} — CertQuestionBank"
        desc = f"Prepare for the {slug.replace('-', ' ').title()} exam with full-length timed practice tests on CertQuestionBank."
        image = f"{base_url}/og-image.png"
        canonical = f"{base_url}/detail/{slug}"

        try:
            exam = await exam_service.get_exam_by_slug(slug)
            if exam:
                title = f"Practice Exams for {exam['title']} — CertQuestionBank"
                q_count = exam.get("questions", "")
                desc = f"Prepare for the {exam['title']} exam with {q_count} practice questions across 6 full-length timed tests. {exam.get('description', '')}".strip()
                if exam.get("logo_url"):
                    image = f"{base_url}{exam['logo_url']}"
        except Exception:
            pass

        def esc(s: str) -> str:
            return str(s).replace("&", "&amp;").replace('"', "&quot;").replace("<", "&lt;").replace(">", "&gt;")

        meta_block = f"""
  <meta name="description" content="{esc(desc)}"/>
  <link rel="canonical" href="{esc(canonical)}"/>
  <meta property="og:type" content="website"/>
  <meta property="og:site_name" content="CertQuestionBank"/>
  <meta property="og:url" content="{esc(canonical)}"/>
  <meta property="og:title" content="{esc(title)}"/>
  <meta property="og:description" content="{esc(desc)}"/>
  <meta property="og:image" content="{esc(image)}"/>
  <meta property="og:image:width" content="1200"/>
  <meta property="og:image:height" content="630"/>
  <meta property="og:image:alt" content="{esc(title)}"/>
  <meta name="twitter:card" content="summary_large_image"/>
  <meta name="twitter:site" content="@certquestionbank"/>
  <meta name="twitter:title" content="{esc(title)}"/>
  <meta name="twitter:description" content="{esc(desc)}"/>
  <meta name="twitter:image" content="{esc(image)}"/>
  <meta name="twitter:image:alt" content="{esc(title)}"/>"""

        html = html.replace("  <!-- SSR_META -->", meta_block)
        return HTMLResponse(html)

    # ── Serve Static Pages with Clean URLs ───────────────────────
    @app.get("/login", include_in_schema=False)
    @app.get("/signup", include_in_schema=False)
    @app.get("/forgot-password", include_in_schema=False)
    @app.get("/reset-password", include_in_schema=False)
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
    @app.get("/payment/success", include_in_schema=False)
    @app.get("/payment/cancel", include_in_schema=False)
    async def serve_pages(request: Request):
        page = request.url.path.strip("/")
        special = {"quiz": "exam-quiz.html", "forgot-password": "forgot-password.html", "reset-password": "reset-password.html", "payment/success": "payment-success.html", "payment/cancel": "payment-cancel.html"}
        filename = special.get(page, f"{page}.html")
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

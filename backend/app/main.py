"""FastAPI application entrypoint."""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.v1.endpoints import health as health_endpoints
from app.api.v1.router import api_router
from app.core.config import settings
from app.core.exceptions import AppError
from app.core.logging import get_logger, request_id_ctx, setup_logging

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    setup_logging()
    logger.info("Starting %s (%s)", settings.APP_NAME, settings.APP_ENV)
    scanner_started = False
    if settings.SCANNER_ENABLED:
        from app.tasks.scanner import start_background_scanner

        start_background_scanner(float(settings.SCANNER_INTERVAL_SECONDS))
        scanner_started = True
    try:
        yield
    finally:
        if scanner_started:
            from app.tasks.scanner import stop_background_scanner

            await stop_background_scanner()
        logger.info("Shutting down %s", settings.APP_NAME)


def create_app() -> FastAPI:
    # Production hardening: hide interactive docs unless explicitly enabled.
    expose_docs = settings.ENABLE_API_DOCS or settings.APP_ENV != "production"
    app = FastAPI(
        title=settings.APP_NAME,
        version="1.0.0",
        lifespan=lifespan,
        docs_url="/api/docs" if expose_docs else None,
        openapi_url="/api/openapi.json" if expose_docs else None,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def request_id_middleware(request: Request, call_next):
        request_id = request.headers.get("x-request-id") or uuid.uuid4().hex
        request.state.request_id = request_id
        token = request_id_ctx.set(request_id)
        try:
            response = await call_next(request)
        finally:
            request_id_ctx.reset(token)
        response.headers["x-request-id"] = request_id
        return response

    def _error_payload(code: str, message: str, details: Any, request_id: str | None) -> dict:
        return {
            "code": code,
            "message": message,
            "details": details,
            "request_id": request_id,
        }

    @app.exception_handler(AppError)
    async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
        rid = getattr(request.state, "request_id", None)
        logger.warning("AppError %s: %s", exc.code, exc.message)
        return JSONResponse(status_code=exc.status_code, content=exc.to_payload(rid))

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        rid = getattr(request.state, "request_id", None)
        return JSONResponse(
            status_code=422,
            content=_error_payload(
                "validation_error",
                "Request validation failed",
                exc.errors(),
                rid,
            ),
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_error_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        rid = getattr(request.state, "request_id", None)
        return JSONResponse(
            status_code=exc.status_code,
            content=_error_payload(
                f"http_{exc.status_code}",
                str(exc.detail),
                None,
                rid,
            ),
        )

    @app.exception_handler(Exception)
    async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
        rid = getattr(request.state, "request_id", None)
        logger.exception("Unhandled error req=%s", rid)
        # Do not leak stack traces or SQL to clients (spec §11)
        return JSONResponse(
            status_code=500,
            content=_error_payload("internal_error", "Internal server error", None, rid),
        )

    app.include_router(health_endpoints.router)
    app.include_router(api_router, prefix=settings.API_V1_PREFIX)

    return app


app = create_app()

"""Application factory with fail-fast dataset checks and non-leaking error responses."""

import logging
import sqlite3
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from starlette.exceptions import HTTPException

from backend import __version__
from backend.api import Service, envelope, router
from backend.config import Settings
from backend.database import load_snapshot
from backend.models import Envelope, ErrorResponse
from backend.services import ApiError

logger = logging.getLogger("ipl_backend")


def error_response(status: int, code: str, message: str, details=None):
    return JSONResponse(
        status_code=status,
        content={
            "error": {
                "code": code,
                "message": message,
                "details": details,
            }
        },
    )


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.from_env()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.snapshot = load_snapshot(settings)
        logger.info("IPL dataset %s loaded", app.state.snapshot["version"])
        yield

    app = FastAPI(
        title="IPL Roster Analytics API",
        version=__version__,
        lifespan=lifespan,
        description="Read-only IPL observations, Bayesian delivery forecasts, uninterrupted match simulations and constrained XI planning with exclusive historical cutoffs. "
        "No production-validated predictions, verified eligible XI or live injury/pitch feed yet.",
    )
    app.state.settings = settings
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins),
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["Accept", "Content-Type"],
    )

    @app.exception_handler(ApiError)
    async def domain_error(_request: Request, exc: ApiError):
        return error_response(exc.status, exc.code, exc.message)

    @app.exception_handler(RequestValidationError)
    async def validation_error(_request: Request, exc: RequestValidationError):
        details = [
            {"location": list(e["loc"]), "message": e["msg"], "type": e["type"]}
            for e in exc.errors()
        ]
        return error_response(
            422, "invalid_request", "One or more request parameters are invalid", details
        )

    @app.exception_handler(HTTPException)
    async def http_error(_request: Request, exc: HTTPException):
        return error_response(exc.status_code, "http_error", str(exc.detail))

    @app.exception_handler(sqlite3.Error)
    async def database_error(_request: Request, exc: sqlite3.Error):
        interrupted = "interrupted" in str(exc).lower()
        code = "query_timeout" if interrupted else "data_unavailable"
        logger.warning("Database request failed: %s", code)
        return error_response(
            503, code, "The data query could not complete; try a narrower filter or retry"
        )

    @app.exception_handler(Exception)
    async def unexpected_error(_request: Request, exc: Exception):
        logger.error("Unhandled backend error", exc_info=exc)
        return error_response(500, "internal_error", "An unexpected server error occurred")

    @app.get("/", include_in_schema=False)
    def root():
        return RedirectResponse("/docs")

    @app.get("/health", tags=["Operations"])
    def health():
        return {"status": "ok", "service": "ipl-roster-backend", "version": __version__}

    @app.get(
        "/ready",
        response_model=Envelope[dict],
        tags=["Operations"],
        responses={503: {"model": ErrorResponse}},
    )
    def ready(service: Service):
        service.db.execute("SELECT 1 FROM players LIMIT 1").fetchone()
        return envelope(service, {"status": "ready", "database": "read_only"})

    app.include_router(router)
    return app


app = create_app()

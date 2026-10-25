import logging
import time
import uuid

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.v1.router import api_router
from app.core.config import get_settings

settings = get_settings()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-5s %(name)s: %(message)s",
)
logger = logging.getLogger("raisa_synapse")


def create_app() -> FastAPI:
    app = FastAPI(
        title="RAISA Synapse API",
        description="Layer 1 foundation — see /docs/LAYER_1_FOUNDATION.md",
        version="0.1.0-layer1",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ALLOW_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def request_context_middleware(request: Request, call_next):
        """Structured logging foundation (spec §50): every request gets a
        request_id, and it's echoed back in the response header so a
        frontend error toast can be correlated with a server log line."""
        request_id = str(uuid.uuid4())
        start = time.monotonic()
        response = await call_next(request)
        duration_ms = round((time.monotonic() - start) * 1000, 2)
        response.headers["X-Request-ID"] = request_id
        logging.getLogger("raisa_synapse.access").info(
            "request_id=%s %s %s -> %s (%sms)",
            request_id,
            request.method,
            request.url.path,
            response.status_code,
            duration_ms,
        )
        return response

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        """Standard API error model (spec §49) — every error response has
        the same shape, and internal stack traces never reach the client.
        """
        request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error_code": f"HTTP_{exc.status_code}",
                "message": exc.detail if isinstance(exc.detail, str) else "Request failed",
                "details": exc.detail if isinstance(exc.detail, dict) else None,
                "request_id": request_id,
                "timestamp": time.time(),
            },
        )

    app.include_router(api_router)

    return app


app = create_app()

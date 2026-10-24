"""HTTP boundary and application factory. Business decisions live in the service."""

from importlib.resources import files

from fastapi import FastAPI, HTTPException
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .analysis import LabEngine
from .models import Analysis, AnalyzeRequest
from .providers import EvidenceProvider
from .providers.catalog import SERVICES
from .providers.mock import scenario_catalog
from .service import AnalysisService, AnalysisUnavailable, EvidenceUnavailable
from .settings import Settings


def create_app(settings: Settings | None = None, service: AnalysisService | None = None) -> FastAPI:
    settings = settings or (service.settings if service is not None else Settings.from_env())
    service = service or AnalysisService(settings, EvidenceProvider(settings), LabEngine(settings))
    app = FastAPI(title="TiderOps · Consola de agentes", version="0.5.0")
    app.state.analysis_service = service
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["localhost", "127.0.0.1", "[::1]", "testserver"])
    static = files("tider.console").joinpath("static")
    app.mount("/static", StaticFiles(directory=str(static)), name="static")

    @app.middleware("http")
    async def response_headers(request, call_next):
        response = await call_next(request)
        response.headers.update(
            {
                "X-Content-Type-Options": "nosniff",
                "Referrer-Policy": "no-referrer",
                "Cache-Control": "no-store",
            }
        )
        if request.url.path == "/":
            response.headers["Content-Security-Policy"] = (
                "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; frame-ancestors 'none'; base-uri 'none'"
            )
        return response

    @app.get("/", include_in_schema=False)
    def console():
        return FileResponse(str(static.joinpath("index.html")))

    @app.get("/health")
    def health():
        return {
            "status": "ok",
            "evidence_mode": settings.evidence_mode,
            "engine": "langgraph",
            "execution": "observation",
        }

    @app.get("/v1/lab/config")
    def config():
        return {
            "project": settings.google_cloud_project,
            "cluster": settings.gcp_cluster,
            "namespace": settings.gcp_namespace,
            "location": settings.gcp_location,
            "gcp_enabled": settings.evidence_mode == "gcp",
            "reasoning_mode": settings.llm_provider,
            "model": settings.tider_model if settings.llm_provider != "none" else "",
            "services": SERVICES,
            "scenarios": scenario_catalog(),
            "history_limit": settings.history_limit,
            "gcp_sources": ["log"],
            "execution": "observation",
        }

    @app.get("/v1/incidents", response_model=list[Analysis])
    def incidents():
        return service.history()

    @app.post("/v1/incidents/analyze", response_model=Analysis)
    def analyze(request: AnalyzeRequest):
        try:
            return service.analyze(request)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        except EvidenceUnavailable:
            raise HTTPException(
                503, "No se pudo consultar la evidencia. Revisa credenciales, permisos y configuración."
            ) from None
        except AnalysisUnavailable:
            raise HTTPException(
                503, "No se pudo completar el análisis. Revisa el motor y la configuración del modelo."
            ) from None

    return app

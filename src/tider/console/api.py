"""HTTP boundary and application factory. Business decisions live in the service."""

from importlib.resources import files

from fastapi import FastAPI, HTTPException
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .analysis import LabEngine
from .catalog_review import CatalogReview
from .context_lake import ContextLake
from .models import Analysis, AnalyzeRequest
from .providers import EvidenceProvider
from .providers.catalog import SERVICES
from .providers.mock import scenario_catalog
from .service import AnalysisService, AnalysisUnavailable, EvidenceUnavailable
from .settings import Settings


class ContextUpload(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    content: str = Field(min_length=1, max_length=1_000_000)


class ContextQuery(BaseModel):
    query: str = Field(min_length=1, max_length=2000)


def create_app(settings: Settings | None = None, service: AnalysisService | None = None) -> FastAPI:
    settings = settings or (service.settings if service is not None else Settings.from_env())
    lake = ContextLake()
    service = service or AnalysisService(settings, EvidenceProvider(settings, lake), LabEngine(settings, lake))
    app = FastAPI(title="TiderOps · Consola de agentes", version="0.5.0")
    app.state.analysis_service = service
    app.state.context_lake = lake
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["localhost", "127.0.0.1", "[::1]", "testserver"])
    static = files("tider.console").joinpath("static")
    app.mount("/static", StaticFiles(directory=str(static)), name="static")

    @app.middleware("http")
    async def response_headers(request, call_next):
        if request.url.path.startswith("/v1/context") and request.method in {"POST", "DELETE"}:
            origin = request.headers.get("origin")
            if origin and origin != str(request.base_url).rstrip("/"):
                from fastapi.responses import JSONResponse

                return JSONResponse({"detail": "Origen no permitido."}, status_code=403)
            if request.method == "POST":
                size = 0
                chunks = []
                async for chunk in request.stream():
                    size += len(chunk)
                    if size > 6_100_000:
                        from fastapi.responses import JSONResponse

                        return JSONResponse({"detail": "Solicitud demasiado grande."}, status_code=413)
                    chunks.append(chunk)
                request._body = b"".join(chunks)
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
        catalog = lake.catalog()
        confirmed = catalog["confirmed"]
        return {
            "project": settings.google_cloud_project,
            "cluster": settings.gcp_cluster,
            "namespace": settings.gcp_namespace,
            "location": settings.gcp_location,
            "gcp_enabled": settings.evidence_mode == "gcp",
            "reasoning_mode": settings.llm_provider,
            "model": settings.tider_model if settings.llm_provider != "none" else "",
            "services": [s["name"] for s in confirmed["services"]]
            if confirmed
            else ([] if catalog["status"] == "pending" else SERVICES),
            "mock_services": SERVICES,
            "catalog_status": catalog["status"],
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

    @app.get("/v1/context/catalog")
    def context_catalog():
        return lake.catalog()

    @app.post("/v1/context/catalog/confirm")
    def context_catalog_confirm(body: CatalogReview):
        try:
            return lake.confirm_catalog(body)
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from None

    @app.get("/v1/context")
    def context_inventory():
        return lake.inventory()

    @app.post("/v1/context/documents")
    def context_upload(body: ContextUpload):
        try:
            return lake.add(body.name, body.content)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from None
        except Exception:
            raise HTTPException(
                503, "No se pudo indexar. Comprueba la disponibilidad del modelo local."
            ) from None

    @app.delete("/v1/context/documents/{doc_id}")
    def context_delete(doc_id: str):
        try:
            lake.delete(doc_id)
        except KeyError:
            raise HTTPException(404, "Documento no encontrado.") from None
        return {"deleted": True}

    @app.post("/v1/context/search")
    def context_search(body: ContextQuery):
        try:
            matches = lake.search(body.query)
            return {
                "matches": matches,
                "status": "matches" if matches else "insufficient_context",
                "message": ""
                if matches
                else "No encontramos información suficiente sobre esta consulta en los documentos cargados.",
            }
        except Exception:
            raise HTTPException(503, "No se pudo consultar el índice documental.") from None

    return app

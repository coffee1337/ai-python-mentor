import os
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.auth import router as auth_router
from app.learning import router as learning_router
from app.mentor import router as mentor_router
from app.practice import router as practice_router
from app.learning_plan_api import router as learning_plan_router
from app.knowledge_check import router as knowledge_check_router
from app.assessment import router as assessment_router
from app.skill_graph_api import router as skill_graph_router
from app.curriculum_api import router as curriculum_router
from app.ai_curriculum_api import router as ai_curriculum_router
from app.exercise_hints import router as exercise_hints_router
from app.mistake_memory_api import router as mistake_memory_router
from app.reviews_api import router as reviews_router
from app.reflections_api import router as reflections_router
from app.accounts_api import router as accounts_router
from app.vacancies import router as vacancies_router
from app.projects import router as projects_router
from app.generated_practice import router as generated_practice_router
from app.jobs_api import router as jobs_router
from app.health_api import router as health_router
from app.http_limits import RequestSizeLimit
from app.db.session import engine

logger = logging.getLogger("mentor.startup")


@asynccontextmanager
async def lifespan(_: FastAPI):
    report_gateway_status()
    yield


app = FastAPI(title="AI-наставник API", version="0.1.0", lifespan=lifespan)
app.add_middleware(RequestSizeLimit)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in os.getenv("WEB_ORIGINS", "http://localhost:3000").split(",") if origin.strip()],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "X-CSRF-Token", "Idempotency-Key"],
)
app.include_router(auth_router)
app.include_router(learning_router)
app.include_router(mentor_router)
app.include_router(practice_router)
app.include_router(learning_plan_router)
app.include_router(knowledge_check_router)
app.include_router(assessment_router)
app.include_router(skill_graph_router)
app.include_router(curriculum_router)
app.include_router(ai_curriculum_router)
app.include_router(exercise_hints_router)
app.include_router(mistake_memory_router)
app.include_router(reviews_router)
app.include_router(reflections_router)
app.include_router(accounts_router)
app.include_router(vacancies_router)
app.include_router(projects_router)
app.include_router(generated_practice_router)
app.include_router(jobs_router)
app.include_router(health_router)


def report_gateway_status() -> None:
    """Log gateway readiness without printing keys or endpoints."""
    try:
        from app import ai_gateway

        ai_gateway.configuration()
    except ai_gateway.GatewayError:
        logger.warning(
            "AI gateway is not configured: mentor chat and AI curriculum return 503. "
            "Set AI_GATEWAY_URL, AI_GATEWAY_MODEL and AI_GATEWAY_API_KEY in .env, then restart."
        )
    else:
        logger.info("AI gateway configured; mentor chat and AI curriculum are available.")


@app.get("/health", tags=["health"])
def health() -> dict[str, str]:
    """Report API and database readiness without exposing connection details."""
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail="Database is unavailable") from exc
    return {"status": "ok", "database": "ok"}


@app.middleware("http")
async def request_observation(request, call_next):
    from uuid import uuid4
    from time import monotonic
    from starlette.responses import JSONResponse
    request_id = str(uuid4())
    started = monotonic()
    try:
        response = await call_next(request)
    except Exception as error:
        # Exception text/SQL/body may contain learner source, tokens or PII.
        logging.getLogger("mentor.request").error("request_failed id=%s type=%s", request_id, type(error).__name__)
        response = JSONResponse({"detail":"Service is temporarily unavailable","request_id":request_id},status_code=503 if isinstance(error, SQLAlchemyError) else 500)
    response.headers["X-Request-ID"] = request_id
    route = getattr(request.scope.get("route"), "path", "unmatched")
    logging.getLogger("mentor.request").info("request_finished id=%s method=%s route=%s status=%s duration_ms=%d",request_id,request.method,route,response.status_code,int((monotonic()-started)*1000))
    return response

import logging
import time
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from prometheus_client import REGISTRY
from prometheus_fastapi_instrumentator import Instrumentator
from sqlalchemy import text
from sqlalchemy.exc import OperationalError, ProgrammingError
from sqlalchemy.orm import Session

from . import monitoring
from .auth import _jwt_secret, ensure_initial_users
from .config import settings
from .database import Base, SessionLocal, engine, get_db
from .integrity import IntegrityError
from .metrics import model_mae
from .routers import auth, forecast, products, sales, stock
from .seed import seed
from .services import _load_forecaster

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("freshtrack")


def create_tables(retries: int = 5):
    for attempt in range(1, retries + 1):
        try:
            Base.metadata.create_all(engine)
            return
        except (OperationalError, ProgrammingError) as err:
            if attempt == retries:
                raise
            log.warning("create tables failed (%s), retry %d/%d", type(err).__name__, attempt, retries)
            time.sleep(3)


@asynccontextmanager
async def lifespan(app: FastAPI):
    create_tables()
    _jwt_secret()
    with SessionLocal() as db:
        ensure_initial_users(db)
    if settings.seed_on_start:
        with SessionLocal() as db:
            if seed(db):
                log.info("database seeded with demo data")
    try:
        fc = _load_forecaster()
        model_mae.set(fc.metrics.get("model", {}).get("mae", 0))
        log.info("forecast model %s loaded from %s (integrity verified)", fc.version, settings.model_path)
    except FileNotFoundError:
        log.warning("no model at %s - forecast endpoints will return 503", settings.model_path)
    except IntegrityError as err:
        log.error("REFUSING to load model: %s", err)
    yield


app = FastAPI(title="FreshTrack Inventory API", version=settings.app_version, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(products.router)
app.include_router(stock.router)
app.include_router(sales.router)
app.include_router(forecast.router)

Instrumentator(excluded_handlers=["/health", "/ready", "/metrics"]).instrument(app).expose(
    app, include_in_schema=False
)


def _model_metrics():
    try:
        return _load_forecaster().metrics
    except FileNotFoundError:
        return None


monitoring.collector.get_metrics = _model_metrics
try:
    REGISTRY.register(monitoring.collector)
except ValueError:
    pass


@app.get("/health", tags=["ops"])
def health():
    return {"status": "ok", "version": settings.app_version}


@app.get("/ready", tags=["ops"])
def ready(db: Session = Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))
    except Exception:
        log.exception("readiness check failed")
        return JSONResponse({"status": "db unavailable"}, status_code=503)
    try:
        _load_forecaster()
    except IntegrityError as err:
        return JSONResponse({"status": "model integrity check failed", "detail": str(err)}, status_code=503)
    except FileNotFoundError:
        pass
    return {"status": "ready"}

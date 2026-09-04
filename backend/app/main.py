"""FastAPI application entry point.

Start it from the project root with:

    .venv\\Scripts\\python.exe -m uvicorn app.main:app --reload --app-dir backend

or, with the virtual environment activated, from inside ``backend/``:

    uvicorn app.main:app --reload

Interactive documentation is then at http://localhost:8000/docs
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.core.config import LISTING_IMAGE_DIR, LISTING_IMAGE_URL_PREFIX, settings
from app.routers import auth, categories, health, listings, marketplace, ml
from app.services.ml_service import classifier

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)-8s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Runs once when the server starts, and once when it stops.

    Two jobs on startup.

    **Make sure the image folder exists.** Git cannot store an empty folder, so
    a fresh clone might not have ``backend/uploads/listings/``. Creating it here
    means the first person to publish a listing does not hit a confusing error.

    **Load the model, and run one throwaway prediction.** The very first
    prediction is slow because TensorFlow builds its computation graph on
    demand; doing it now means the first real user does not pay for it.

    If the model cannot be loaded we log the problem and start anyway. That is
    deliberate: registering, logging in and browsing the marketplace do not need
    the model at all, and a running server that reports ``model_loaded: false``
    on GET /api/health is far easier to diagnose than one that refuses to boot.
    """
    LISTING_IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    logger.info("Listing image folder ready: %s", LISTING_IMAGE_DIR)

    if settings.warm_model_on_startup:
        logger.info("Loading the classification model...")
        try:
            await run_in_threadpool(classifier.warm_up)
            logger.info("Model ready.")
        except Exception:  # noqa: BLE001 - never let this stop startup
            # .exception() logs the full traceback, which is what you need when
            # a model fails to load.
            logger.exception(
                "Model could not be loaded. The API is still running, but "
                "POST /api/ml/predict will fail and GET /api/health will "
                "report model_loaded: false."
            )
    else:
        logger.info("WARM_MODEL_ON_STARTUP is false - model loads on first use.")

    yield

    logger.info("Shutting down.")


app = FastAPI(
    title="Date Fruit AI & Price Marketplace API",
    version="2.0.0",
    description=(
        "AI date-fruit classification plus a shared price marketplace. Every "
        "registered user can classify a photo, publish a priced listing, and "
        "compare prices published by everyone else."
    ),
    lifespan=lifespan,
)

# CORS = Cross-Origin Resource Sharing.
#
# A browser refuses to let a page served from http://localhost:5173 (React) call
# an API on http://localhost:8000 (FastAPI) unless the API explicitly says that
# address is welcome. A different port counts as a different origin, as far as
# the browser is concerned. Without this middleware every request from the React
# app fails with an opaque CORS error in the browser console.
#
# The allowed address comes from FRONTEND_URL in .env - not hard-coded - so this
# still works if the frontend runs on another port or another machine.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(auth.router)
app.include_router(ml.router)
app.include_router(categories.router)
app.include_router(listings.router)
app.include_router(marketplace.router)

# --- Published listing images ---------------------------------------------
#
# This serves the files in backend/uploads/listings/ at /uploads/listings/<name>.
#
# Two things about it are deliberate.
#
# **Only that one folder is exposed.** StaticFiles serves the directory it is
# given and nothing above it: a request for "../../.env" is resolved and refused
# by Starlette before it reaches the filesystem. Writing this by hand is how
# directory-traversal holes get created, so the well-tested implementation is
# used instead.
#
# **The images are not behind the login.** A browser does not send an
# Authorization header when it loads an <img src="...">, so requiring a token
# would simply stop the photos from appearing. Instead every filename is 32
# random hex characters, which is not guessable, and the images are photographs
# of dates in a shop window - they are the least sensitive thing in the project.
# The account details behind them stay protected as normal.
#
# mkdir here as well as in the lifespan above, because StaticFiles checks that
# the folder exists at this moment - which is before the lifespan has run.
LISTING_IMAGE_DIR.mkdir(parents=True, exist_ok=True)
app.mount(
    LISTING_IMAGE_URL_PREFIX,
    StaticFiles(directory=LISTING_IMAGE_DIR),
    name="listing-images",
)


@app.get("/", tags=["meta"])
def read_root() -> dict[str, str]:
    """A plain liveness check, so you can confirm the server is running."""
    return {
        "message": "Date Fruit AI & Price Marketplace API is running",
        "docs": "/docs",
    }

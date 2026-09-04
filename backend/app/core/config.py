"""Application configuration.

Why this file exists
--------------------
Everything that differs from one computer to another - the database password,
the JWT signing secret, the frontend address - is read from a ``.env`` file
instead of being typed into the source code. That is what makes this project
portable: clone it onto a different machine, write a new ``.env``, and it runs
without editing a single Python file.

``backend/.env``          real values, ignored by Git, never committed.
``backend/.env.example``  placeholders, committed, shows which keys exist.

If a value is missing or wrong, the application refuses to start and explains
what to fix. Failing loudly at startup is far easier to debug than a mysterious
error hours later.
"""

from __future__ import annotations

from pathlib import Path

# pyrefly: ignore [missing-import]
from pydantic import field_validator
# pyrefly: ignore [missing-import]
from pydantic_settings import BaseSettings, SettingsConfigDict

# ---------------------------------------------------------------------------
# Project paths
#
# These are worked out from the location of THIS file - never from the current
# working directory, and never from a hard-coded absolute path like
# "C:\\Users\\...". That means `uvicorn` works whether you start it from the
# project root or from inside `backend/`, and the project works after being
# cloned into any folder on any machine.
#
# This file lives at  <project_root>/backend/app/core/config.py  so:
#     parents[0] = <project_root>/backend/app/core
#     parents[1] = <project_root>/backend/app
#     parents[2] = <project_root>/backend
#     parents[3] = <project_root>
# ---------------------------------------------------------------------------
_THIS_FILE = Path(__file__).resolve()

BACKEND_DIR: Path = _THIS_FILE.parents[2]
PROJECT_ROOT: Path = _THIS_FILE.parents[3]

# --- The trained model (never modified by this application) ---------------
MODEL_DIR: Path = PROJECT_ROOT / "model"
MODEL_PATH: Path = MODEL_DIR / "date_fruit_model.keras"
CLASSES_PATH: Path = MODEL_DIR / "classes.json"
CENTER_PATH: Path = MODEL_DIR / "date_feature_center.npy"

# --- Published listing images ---------------------------------------------
# Only images belonging to a published listing are stored here. An image that
# was merely classified and never published is never written to disk.
#
# LISTING_IMAGE_URL_PREFIX is the public web address these are served under.
# The database stores the relative path ("uploads/listings/<name>.jpg"), never
# an absolute Windows path, so the rows stay valid on another computer.
UPLOAD_DIR: Path = BACKEND_DIR / "uploads"
LISTING_IMAGE_DIR: Path = UPLOAD_DIR / "listings"
LISTING_IMAGE_URL_PREFIX: str = "/uploads/listings"

ENV_FILE: Path = BACKEND_DIR / ".env"

# SQLAlchemy reads the part before "://" to decide which driver to load.
# "postgresql://" makes it look for psycopg2, which this project does not
# install; "postgresql+psycopg://" selects psycopg 3, which it does.
PLAIN_POSTGRES_PREFIX = "postgresql://"
PSYCOPG3_POSTGRES_PREFIX = "postgresql+psycopg://"
SQLITE_PREFIX = "sqlite:"


class Settings(BaseSettings):
    """Values loaded from ``backend/.env``.

    Each attribute name here maps to the upper-case key in the .env file:
    ``database_url`` <- ``DATABASE_URL``. Matching is case-insensitive.
    """

    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- Required: no default, so a missing value is an immediate error ---
    database_url: str
    jwt_secret: str

    # --- Optional: sensible defaults, overridable from .env ---
    jwt_expire_minutes: int = 60
    confidence_threshold: float = 0.70
    frontend_url: str = "http://localhost:5173"

    # ------------------------------------------------------------------
    # Fixed technical settings. Deliberately NOT in .env.example, because
    # changing them is a code decision rather than a per-machine one.
    # ------------------------------------------------------------------

    # HS256 = sign the token with our shared secret. Standard for a single
    # backend like this one.
    jwt_algorithm: str = "HS256"

    # Reject uploads larger than 5 MB before spending memory decoding them.
    # This is a real memory guard, not red tape: a JPEG is compressed on disk
    # but not in RAM, and once decoded to float32 it can be a hundred times
    # larger. On the 8 GB laptop this project must also run on, one careless
    # upload could otherwise exhaust memory.
    max_upload_bytes: int = 5 * 1024 * 1024

    # A second, independent guard on the same problem: refuse absurdly large
    # pixel dimensions even if the file itself is small. (A "decompression
    # bomb" is a tiny file that expands enormously.) 40 megapixels is far
    # above any phone camera, and the project's own dataset photos are 18 MP.
    max_image_megapixels: float = 40.0

    # Load the model, and run one throwaway prediction, when the API starts,
    # so the first real user does not wait for it. Set
    # WARM_MODEL_ON_STARTUP=false in .env to skip - useful when running tests
    # that never touch the model, because loading it costs several seconds
    # and a few hundred MB of RAM.
    warm_model_on_startup: bool = True

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------
    @field_validator("database_url")
    @classmethod
    def _validate_database_url(cls, value: str) -> str:
        """Check the URL is PostgreSQL or SQLite, and point it at the right driver."""
        value = value.strip()
        if not value:
            raise ValueError("DATABASE_URL is empty. See backend/.env.example.")
        if value.startswith(SQLITE_PREFIX):
            if value.startswith("sqlite:///./"):
                db_path = PROJECT_ROOT / value.replace("sqlite:///./", "")
                return f"sqlite:///{db_path.as_posix()}"
            elif value.startswith("sqlite:///") and not value.startswith("sqlite:////") and ":" not in value[10:]:
                db_path = PROJECT_ROOT / value.replace("sqlite:///", "")
                return f"sqlite:///{db_path.as_posix()}"
            return value
        if not value.startswith((PLAIN_POSTGRES_PREFIX, PSYCOPG3_POSTGRES_PREFIX)):
            raise ValueError(
                "DATABASE_URL must be a PostgreSQL or SQLite URL starting with "
                f"'{PLAIN_POSTGRES_PREFIX}' or '{SQLITE_PREFIX}'. "
                f"Got: {value.split('://', 1)[0]}://..."
            )
        if value.startswith(PLAIN_POSTGRES_PREFIX):
            return value.replace(PLAIN_POSTGRES_PREFIX, PSYCOPG3_POSTGRES_PREFIX, 1)
        return value

    @field_validator("jwt_secret")
    @classmethod
    def _validate_jwt_secret(cls, value: str) -> str:
        """Refuse to run with the placeholder or an obviously weak secret."""
        value = value.strip()
        if value in ("", "CHANGE_ME"):
            raise ValueError(
                "JWT_SECRET is still the placeholder 'CHANGE_ME'. Anyone could "
                "forge a login token. Generate a real one and put it in "
                "backend/.env:\n"
                '  .venv\\Scripts\\python.exe -c "import secrets; '
                'print(secrets.token_urlsafe(48))"'
            )
        if len(value) < 32:
            raise ValueError(
                f"JWT_SECRET is too short ({len(value)} characters). Use at "
                "least 32 characters of random text. Generate one with:\n"
                '  .venv\\Scripts\\python.exe -c "import secrets; '
                'print(secrets.token_urlsafe(48))"'
            )
        return value

    @field_validator("confidence_threshold")
    @classmethod
    def _validate_confidence_threshold(cls, value: float) -> float:
        """A softmax probability can only ever be between 0 and 1."""
        if not 0.0 < value <= 1.0:
            raise ValueError(
                f"CONFIDENCE_THRESHOLD must be greater than 0 and at most 1.0, "
                f"got {value}."
            )
        return value

    @field_validator("jwt_expire_minutes")
    @classmethod
    def _validate_jwt_expire_minutes(cls, value: int) -> int:
        if value <= 0:
            raise ValueError(
                f"JWT_EXPIRE_MINUTES must be a positive number of minutes, "
                f"got {value}."
            )
        return value

    @field_validator("frontend_url")
    @classmethod
    def _validate_frontend_url(cls, value: str) -> str:
        """CORS needs an origin like ``http://localhost:5173``.

        A trailing slash makes the browser's origin comparison fail, and the
        resulting CORS error in the console does not mention the slash at all.
        Stripping it here saves a genuinely baffling debugging session.
        """
        value = value.strip().rstrip("/")
        if not value.startswith(("http://", "https://")):
            raise ValueError(
                "FRONTEND_URL must start with http:// or https:// - for example "
                f"http://localhost:5173. Got: {value!r}"
            )
        return value


def _load_settings() -> Settings:
    """Build the Settings object, with a helpful message if .env is missing."""
    if not ENV_FILE.exists():
        raise RuntimeError(
            f"Configuration file not found: {ENV_FILE}\n\n"
            "Create it by copying the example, then fill in your real values:\n"
            "  Windows PowerShell :  Copy-Item backend\\.env.example backend\\.env\n"
            "  Windows CMD        :  copy backend\\.env.example backend\\.env\n"
            "  macOS / Linux      :  cp backend/.env.example backend/.env"
        )
    return Settings()



# Created once, when this module is first imported, and shared everywhere.
settings: Settings = _load_settings()

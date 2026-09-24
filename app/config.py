"""Application settings loaded from environment (pydantic-settings)."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="A27_", extra="ignore")

    # --- Database -----------------------------------------------------------
    database_url: str = "sqlite:///./a27.db"

    # --- LLM backends (classification / extraction) -------------------------
    # Anthropic (paid) — used when anthropic_api_key is set.
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-4-20250514"

    # OpenRouter (free tier available) — used when openrouter_api_key is set.
    # Endpoint: https://openrouter.ai/api/v1 (OpenAI-compatible).
    openrouter_api_key: str = ""
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    openrouter_model: str = "nvidia/nemotron-3-super-120b-a12b:free"
    # Classifier runs on a separate model: Gemini returned
    # 'unclassified' on a valid SAFE where Nemotron scored 0.99.
    openrouter_classification_model: str = (
        "nvidia/nemotron-3-super-120b-a12b:free"
    )
    # Assistant uses a non-reasoning instruction-tuned model.
    # Reasoning models dump chain-of-thought into the response body.
    openrouter_assistant_model: str = (
        "google/gemma-4-31b-it:free"
    )

    # Which LLM backend to prefer when both keys are set: "anthropic" | "openrouter"
    llm_backend_preference: str = "openrouter"

    # ------------------------------------------------------------------
    # LLM tier reporting
    #
    # Demo deployments use OpenRouter's free tier so a fresh checkout
    # runs with no key. Production deployments run on paid models.
    # This method reports which one is active -- it does not change
    # behaviour. See MODEL-TIERS.md.
    # ------------------------------------------------------------------

    def llm_is_free_tier(self) -> bool:
        backend = (self.llm_backend_preference or "").strip().lower()
        if backend == "anthropic":
            return not bool(self.anthropic_api_key)
        if backend == "openrouter":
            if not self.openrouter_api_key:
                return True
            return ":free" in (self.openrouter_model or "")
        # Unknown backend: assume free until proven otherwise
        return True

    classification_min_confidence: float = 0.75
    extraction_min_confidence: float = 0.85

    extraction_llm_min_confidence: float = 0.70

    # --- Clerk (per-user identity for the UI) -------------------------------
    # JWTs are RS256-signed; verification only needs the public JWKS endpoint.
    # No secret key on the backend.
    clerk_publishable_key: str = ""
    clerk_jwks_url: str = ""
    clerk_issuer: str = ""

    # --- Langfuse observability ---------------------------------------------
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    langfuse_host: str = "https://cloud.langfuse.com"
    # Set to "console" to emit traces without network / credentials in dev.
    telemetry_backend: str = "console"

    # --- Security -----------------------------------------------------------
    # KYC/AML and other PII documents are encrypted at rest with this key
    # (Fernet). Access to those rows is role-scoped at the API layer.
    # Retention: 7 years, matching common money-laundering regulations.
    document_encryption_key: str = ""  # base64 32-byte Fernet key
    pii_retention_days: int = 2557  # 7 years

    # --- API auth -------------------------------------------------------
    # Comma-separated allowlist of API keys. Empty means the API fails
    # closed (503 on every route) rather than silently open -- see
    # app.main.require_api_key.
    api_keys: str = ""

    # --- Uploads ----------------------------------------------------------
    # Uploaded originals are persisted here so reviewers (and developers
    # tuning the extractors) can always see the exact document the pipeline
    # processed -- file_url in the DB points at the saved file.
    uploads_dir: str = "uploads"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
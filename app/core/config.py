from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    APP_NAME: str = "RAG EDDI"
    APP_ENV: str = "development"
    APP_PORT: int = 8000
    APP_BASE_URL: str = "http://127.0.0.1:8000"

    DATABASE_URL: str

    GEMINI_API_KEY: str = ""
    CHAT_MODEL: str = "gemini-2.5-flash"
    EMBEDDING_MODEL: str = "text-embedding-004"

    ADMIN_TOKEN: str = "CAMBIAR_TOKEN_ADMIN"
    ADMIN_USERNAME: str = "admin"
    ADMIN_PASSWORD: str = "admin123"
    SESSION_SECRET_KEY: str = "CAMBIAR_SECRETO_MUY_LARGO"

    RAG_TOP_K: int = 8
    RAG_MIN_SCORE: float = 0.20
    RAG_CHUNK_SIZE: int = 1000
    RAG_CHUNK_OVERLAP: int = 120

    CORS_ORIGINS: str = "*"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
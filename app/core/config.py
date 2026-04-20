from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    APP_NAME: str = "RAG EDDI"
    APP_ENV: str = "development"
    APP_PORT: int = 8000
    APP_BASE_URL: str = "http://127.0.0.1:8000"

    DATABASE_URL: str

    GEMINI_API_KEY: str = ""
    CHAT_MODEL: str = "gemini-2.5-flash"
    EMBEDDING_MODEL: str = "gemini-embedding-001"
    VECTOR_DIMENSION: int = 3072

    ADMIN_TOKEN: str = "CAMBIAR_TOKEN_ADMIN"
    ADMIN_USERNAME: str = "admin"
    ADMIN_PASSWORD: str = "admin123"
    SESSION_SECRET_KEY: str = "CAMBIAR_SECRETO_MUY_LARGO"

    RAG_TOP_K: int = 8
    RAG_MIN_SCORE: float = 0.20
    RAG_CHUNK_SIZE: int = 1000
    RAG_CHUNK_OVERLAP: int = 120

    CORS_ORIGINS: str = "http://127.0.0.1:8000,http://localhost:8000"
    CORS_ALLOW_CREDENTIALS: bool = True
    CORS_ALLOW_METHODS: str = "GET,POST,PUT,PATCH,DELETE,OPTIONS"
    CORS_ALLOW_HEADERS: str = "Authorization,Content-Type,X-Requested-With"
    SECURITY_HEADERS_ENABLED: bool = True

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


class Config:
    SQLALCHEMY_DATABASE_URI = os.getenv(
        "DATABASE_URL", "mysql+pymysql://root:@localhost:3306/fiscal_ai?charset=utf8mb4"
    )
    SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True}
    OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
    OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:7b")
    TRANSPARENCIA_API_KEY = os.getenv("TRANSPARENCIA_API_KEY", "")
    COLETA_INICIO = os.getenv("COLETA_INICIO", "2025-01-01")
    IBGE_MUNICIPIO = os.getenv("IBGE_MUNICIPIO", "2111300")
    DATA_DIR = str(BASE_DIR / "data")
    SCHEMA_SQL_PATH = str(BASE_DIR / "sql" / "schema.sql")

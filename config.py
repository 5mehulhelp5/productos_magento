import os
from pathlib import Path
from dotenv import load_dotenv

# Cargar variables de entorno desde .env si existe
ENV_PATH = Path(__file__).resolve().parent / ".env"
if ENV_PATH.exists():
    load_dotenv(dotenv_path=ENV_PATH)

def _get_val(key: str, default: str = "") -> str:
    """Busca en variables de entorno locales (.env) o en st.secrets de Streamlit Cloud."""
    val = os.getenv(key)
    if not val:
        try:
            import streamlit as st
            if key in st.secrets:
                val = str(st.secrets[key])
        except Exception:
            pass
    return val if val is not None else default

class Config:
    MAGENTO_BASE_URL = _get_val("MAGENTO_BASE_URL", "https://www.elauditor.com.ar/rest/V1").rstrip("/")
    MAGENTO_BEARER_TOKEN = _get_val("MAGENTO_BEARER_TOKEN", "")
    
    CONCURRENT_WORKERS = int(_get_val("CONCURRENT_WORKERS", "3"))
    PRODUCTS_PAGE_SIZE = int(_get_val("PRODUCTS_PAGE_SIZE", "500"))
    STOCK_PAGE_SIZE = int(_get_val("STOCK_PAGE_SIZE", "6000"))
    
    GOOGLE_SHEET_ID = _get_val("GOOGLE_SHEET_ID", "")
    GOOGLE_WORKSHEET_NAME = _get_val("GOOGLE_WORKSHEET_NAME", "Productos")
    GOOGLE_SERVICE_ACCOUNT_FILE = _get_val("GOOGLE_SERVICE_ACCOUNT_FILE", "service_account.json")

    @classmethod
    def get_service_account_path(cls) -> Path:
        p = Path(cls.GOOGLE_SERVICE_ACCOUNT_FILE)
        if not p.is_absolute():
            return Path(__file__).resolve().parent / p
        return p

    @classmethod
    def update_env(cls, updates: dict):
        """Actualiza el archivo .env con nuevos valores de configuración."""
        env_data = {}
        if ENV_PATH.exists():
            with open(ENV_PATH, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        env_data[k.strip()] = v.strip()
        
        env_data.update(updates)
        
        with open(ENV_PATH, "w", encoding="utf-8") as f:
            for k, v in env_data.items():
                f.write(f"{k}={v}\n")
        
        # Recargar en os.environ
        load_dotenv(dotenv_path=ENV_PATH, override=True)

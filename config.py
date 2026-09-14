import os
from pathlib import Path
from dotenv import load_dotenv

# Cargar variables de entorno desde .env si existe
ENV_PATH = Path(__file__).resolve().parent / ".env"
if ENV_PATH.exists():
    load_dotenv(dotenv_path=ENV_PATH)

class Config:
    MAGENTO_BASE_URL = os.getenv("MAGENTO_BASE_URL", "https://www.elauditor.com.ar/rest/V1").rstrip("/")
    MAGENTO_BEARER_TOKEN = os.getenv("MAGENTO_BEARER_TOKEN", "")
    
    CONCURRENT_WORKERS = int(os.getenv("CONCURRENT_WORKERS", "5"))
    PRODUCTS_PAGE_SIZE = int(os.getenv("PRODUCTS_PAGE_SIZE", "500"))
    STOCK_PAGE_SIZE = int(os.getenv("STOCK_PAGE_SIZE", "6000"))
    
    GOOGLE_SHEET_ID = os.getenv("GOOGLE_SHEET_ID", "")
    GOOGLE_WORKSHEET_NAME = os.getenv("GOOGLE_WORKSHEET_NAME", "Productos_Magento")
    GOOGLE_SERVICE_ACCOUNT_FILE = os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE", "service_account.json")

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

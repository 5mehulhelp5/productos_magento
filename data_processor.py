import os
import json
import pandas as pd
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Any, Tuple, Optional

DATA_DIR = Path(__file__).resolve().parent / "data"
LAST_SYNC_FILE = DATA_DIR / "last_sync.parquet"
METADATA_FILE = DATA_DIR / "metadata.json"

def adjust_utc_to_argentina_date(dt_str: Any) -> str:
    """
    Resta 3 horas exactas a una fecha string de Magento (UTC)
    y retorna únicamente la FECHA en formato 'YYYY-MM-DD' (Argentina UTC-3).
    """
    if not dt_str or not isinstance(dt_str, str):
        return ""
    try:
        dt = datetime.strptime(dt_str.strip(), "%Y-%m-%d %H:%M:%S")
        dt_arg = dt - timedelta(hours=3)
        return dt_arg.strftime("%Y-%m-%d")
    except Exception:
        try:
            dt = datetime.fromisoformat(dt_str.strip())
            dt_arg = dt - timedelta(hours=3)
            return dt_arg.strftime("%Y-%m-%d")
        except Exception:
            # Fallback básico si viene como string
            return str(dt_str)[:10]

def process_and_merge(
    products_raw: List[Dict[str, Any]],
    stock_raw: List[Dict[str, Any]]
) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """
    Procesa y unifica catálogo de productos y stock:
    - Estado de Producto: 1 = Habilitado (Visible en Web), 2 = Deshabilitado.
    - Estado de Stock: 1 = Activo, 2 (o diferente de 1) = Inactivo.
    - Fecha: Una sola columna 'Fecha' (YYYY-MM-DD) en hora oficial Argentina.
    """
    # 1. Indexar stock por SKU
    stock_info: Dict[str, Dict[str, Any]] = {}

    for item in stock_raw:
        sku = str(item.get("sku", "")).strip()
        if not sku:
            continue
        
        qty = float(item.get("quantity", 0) or 0)
        stock_status = int(item.get("status", 1) or 0)

        if sku not in stock_info:
            stock_info[sku] = {
                "quantity": qty,
                "status": stock_status
            }
        else:
            stock_info[sku]["quantity"] += qty

    # 2. Procesar productos
    processed_products = []

    for p in products_raw:
        sku = str(p.get("sku", "")).strip()
        if not sku:
            continue

        # Estado del producto en catálogo (1: Habilitado, otro: Deshabilitado)
        prod_status = int(p.get("status", 1) or 0)
        estado_producto = "Habilitado" if prod_status == 1 else "Deshabilitado"

        # Visibilidad
        vis_map = {
            1: "Not visible",
            2: "Catalog",
            3: "Search",
            4: "Catalog + Search"
        }
        try:
            visibility_num = int(p.get("visibility", 4) or 0)
        except (ValueError, TypeError):
            visibility_num = 4
        visibilidad_label = vis_map.get(visibility_num, f"Visibilidad {visibility_num}")

        # Fechas ajustadas a UTC-3 (Argentina) en formato YYYY-MM-DD
        fecha_alta = adjust_utc_to_argentina_date(p.get("created_at"))
        fecha_ult_mod = adjust_utc_to_argentina_date(p.get("updated_at"))

        # Estado de Stock (1: Activo, otro: Inactivo)
        stock_data = stock_info.get(sku, None)
        if stock_data is None:
            stock_qty = 0.0
            stock_status_num = 0
            estado_stock = "Inactivo"
        else:
            stock_qty = stock_data["quantity"]
            stock_status_num = stock_data["status"]
            estado_stock = "Activo" if stock_status_num == 1 else "Inactivo"

        # Habilitado para Venta:
        # stock_qty > 0 AND stock_status_num == 1 AND prod_status == 1 AND visibility_num == 4
        if stock_qty > 0 and stock_status_num == 1 and prod_status == 1 and visibility_num == 4:
            habilitado_para_venta = "SI"
        else:
            habilitado_para_venta = "NO"

        # Precio
        try:
            price_val = float(p.get("price", 0) or 0)
        except (ValueError, TypeError):
            price_val = 0.0

        processed_products.append({
            "SKU": sku,
            "Nombre": p.get("name", ""),
            "Precio": price_val,
            "Estado_Producto": estado_producto,
            "Visibilidad": visibilidad_label,
            "Stock_Total": stock_qty,
            "Estado_Stock": estado_stock,
            "Habilitado_para_Venta": habilitado_para_venta,
            "Fecha_Alta": fecha_alta,
            "Fecha_Ult_Modificacion": fecha_ult_mod
        })

    df_consolidated = pd.DataFrame(processed_products)

    # Métricas de resumen
    summary = {
        "last_sync_datetime": datetime.now().strftime("%d/%m/%Y %H:%M:%S"),
        "total_productos": len(df_consolidated),
        "productos_habilitados": int((df_consolidated["Estado_Producto"] == "Habilitado").sum()) if not df_consolidated.empty else 0,
        "productos_deshabilitados": int((df_consolidated["Estado_Producto"] == "Deshabilitado").sum()) if not df_consolidated.empty else 0,
        "habilitados_para_venta": int((df_consolidated["Habilitado_para_Venta"] == "SI").sum()) if not df_consolidated.empty else 0,
        "stock_total_unidades": float(df_consolidated["Stock_Total"].sum()) if not df_consolidated.empty else 0.0
    }

    # Guardar automáticamente como última actualización local
    save_last_sync(df_consolidated, summary)

    return df_consolidated, summary

def save_last_sync(df: pd.DataFrame, summary: Dict[str, Any]):
    """Persiste los datos de la última sincronización en disco."""
    DATA_DIR.mkdir(exist_ok=True)
    df.to_parquet(LAST_SYNC_FILE, index=False)
    with open(METADATA_FILE, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

def load_last_sync() -> Tuple[Optional[pd.DataFrame], Optional[Dict[str, Any]]]:
    """Carga los datos de la última sincronización si existen."""
    if LAST_SYNC_FILE.exists() and METADATA_FILE.exists():
        try:
            df = pd.read_parquet(LAST_SYNC_FILE)
            with open(METADATA_FILE, "r", encoding="utf-8") as f:
                metadata = json.load(f)
            return df, metadata
        except Exception:
            return None, None
    return None, None

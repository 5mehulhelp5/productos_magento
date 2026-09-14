import sys
import time
from pathlib import Path
from config import Config
from magento_client import MagentoClient
from data_processor import process_and_merge
from sheets_client import GoogleSheetsClient

def main():
    print("=" * 60)
    print("  AUDITOR: SINCRONIZADOR MAGENTO 2 -> GOOGLE SHEETS (CLI)")
    print("=" * 60)

    if not Config.MAGENTO_BEARER_TOKEN or Config.MAGENTO_BEARER_TOKEN == "tu_token_aqui":
        print("\n❌ Error: MAGENTO_BEARER_TOKEN no configurado en .env.")
        sys.exit(1)

    client = MagentoClient(Config.MAGENTO_BASE_URL, Config.MAGENTO_BEARER_TOKEN)

    print("\n[1/4] Verificando conexion con Magento...")
    conn = client.test_connection()
    if not conn["success"]:
        print(f"❌ Fallo de conexion: {conn['message']}")
        sys.exit(1)
    print(f"✅ Conexion OK. Total en catalogo: {conn['total_count']} productos.")

    print(f"\n[2/4] Descargando productos ({Config.CONCURRENT_WORKERS} workers en paralelo)...")
    start_t = time.time()
    def on_prod(current, total, msg):
        print(f"\r  -> [{current}/{total}] {msg}", end="", flush=True)

    products = client.fetch_all_products(
        page_size=Config.PRODUCTS_PAGE_SIZE,
        max_workers=Config.CONCURRENT_WORKERS,
        on_progress=on_prod
    )
    print(f"\n  Total productos descargados: {len(products)}")

    print("\n[3/4] Descargando inventario de stock (source-items)...")
    def on_stock(current, total, msg):
        print(f"\r  -> {msg}", end="", flush=True)

    stock = client.fetch_all_stock(
        page_size=Config.STOCK_PAGE_SIZE,
        on_progress=on_stock
    )
    print(f"\n  Total registros de stock descargados: {len(stock)}")

    print("\n[4/4] Procesando cruce, fechas (UTC-3 Arg) y estados...")
    df_consolidated, summary = process_and_merge(products, stock)

    elapsed = round(time.time() - start_t, 1)
    print("\n" + "-" * 40)
    print(f" RESUMEN DE PROCESO (Tiempo: {elapsed}s)")
    print("-" * 40)
    print(f" - Total productos:            {summary['total_productos']:,}")
    print(f" - Habilitados (Web):          {summary['productos_habilitados']:,}")
    print(f" - Deshabilitados:             {summary['productos_deshabilitados']:,}")
    print(f" - Habilitados para Venta:     {summary['habilitados_para_venta']:,}")
    print(f" - Stock Total Unidades:       {summary['stock_total_unidades']:,.0f}")
    print("-" * 40)

    # Exportar siempre copia local de seguridad
    output_dir = Path(__file__).resolve().parent / "exports"
    output_dir.mkdir(exist_ok=True)
    timestamp = time.strftime("%Y%m%d_%H%M")
    excel_path = output_dir / f"productos_magento_{timestamp}.xlsx"
    df_consolidated.to_excel(excel_path, index=False)
    print(f"💾 Respaldo local guardado en: {excel_path.name}")

    # Subir a Google Sheets si está configurado
    if Config.GOOGLE_SHEET_ID and Config.get_service_account_path().exists():
        print(f"\n📤 Subiendo a Google Sheet ({Config.GOOGLE_SHEET_ID})...")
        sheets_client = GoogleSheetsClient(Config.get_service_account_path(), Config.GOOGLE_SHEET_ID)
        res = sheets_client.upload_dataframe(df_consolidated, Config.GOOGLE_WORKSHEET_NAME)
        if res["success"]:
            print(f"✅ {res['message']}")
        else:
            print(f"⚠️ Google Sheets aviso: {res['message']}")
    else:
        print("\nℹ️ Google Sheets pendiente de credenciales (datos guardados localmente).")

    print("\n🎉 Proceso completado exitosamente.")

if __name__ == "__main__":
    main()

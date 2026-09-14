import io
import time
import streamlit as st
import pandas as pd
from pathlib import Path

from config import Config
from magento_client import MagentoClient
from data_processor import process_and_merge, load_last_sync
from sheets_client import GoogleSheetsClient

st.set_page_config(
    page_title="Auditor | Catálogo & Stock Magento",
    page_icon="📦",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Estilos CSS modernos y limpios
st.markdown("""
<style>
    .main-header {
        font-size: 2.2rem;
        font-weight: 700;
        color: var(--text-color);
        margin-bottom: 0.2rem;
    }
    .sub-header {
        font-size: 1.05rem;
        color: var(--text-color);
        opacity: 0.75;
        margin-bottom: 1.2rem;
    }
    .sync-badge {
        display: inline-flex;
        align-items: center;
        background-color: rgba(59, 130, 246, 0.12);
        border: 1px solid rgba(59, 130, 246, 0.35);
        color: var(--text-color);
        padding: 0.4rem 0.8rem;
        border-radius: 6px;
        font-weight: 600;
        font-size: 0.95rem;
        margin-bottom: 1.2rem;
    }
    .stButton>button {
        border-radius: 8px;
        font-weight: 600;
    }
</style>
""", unsafe_allow_html=True)

# Intentar cargar datos de la última sincronización al abrir la página
if "df_consolidated" not in st.session_state:
    df_loaded, summary_loaded = load_last_sync()
    st.session_state.df_consolidated = df_loaded
    st.session_state.summary = summary_loaded

# --- SIDEBAR: ESTADO DE SISTEMA ---
with st.sidebar:
    st.image("https://img.icons8.com/color/96/magento.png", width=64)
    st.title("Web Auditor")
    st.caption("Control de Catálogo y Stock")
    st.divider()

    st.subheader("🔌 Estado de los Servicios")
    
    # Validar Magento
    has_token = bool(Config.MAGENTO_BEARER_TOKEN and Config.MAGENTO_BEARER_TOKEN != "tu_token_aqui")
    if has_token:
        st.success("Magento 2 API: Conectado ✅")
    else:
        st.error("Magento 2 API: Token no detectado ❌")

    # Validar Google Sheets
    sheets_ready = Config.get_service_account_path().exists() and bool(Config.GOOGLE_SHEET_ID)
    if sheets_ready:
        st.success("Google Sheets: Conectado ✅")
        st.caption(f"Hoja destino: **{Config.GOOGLE_WORKSHEET_NAME}**")
    else:
        st.warning("Google Sheets: Credenciales pendientes ⚠️")

    st.divider()
    st.caption("Versión 1.0 - Modo Producción")

# --- HEADER Y ESTADO PRINCIPAL ---
st.markdown('<div class="main-header">📦 Catálogo de Productos y Existencias</div>', unsafe_allow_html=True)
st.markdown('<div class="sub-header">Consulta en tiempo real del catálogo de Magento 2 con sincronización a Google Sheets.</div>', unsafe_allow_html=True)

# Mostrar fecha de la última actualización si existe
if st.session_state.summary and "last_sync_datetime" in st.session_state.summary:
    last_date = st.session_state.summary["last_sync_datetime"]
    st.markdown(f'<div class="sync-badge">🕒 Última actualización: {last_date} hs (Hora Argentina)</div>', unsafe_allow_html=True)
else:
    st.info("ℹ️ Aún no se ha realizado ninguna sincronización. Presiona el botón a continuación para descargar los datos por primera vez.")

# --- BOTÓN DE ACTUALIZACIÓN ---
col_sync, col_space = st.columns([1, 2])
with col_sync:
    btn_sync = st.button("🔄 Actualizar Datos Ahora (Sincronizar Magento)", type="primary", use_container_width=True)

if btn_sync:
    if not has_token:
        st.error("❌ No se encontró el Token de Magento configurado en el archivo `.env`.")
    else:
        magento = MagentoClient(Config.MAGENTO_BASE_URL, Config.MAGENTO_BEARER_TOKEN)
        progress_bar = st.progress(0.0)
        status_text = st.empty()
        t0 = time.time()

        try:
            # 1. Productos
            def prog_prod(completed, total, msg):
                ratio = (completed / total) * 0.7 if total > 0 else 0
                progress_bar.progress(min(ratio, 0.7))
                status_text.text(msg)

            status_text.info("Descargando catálogo de productos...")
            prods = magento.fetch_all_products(
                page_size=Config.PRODUCTS_PAGE_SIZE,
                max_workers=Config.CONCURRENT_WORKERS,
                on_progress=prog_prod
            )

            # 2. Stock
            def prog_stock(completed, total, msg):
                ratio = 0.7 + (completed / total) * 0.25 if total > 0 else 0.7
                progress_bar.progress(min(ratio, 0.95))
                status_text.text(msg)

            status_text.info("Descargando inventario de existencias (source-items)...")
            stock = magento.fetch_all_stock(
                page_size=Config.STOCK_PAGE_SIZE,
                on_progress=prog_stock
            )

            # 3. Procesar y Guardar localmente
            status_text.text("Consolidando información y ajustando horario de Argentina...")
            df_cons, summary = process_and_merge(prods, stock)

            st.session_state.df_consolidated = df_cons
            st.session_state.summary = summary

            elapsed = round(time.time() - t0, 1)
            progress_bar.progress(1.0)
            status_text.success(f"✅ ¡Actualización finalizada con éxito en {elapsed} segundos! ({len(df_cons)} productos procesados)")
            time.sleep(1)
            st.rerun()

        except Exception as e:
            status_text.empty()
            st.error(f"❌ Error durante la actualización: {str(e)}")

# --- SI HAY DATOS CARGADOS (ÚLTIMA SYNC O RECIÉN SINCRONIZADOS) ---
if st.session_state.df_consolidated is not None:
    df = st.session_state.df_consolidated
    summ = st.session_state.summary

    st.divider()

    # Tarjetas de Métricas de Negocio
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric(
        "Total Productos",
        f"{summ.get('total_productos', len(df)):,}",
        help="Total general de productos registrados en el catálogo de Magento, sin aplicar ningún filtro."
    )
    c2.metric(
        "Habilitados (Web)",
        f"{summ.get('productos_habilitados', 0):,}",
        help="Cantidad de productos del total que se visualizan en la web."
    )
    c3.metric(
        "Deshabilitados",
        f"{summ.get('productos_deshabilitados', 0):,}",
        help="Cantidad de productos del total que no se visualizan en la web."
    )
    c4.metric(
        "Habilitados p/ Venta",
        f"{summ.get('habilitados_para_venta', 0):,}",
        help="Productos disponibles para compra : están habilitados, visibles en Catalog/Search y cuentan con stock activo"
    )
    c5.metric(
        "Stock Total (U)",
        f"{summ.get('stock_total_unidades', 0):,.0f}",
        help="Suma total de unidades físicas de stock acumuladas."
    )

    st.write("")

    # Acciones de Exportación
    col_upload, col_excel, col_csv = st.columns([2, 1, 1])

    with col_upload:
        if st.button("📤 Subir / Actualizar Google Sheets", type="primary", use_container_width=True):
            if not sheets_ready:
                st.error("No se puede subir a Google Sheets: falta configurar el archivo service_account.json o el ID del Sheet.")
            else:
                with st.spinner("Escribiendo datos masivamente en Google Sheets..."):
                    sheets = GoogleSheetsClient(Config.get_service_account_path(), Config.GOOGLE_SHEET_ID)
                    res = sheets.upload_dataframe(df, Config.GOOGLE_WORKSHEET_NAME)
                    if res["success"]:
                        st.success(f"🎉 {res['message']}")
                        st.markdown(f"[👉 Abrir Google Sheet en el navegador](https://docs.google.com/spreadsheets/d/{Config.GOOGLE_SHEET_ID}/edit)")
                    else:
                        st.error(f"❌ {res['message']}")

    with col_excel:
        excel_buf = io.BytesIO()
        with pd.ExcelWriter(excel_buf, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name="Productos")
        excel_buf.seek(0)
        st.download_button(
            label="📥 Descargar Excel (.xlsx)",
            data=excel_buf,
            file_name=f"productos_magento_{time.strftime('%Y%m%d_%H%M')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True
        )

    with col_csv:
        csv_bytes = df.to_csv(index=False, sep=";").encode("utf-8-sig")
        st.download_button(
            label="📥 Descargar CSV",
            data=csv_bytes,
            file_name=f"productos_magento_{time.strftime('%Y%m%d_%H%M')}.csv",
            mime="text/csv",
            use_container_width=True
        )

    st.divider()

    # Buscador y Filtros
    f_col1, f_col2, f_col3, f_col4 = st.columns([2, 1, 1, 1])
    with f_col1:
        search = st.text_input("🔍 Buscar por SKU o Nombre:", "")
    with f_col2:
        estado_prod_filter = st.selectbox("Estado Producto:", ["Todos", "Habilitado", "Deshabilitado"])
    with f_col3:
        hab_venta_options = ["Todos", "SI", "NO"] if "Habilitado_para_Venta" in df.columns else ["Todos"]
        hab_venta_filter = st.selectbox("Habilitado p/ Venta:", hab_venta_options)
    with f_col4:
        col_fecha_ref = "Fecha_Ult_Modificacion" if "Fecha_Ult_Modificacion" in df.columns else ("Fecha" if "Fecha" in df.columns else None)
        if col_fecha_ref:
            fechas_unicas = ["Todas"] + sorted([str(f) for f in df[col_fecha_ref].dropna().unique() if str(f).strip()], reverse=True)
            fecha_filter = st.selectbox("Filtrar Fecha Modif.:", fechas_unicas)
        else:
            col_fecha_ref = None
            fecha_filter = "Todas"

    # Aplicar filtros
    filtered_df = df
    if search:
        filtered_df = filtered_df[
            filtered_df["SKU"].str.contains(search, case=False, na=False) |
            filtered_df["Nombre"].str.contains(search, case=False, na=False)
        ]
    if estado_prod_filter != "Todos" and "Estado_Producto" in filtered_df.columns:
        filtered_df = filtered_df[filtered_df["Estado_Producto"] == estado_prod_filter]
    if hab_venta_filter != "Todos" and "Habilitado_para_Venta" in filtered_df.columns:
        filtered_df = filtered_df[filtered_df["Habilitado_para_Venta"] == hab_venta_filter]
    if col_fecha_ref and fecha_filter != "Todas":
        filtered_df = filtered_df[filtered_df[col_fecha_ref] == fecha_filter]

    st.caption(f"Mostrando **{len(filtered_df):,}** de **{len(df):,}** productos")
    st.dataframe(filtered_df, use_container_width=True, height=500)

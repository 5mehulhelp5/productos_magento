# Auditor - Sincronizador de Catálogo y Stock Magento 2 a Google Sheets

Herramienta en Python con interfaz interactiva (Streamlit) para consultar el catálogo de Magento 2 en paralelo, verificar disponibilidad y visibilidad, auditar existencias y exportar a Google Sheets o Excel.

## 🚀 Características

- **Descarga concurrente:** Consulta paralela mediante hilos (5 workers) para procesar catálogos grandes (~13.000 productos) en menos de 40 segundos.
- **Ajuste horario oficial:** Conversión de fechas de UTC a hora Argentina (UTC-3).
- **Control de visibilidad y estado de venta:** Identifica productos habilitados para venta directa (`Stock > 0`, `Stock Status = 1`, `Status = 1`, `Visibilidad = 4`).
- **Persistencia local:** Carga instantánea de la última sincronización al abrir la web sin recargar Magento.
- **Subida atómica por lote:** Escritura masiva a Google Sheets (`batchUpdate`) respetando cuotas de API.

## 🛠️ Instalación y Uso

1. Clonar el repositorio:
   ```bash
   git clone <URL_DEL_REPOSITORIO>
   cd productos_magento
   ```

2. Instalar dependencias:
   ```bash
   pip install -r requirements.txt
   ```

3. Configurar credenciales:
   - Copiar el archivo de plantilla:
     ```bash
     cp .env.example .env
     ```
   - Completar en `.env` el `MAGENTO_BEARER_TOKEN` y el `GOOGLE_SHEET_ID`.
   - Colocar el archivo `service_account.json` de Google Cloud en la raíz del proyecto.

4. Iniciar la aplicación web:
   - En Windows: doble clic en `run_app.bat` o ejecutar:
     ```bash
     python -m streamlit run app.py
     ```

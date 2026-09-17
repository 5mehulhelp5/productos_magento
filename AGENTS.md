# Contexto del Proyecto y Decisiones de Arquitectura (AGENTS.md)

Este documento contiene la memoria técnica, el contexto de negocio y las razones detrás de cada decisión arquitectónica de este proyecto, estructurado de acuerdo a la **Regla Global de Preservación de Contexto**. Su objetivo es permitir que cualquier desarrollador o agente de Inteligencia Artificial comprenda inmediatamente el porqué de cada línea de código y continúe el trabajo sin depender del historial de chat.

---

## 1. Propósito y Alcance

* **Problema que resuelve:** La empresa (**El Auditor**) requiere un sistema centralizado para consultar periódicamente el catálogo completo (~13.000 a 14.000 productos) y sus existencias físicas desde **Magento 2**, cruzar ambos endpoints, normalizar fechas y estados comerciales, auditar su disponibilidad real para venta al público y volcar el resultado de forma masiva a **Google Sheets** (y respaldos en Excel/CSV).
* **Usuarios y destinatarios:** Áreas comerciales, de auditoría de inventario y compras de El Auditor.
* **Límites funcionales:** El sistema es de lectura y auditoría (extracción desde Magento y exportación hacia Sheets/Excel); no realiza modificaciones ni altas de productos en el catálogo de Magento por el momento (las limpiezas de registros erróneos se realizan por scripts independientes o panel de Magento).

---

## 2. Preparación, Ejecución y Validación

### Requisitos
* Python 3.10 o superior (validado en Python 3.14).
* Conexión a internet con acceso a `elauditor.com.ar` y a las APIs de Google Cloud.

### Instalación de Dependencias
Ejecutar en la raíz del proyecto:
```bash
pip install -r requirements.txt
```

### Variables de Entorno y Configuración
El sistema soporta ejecución dual:
1. **Entorno Local (`.env` y `service_account.json`):**
   * Crear archivo `.env` a partir de `.env.example`:
     - `MAGENTO_BASE_URL`: URL base de la API REST (por defecto: `https://www.elauditor.com.ar/rest/V1`).
     - `MAGENTO_BEARER_TOKEN`: Integration token fijo de Magento 2.
     - `GOOGLE_SHEET_ID`: ID de la hoja de cálculo de Google.
     - `GOOGLE_WORKSHEET_NAME`: Nombre de la pestaña destino (ej: `Productos`).
     - `CONCURRENT_WORKERS`: Cantidad de hilos de descarga (valor: `3` a `5`).
     - `PRODUCTS_PAGE_SIZE`: Tamaño de lote de catálogo (valor: `500`).
     - `STOCK_PAGE_SIZE`: Tamaño de lote de existencias (valor: `6000`).
   * Colocar en la raíz del proyecto el archivo `service_account.json` descargado de Google Cloud Console.
2. **Entorno en la Nube (Streamlit Community Cloud):**
   * Configurar en la sección **Secrets** de la app los valores anteriores y el bloque `[gcp_service_account]` con el contenido del JSON de la cuenta de servicio.

### Comandos de Ejecución
* **Modo Web Interactivo (Streamlit):**
  - Windows: Doble clic en `run_app.bat` o:
    ```bash
    python -m streamlit run app.py
    ```
  - Acceso por defecto: `http://localhost:8501`.
* **Modo Desatendido / Programado (CLI):**
  ```bash
  python sync_cli.py
  ```

### Verificación y Validación
* Para verificar la compilación y lógica de procesamiento:
  ```bash
  python -c "import app, data_processor, magento_client, sheets_client; print('OK')"
  ```
* Probar la conexión a Magento y Google Sheets desde los indicadores de estado de la barra lateral de la app web.

---

## 3. Arquitectura y Decisiones Relevantes

### A. Python + Streamlit vs Google Apps Script Puro
* **Alternativa descartada:** Google Apps Script corriendo internamente en Google Sheets.
* **Motivo del descarte:** Apps Script tiene un límite infranqueable de **6 minutos** de tiempo de ejecución y cuota estricta de memoria. Para 13.000 productos son 26 llamadas pesadas a Magento; Apps Script tardaría entre 4 y 6 minutos solo en transferir datos por red, con altísimo riesgo de error `504 Gateway Timeout` y fallos irrecuperables.
* **Solución adoptada:** Python ejecuta en local/cloud, procesa en memoria con Pandas en <1 segundo y escribe los 13.000 registros en un único bloque atómico (`batchUpdate`) en 3 a 5 segundos.

### B. Concurrencia y Cantidad de Workers (Hilos)
* **Valor configurado:** 3 a 5 workers concurrentes (`ThreadPoolExecutor`).
* **Motivo técnico:** Magento 2 corre sobre PHP-FPM y MySQL. Abrir 20 o más hilos con consultas de 500 productos satura los procesos PHP del servidor de producción, pudiendo degradar la navegación de los clientes reales de `elauditor.com.ar`. Con 3-5 hilos, la descarga completa toma **~35 a 40 segundos** con carga despreciable sobre el servidor.

### C. Autenticación de Google Sheets sin Costos
* Se utiliza una **Cuenta de Servicio (Service Account)** gratuita de Google Cloud. No requiere vincular tarjetas de crédito ni facturación.
* La hoja de cálculo se comparte al correo del robot (`magento-sync@global-bridge-...iam.gserviceaccount.com`) con rol de **Editor**.
* Se utiliza `worksheet.clear()` seguido de `worksheet.update('A1', data_matrix)` para no agotar la cuota de 60 peticiones/minuto de la API de Google.

---

## 4. Reglas de Negocio y Mapeos de Dominio

### A. Desfase Horario de Argentina (UTC a UTC-3)
* **Problema detectado:** Magento almacena fechas (`created_at`, `updated_at`) en formato UTC (+0). Al estar Argentina en UTC-3, los productos editados al final de la tarde o noche figuraban con fecha del día siguiente.
* **Regla aplicada:** `adjust_utc_to_argentina_date()` resta **3 horas exactas** antes de formatear.
* **Formato adoptado:** Formato estándar `YYYY-MM-DD` en dos columnas separadas:
  - `Fecha_Alta`: Fecha de creación en catálogo.
  - `Fecha_Ult_Modificacion`: Fecha de última actualización.
  Se prescinde de la hora para permitir filtros directos y agrupaciones por día.

### B. Particularidad del Stock en Magento 2 (MSI)
* **Problema detectado:** En Magento 2, si un registro de stock tiene `status = 2` (Inactivo), aunque tenga unidades físicas en el depósito (ej: `quantity = 15`), en la tienda web desaparecen los botones *"Comprar"* y *"Agregar al carrito"* y el producto figura como **"Sin Stock"**.
* **Mapeo:**
  - `Estado_Stock`: `Activo` si `status = 1`; `Inactivo` si `status = 2` o distinto de 1.
  - `Stock_Total`: Mantiene la sumatoria física real de unidades para auditoría del depósito.

### C. Visibilidad del Catálogo
El endpoint de productos expone el campo numérico `visibility`:
* `1` ➔ `Not visible`
* `2` ➔ `Catalog`
* `3` ➔ `Search`
* `4` ➔ `Catalog + Search` (Visible tanto en listados como en buscador).

### D. Regla de Oro: `Habilitado_para_Venta`
Un producto se marca con **`Habilitado_para_Venta = "SI"`** únicamente si cumple **simultáneamente 4 condiciones**:
1. `Stock_Total > 0` (Tiene existencias físicas).
2. `Estado_Stock == 1` (El stock está en estado Activo).
3. `Estado_Producto == 1` (El producto está Habilitado en el catálogo).
4. `Visibilidad == 4` (Configurado como `Catalog + Search`).

Si cualquiera de las 4 falla ➔ `"NO"`.

---

## 5. Datos e Integraciones

### Origen de Datos: Magento 2 REST API
* **Autenticación:** Bearer Token fijo de integración.
* **Endpoint 1 (Productos):**  
  `/rest/V1/products?searchCriteria[pageSize]=500&searchCriteria[currentPage]={page}&fields=items[sku,price,name,status,visibility,created_at,updated_at]`  
  - Paginado dinámico: primero se consulta `total_count` para calcular total de páginas y se disparan peticiones en paralelo con `ThreadPoolExecutor`.
* **Endpoint 2 (Stock MSI):**  
  `/rest/V1/inventory/source-items?searchCriteria[pageSize]=6000&searchCriteria[currentPage]={page}`  
  - Descarga ultrarrápida (~1 segundo por lote de 6.000 ítems).
* **Depuración de Duplicados en Stock:** Inicialmente se detectaron duplicados en `source-items` que fueron auditados y purgados directamente vía API. La app realiza una agregación defensiva (`stock_info[sku]["quantity"] += qty`) para asegurar integridad.

### Destino de Datos y Persistencia
* **Google Sheets:** Conexión vía `gspread` con subida por bloque (`batchUpdate`) en la pestaña configurada.
* **Caché Local:**
  - `data/last_sync.parquet`: Almacenamiento columnar comprimido de lectura instantánea.
  - `data/metadata.json`: Registro de métricas y fecha/hora exacta de la última sincronización.
  - Al abrir o recargar la aplicación web, se carga este archivo local de inmediato para no saturar Magento.
* **Exportaciones Locales:** Generación bajo demanda de archivos Excel (`.xlsx`) y CSV (`utf-8-sig`).

---

## 6. Mapa del Proyecto

Todas las rutas son relativas a la raíz del repositorio:

| Archivo / Directorio | Responsabilidad |
|---|---|
| [`app.py`](app.py) | Interfaz web interactiva en Streamlit: métricas con tooltips `(?)`, filtros dinámicos, tabla interactiva, botones de exportación y subida. |
| [`magento_client.py`](magento_client.py) | Cliente HTTP con concurrencia controlada (`ThreadPoolExecutor`) y paginación para `/products` y `/inventory/source-items`. |
| [`data_processor.py`](data_processor.py) | Motor de cruce en memoria (Pandas), ajuste de horario UTC-3, cálculo de `Habilitado_para_Venta` y persistencia en `data/`. |
| [`sheets_client.py`](sheets_client.py) | Conexión y subida masiva en bloque (`batchUpdate`) con Google Sheets (soporta credenciales locales y de Streamlit Cloud Secrets). |
| [`config.py`](config.py) | Carga unificada de parámetros desde variables de entorno local (`.env`) o secretos en la nube (`st.secrets`). |
| [`sync_cli.py`](sync_cli.py) | Ejecución desatendida por línea de comandos para tareas programadas (Task Scheduler). |
| [`run_app.bat`](run_app.bat) | Lanzador ejecutable con doble clic para Windows. |
| [`requirements.txt`](requirements.txt) | Lista de dependencias de Python fijadas. |
| [`.env.example`](.env.example) | Plantilla de configuración con variables de entorno requeridas. |
| [`.gitignore`](.gitignore) | Exclusión obligatoria de credenciales (`.env`, `service_account.json`), cachés y archivos de datos. |

---

## 7. Indicaciones de Trabajo y Restricciones

1. **Seguridad Estricta de Secretos:**  
   Bajo ninguna circunstancia subir archivos `.env` o `service_account.json` al repositorio Git. Si se despliega en Streamlit Cloud, usar siempre `st.secrets`.
2. **Uso Exclusivo de Rutas Relativas:**  
   Toda referencia a archivos en documentación o código debe ser relativa (`[app.py](app.py)`), nunca absoluta con letras de unidad de Windows (`C:\Users\...`).
3. **Mantenimiento de Documentación:**  
   Cualquier cambio futuro en los endpoints, reglas de cálculo de venta, campos solicitados a Magento o variables de configuración **debe actualizarse inmediatamente en este archivo `AGENTS.md`** antes de finalizar la tarea.

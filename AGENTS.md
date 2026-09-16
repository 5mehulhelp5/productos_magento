# Contexto del Proyecto y Decisiones de Arquitectura (AGENTS.md)

Este documento contiene la memoria técnica, el contexto de negocio y las razones detrás de cada decisión arquitectónica de este proyecto. Su objetivo es permitir que cualquier desarrollador o agente de Inteligencia Artificial que trabaje en este repositorio comprenda inmediatamente el porqué de cada línea de código sin depender de historiales de chat previos.

---

## 1. Propósito del Sistema
La empresa (**El Auditor**) requiere un sistema para consultar periódicamente el catálogo completo (~13.000 a 14.000 productos) y sus existencias físicas desde **Magento 2**, cruzar ambos endpoints, normalizar fechas y estados comerciales, y volcar el resultado de forma masiva a **Google Sheets** (y respaldos en Excel/CSV), ofreciendo además una interfaz web amigable con **Streamlit** y ejecutable autónomo por consola (CLI).

---

## 2. Decisiones Arquitectónicas y Justificación Técnica

### ¿Por qué Python + Streamlit en lugar de Google Apps Script puro?
* **Problema:** Google Apps Script corre en la infraestructura de Google y tiene un límite estricto de **6 minutos** de ejecución por script.
* **Cálculo:** Para 13.000 productos a 500 por página son 26 peticiones HTTP pesadas de productos + peticiones de stock. Apps Script tardaría entre 4 y 6 minutos solo en descargar los datos, con alto riesgo de error `504 Timeout` o corte abrupto por cuota de tiempo y memoria.
* **Solución:** Python permite procesamiento multihilo en memoria con **Pandas**, descarga en paralelo y escribe en Google Sheets mediante un único bloque atómico (`batchUpdate`) en 3 a 5 segundos.

### Concurrencia y Cantidad de Workers (Hilos)
* **Configuración:** Entre 3 y 5 hilos simultáneos (`ThreadPoolExecutor`).
* **¿Por qué no 20 o 50 hilos?**  
  El servidor de Magento 2 corre sobre PHP-FPM y MySQL. Lanzar 20 o más peticiones concurrentes de 500 productos con joins de base de datos satura los workers de PHP del servidor de producción de la tienda, pudiendo ralentizar la navegación de los clientes reales en `elauditor.com.ar` o provocar errores `502 Bad Gateway`. Con 3 a 5 hilos, el catálogo completo se descarga en **~35 a 40 segundos** con impacto nulo en el servidor.
* **Tamaños de página:**
  - `/products`: `pageSize = 500` (~8 segundos por llamada).
  - `/inventory/source-items`: `pageSize = 6000` (~1 segundo por llamada).

### Integración con Google Sheets sin Tarjetas ni Costos
* Se utiliza una **Cuenta de Servicio (Service Account)** de Google Cloud gratuita. No requiere tarjeta de crédito ni facturación.
* **Permisos:** La hoja de cálculo se comparte con el email del robot (`magento-sync@global-bridge-...iam.gserviceaccount.com`) con rol de **Editor**.
* **Escritura Batch:** Se utiliza `worksheet.clear()` seguido de `worksheet.update('A1', data_matrix)` para no agotar la cuota de 60 peticiones/minuto de la API de Google.

### Soporte Dual de Credenciales (Local vs Streamlit Cloud)
* **Localmente:** Lee desde `.env` y el archivo físico `service_account.json`.
* **En Streamlit Cloud:** Lee desde `st.secrets` (sección `[gcp_service_account]`), permitiendo desplegar la app en la nube sin exponer archivos de claves en GitHub.

---

## 3. Particularidades del Negocio y Reglas de Dominio (Magento 2)

### A. Desfase Horario de Argentina (UTC a UTC-3)
* **Problema detectado:** Magento guarda los campos `created_at` y `updated_at` en formato UTC (hora 0). Como Argentina está en UTC-3, los productos modificados a última hora de la tarde o noche figuraban con fecha del día siguiente.
* **Regla aplicada:** La función `adjust_utc_to_argentina_date()` resta **3 horas exactas** antes de formatear la fecha.
* **Formato adoptado:** Se dejan dos columnas separadas:
  - `Fecha_Alta`: Fecha de creación (`YYYY-MM-DD`).
  - `Fecha_Ult_Modificacion`: Fecha del último cambio (`YYYY-MM-DD`).
  Se utiliza solo la fecha sin la hora para permitir filtros y agrupaciones limpias en Sheets y en la web.

### B. Comportamiento del Stock en Magento 2 (MSI)
* **Problema detectado:** En Magento 2, si un registro de stock tiene `status = 2` (Inactivo), aunque tenga unidades físicas en el depósito (ej: `quantity = 15`), en la tienda web desaparecen los botones *"Comprar"* y *"Agregar al carrito"* y el producto figura como **"Sin Stock"**.
* **Mapeo implementado:**
  - `Estado_Stock`:
    - `Activo` si `status = 1`.
    - `Inactivo` si `status = 2` o distinto de 1.
  - `Stock_Total`: Mantiene la sumatoria física real de unidades para control de auditoría del depósito.

### C. Regla de Oro: `Habilitado_para_Venta`
Para que un producto se considere listo y disponible para la compra directa por los clientes en la tienda web, debe cumplir **simultáneamente 4 condiciones**:
1. `Stock_Total > 0` (Tiene existencias físicas).
2. `Estado_Stock == 1` (El stock está en estado Activo).
3. `Estado_Producto == 1` (El producto está Habilitado en el catálogo).
4. `Visibilidad == 4` (El producto está configurado como `Catalog + Search`).

Si cumple las 4 ➔ Columna `Habilitado_para_Venta = "SI"`. En caso contrario ➔ `"NO"`.

### D. Historial de Duplicados de Stock
Durante el desarrollo se detectó que existían registros duplicados para un mismo SKU en `source-items`. Tras auditar la base, dichos registros fueron depurados y eliminados directamente vía API de Magento, por lo que la pestaña de auditoría inicial se retiró para mantener la app limpia.

---

## 4. Persistencia y Carga Instantánea (Cache Local)
Para evitar tener que consultar la API de Magento cada vez que un usuario abre o recarga la web:
* Los datos de la última sincronización se persisten localmente en:
  - `data/last_sync.parquet` (archivo binario comprimido de lectura ultra rápida).
  - `data/metadata.json` (resumen de métricas y fecha/hora exacta de última actualización).
* Al abrir la web, Streamlit carga estos datos al instante y muestra el banner con la hora oficial argentina de la última sincronización.

---

## 5. Estructura de Módulos y Responsabilidades

| Archivo | Responsabilidad |
|---|---|
| [`app.py`](app.py) | Interfaz visual en Streamlit con métricas, descripciones `(?)`, filtros y botones de subida/descarga. |
| [`magento_client.py`](magento_client.py) | Cliente HTTP con concurrencia controlada (`ThreadPoolExecutor`) y paginación para `/products` y `/inventory/source-items`. |
| [`data_processor.py`](data_processor.py) | Motor de cruce en memoria, ajuste de horario UTC-3, cálculo de `Habilitado_para_Venta` y persistencia en `data/`. |
| [`sheets_client.py`](sheets_client.py) | Conexión y subida masiva en bloque (`batchUpdate`) con Google Sheets (soporta credenciales locales y de Streamlit Cloud). |
| [`config.py`](config.py) | Carga unificada de parámetros desde `.env` o `st.secrets`. |
| [`sync_cli.py`](sync_cli.py) | Ejecución desatendida por línea de comandos para tareas programadas (Task Scheduler). |
| [`run_app.bat`](run_app.bat) | Lanzador con doble clic para Windows. |

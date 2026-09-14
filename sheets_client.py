import os
from pathlib import Path
from typing import Dict, Any, List
import pandas as pd

class GoogleSheetsClient:
    def __init__(self, service_account_path: str, spreadsheet_id: str):
        self.service_account_path = Path(service_account_path)
        self.spreadsheet_id = spreadsheet_id.strip()
        self.scopes = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive"
        ]
        self._gc = None
        self._spreadsheet = None

    def validate_credentials_file(self) -> Dict[str, Any]:
        """Comprueba si el archivo service_account.json existe y es legible."""
        if not self.service_account_path.exists():
            return {
                "success": False,
                "message": f"No se encontró el archivo de credenciales en: {self.service_account_path.name}"
            }
        return {"success": True, "message": "Archivo service_account.json detectado."}

    def connect(self) -> Dict[str, Any]:
        """Valida la conexión y permisos sobre la hoja de cálculo."""
        val = self.validate_credentials_file()
        if not val["success"]:
            return val

        if not self.spreadsheet_id:
            return {
                "success": False,
                "message": "Falta configurar el GOOGLE_SHEET_ID."
            }

        try:
            import gspread
            from google.oauth2.service_account import Credentials

            creds = Credentials.from_service_account_file(
                str(self.service_account_path),
                scopes=self.scopes
            )
            self._gc = gspread.authorize(creds)
            self._spreadsheet = self._gc.open_by_key(self.spreadsheet_id)

            return {
                "success": True,
                "title": self._spreadsheet.title,
                "client_email": creds.service_account_email,
                "message": f"Conectado exitosamente al Sheet: '{self._spreadsheet.title}'"
            }
        except Exception as e:
            err_str = str(e)
            client_email = ""
            try:
                import json
                with open(self.service_account_path, "r", encoding="utf-8") as f:
                    client_email = json.load(f).get("client_email", "")
            except Exception:
                pass

            if "PERMISSION_DENIED" in err_str or "403" in err_str or "The caller does not have permission" in err_str:
                msg = (
                    f"Permiso denegado (403). Debes abrir tu Google Sheet y compartirlo con permiso de EDITOR "
                    f"al correo del robot:\n👉 {client_email}"
                )
            elif "404" in err_str or "SpreadsheetNotFound" in err_str:
                msg = f"No se encontró la hoja con ID '{self.spreadsheet_id}'. Verifica que el ID sea correcto."
            else:
                msg = f"Error al conectar con Google Sheets: {err_str}"

            return {
                "success": False,
                "message": msg,
                "client_email": client_email
            }

    def upload_dataframe(
        self,
        df: pd.DataFrame,
        worksheet_name: str = "Productos_Magento"
    ) -> Dict[str, Any]:
        """
        Sube un DataFrame completo a Google Sheets en una sola operación por lote (Batch).
        """
        conn = self.connect()
        if not conn["success"]:
            return conn

        try:
            # Seleccionar o crear la pestaña
            try:
                worksheet = self._spreadsheet.worksheet(worksheet_name)
            except Exception:
                # Si no existe, crearla con filas y columnas suficientes
                num_rows = max(len(df) + 100, 1000)
                num_cols = max(len(df.columns) + 5, 20)
                worksheet = self._spreadsheet.add_worksheet(title=worksheet_name, rows=num_rows, cols=num_cols)

            # Preparar matriz de datos (reemplazando NaN y valores nulos)
            df_clean = df.fillna("")
            headers = df_clean.columns.tolist()
            # Convertir todas las filas a tipos JSON serializables
            rows = df_clean.astype(str).values.tolist()
            data_matrix = [headers] + rows

            # Limpiar contenido anterior y actualizar en un solo batch
            worksheet.clear()
            worksheet.update(range_name="A1", values=data_matrix, value_input_option="USER_ENTERED")

            # Formatear la primera fila (congelar encabezado)
            try:
                worksheet.freeze(rows=1)
            except Exception:
                pass

            return {
                "success": True,
                "rows_uploaded": len(rows),
                "worksheet": worksheet_name,
                "sheet_title": self._spreadsheet.title,
                "message": f"Se sincronizaron con éxito {len(rows)} filas en la pestaña '{worksheet_name}'."
            }
        except Exception as e:
            return {
                "success": False,
                "message": f"Error durante la subida masiva a Google Sheets: {str(e)}"
            }

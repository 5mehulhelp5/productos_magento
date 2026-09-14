import os
from pathlib import Path
from typing import Dict, Any, List, Tuple, Optional
import pandas as pd

class GoogleSheetsClient:
    def __init__(self, service_account_path: Any, spreadsheet_id: str):
        self.service_account_path = Path(service_account_path) if service_account_path else Path("service_account.json")
        self.spreadsheet_id = spreadsheet_id.strip()
        self.scopes = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive"
        ]
        self._gc = None
        self._spreadsheet = None

    def _get_credentials(self) -> Tuple[Optional[Any], str]:
        """Obtiene credenciales desde st.secrets (Streamlit Cloud) o archivo local."""
        from google.oauth2.service_account import Credentials

        # 1. Probar desde st.secrets de Streamlit Cloud
        try:
            import streamlit as st
            if "gcp_service_account" in st.secrets:
                info = dict(st.secrets["gcp_service_account"])
                creds = Credentials.from_service_account_info(info, scopes=self.scopes)
                return creds, info.get("client_email", "")
        except Exception:
            pass

        # 2. Probar desde archivo local
        if self.service_account_path.exists():
            try:
                creds = Credentials.from_service_account_file(
                    str(self.service_account_path),
                    scopes=self.scopes
                )
                return creds, creds.service_account_email
            except Exception:
                pass

        return None, ""

    def validate_credentials_file(self) -> Dict[str, Any]:
        """Comprueba si existen credenciales válidas."""
        creds, _ = self._get_credentials()
        if creds is None:
            return {
                "success": False,
                "message": "No se encontraron credenciales de Google (ni en secrets ni en service_account.json)"
            }
        return {"success": True, "message": "Credenciales de Google detectadas."}

    def connect(self) -> Dict[str, Any]:
        """Valida la conexión y permisos sobre la hoja de cálculo."""
        if not self.spreadsheet_id:
            return {
                "success": False,
                "message": "Falta configurar el GOOGLE_SHEET_ID."
            }

        try:
            import gspread
            creds, client_email = self._get_credentials()
            if creds is None:
                return {
                    "success": False,
                    "message": "No se encontraron credenciales de Google Service Account."
                }

            self._gc = gspread.authorize(creds)
            self._spreadsheet = self._gc.open_by_key(self.spreadsheet_id)

            return {
                "success": True,
                "title": self._spreadsheet.title,
                "client_email": client_email,
                "message": f"Conectado exitosamente al Sheet: '{self._spreadsheet.title}'"
            }
        except Exception as e:
            err_str = str(e)
            _, client_email = self._get_credentials()

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
        worksheet_name: str = "Productos"
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
                num_rows = max(len(df) + 100, 1000)
                num_cols = max(len(df.columns) + 5, 20)
                worksheet = self._spreadsheet.add_worksheet(title=worksheet_name, rows=num_rows, cols=num_cols)

            # Preparar matriz de datos
            df_clean = df.fillna("")
            headers = df_clean.columns.tolist()
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

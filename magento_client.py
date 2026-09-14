import math
import requests
from typing import List, Dict, Any, Callable, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed

class MagentoClient:
    def __init__(self, base_url: str, token: str, timeout: int = 40):
        self.base_url = base_url.rstrip("/")
        self.token = token.strip()
        self.timeout = timeout

    @property
    def headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
            "Accept": "application/json"
        }

    def test_connection(self) -> Dict[str, Any]:
        """Prueba la conexión a la API de Magento con una consulta mínima."""
        url = f"{self.base_url}/products?searchCriteria[pageSize]=1&searchCriteria[currentPage]=1&fields=total_count"
        try:
            resp = requests.get(url, headers=self.headers, timeout=15)
            if resp.status_code == 200:
                data = resp.json()
                return {
                    "success": True,
                    "total_count": data.get("total_count", 0),
                    "message": "Conexión exitosa con la API de Magento."
                }
            elif resp.status_code == 401:
                return {
                    "success": False,
                    "message": "Error 401: Token Bearer no autorizado o inválido."
                }
            else:
                return {
                    "success": False,
                    "message": f"Error {resp.status_code}: {resp.text[:200]}"
                }
        except Exception as e:
            return {
                "success": False,
                "message": f"Error de red al conectar con Magento: {str(e)}"
            }

    def get_products_total_count(self) -> int:
        """Obtiene el total de productos registrados en el catálogo."""
        url = f"{self.base_url}/products?searchCriteria[pageSize]=1&searchCriteria[currentPage]=1&fields=total_count"
        resp = requests.get(url, headers=self.headers, timeout=self.timeout)
        resp.raise_for_status()
        return int(resp.json().get("total_count", 0))

    def _fetch_products_page(self, page: int, page_size: int) -> List[Dict[str, Any]]:
        """Descarga una página específica de productos."""
        url = (
            f"{self.base_url}/products?"
            f"searchCriteria[pageSize]={page_size}&"
            f"searchCriteria[currentPage]={page}&"
            f"fields=items[sku,price,name,status,visibility,created_at,updated_at]"
        )
        resp = requests.get(url, headers=self.headers, timeout=self.timeout)
        resp.raise_for_status()
        data = resp.json()
        return data.get("items", [])

    def fetch_all_products(
        self,
        page_size: int = 500,
        max_workers: int = 5,
        on_progress: Optional[Callable[[int, int, str], None]] = None
    ) -> List[Dict[str, Any]]:
        """
        Descarga todos los productos en paralelo usando ThreadPoolExecutor.
        """
        total_count = self.get_products_total_count()
        if total_count == 0:
            return []

        total_pages = math.ceil(total_count / page_size)
        all_products = []
        completed_pages = 0

        if on_progress:
            on_progress(0, total_pages, f"Iniciando descarga de {total_count} productos ({total_pages} páginas con {max_workers} hilos)...")

        # Usar ThreadPoolExecutor para concurrencia controlada
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_page = {
                executor.submit(self._fetch_products_page, page, page_size): page
                for page in range(1, total_pages + 1)
            }

            for future in as_completed(future_to_page):
                page_num = future_to_page[future]
                try:
                    items = future.result()
                    all_products.extend(items)
                    completed_pages += 1
                    if on_progress:
                        on_progress(
                            completed_pages,
                            total_pages,
                            f"Descargando productos: Página {completed_pages}/{total_pages} completada (Items acumulados: {len(all_products)})"
                        )
                except Exception as exc:
                    raise RuntimeError(f"Error al descargar página {page_num} de productos: {str(exc)}")

        return all_products

    def _fetch_stock_page(self, page: int, page_size: int) -> Dict[str, Any]:
        """Descarga una página de source-items."""
        url = (
            f"{self.base_url}/inventory/source-items?"
            f"searchCriteria[pageSize]={page_size}&"
            f"searchCriteria[currentPage]={page}"
        )
        resp = requests.get(url, headers=self.headers, timeout=self.timeout)
        resp.raise_for_status()
        return resp.json()

    def fetch_all_stock(
        self,
        page_size: int = 6000,
        on_progress: Optional[Callable[[int, int, str], None]] = None
    ) -> List[Dict[str, Any]]:
        """
        Descarga todos los registros de stock (source-items) paginados.
        Dado que page_size=6000 responde en ~1s, se realiza secuencial o semi-paralelo de forma ultrarrápida.
        """
        if on_progress:
            on_progress(0, 1, "Consultando inventario de stock (source-items)...")

        first_res = self._fetch_stock_page(1, page_size)
        items = first_res.get("items", [])
        total_count = first_res.get("total_count", len(items))

        total_pages = math.ceil(total_count / page_size) if total_count > 0 else 1
        all_stock = list(items)

        if on_progress:
            on_progress(1, total_pages, f"Descargando stock: Página 1/{total_pages} ({len(all_stock)} registros)")

        for page in range(2, total_pages + 1):
            res = self._fetch_stock_page(page, page_size)
            page_items = res.get("items", [])
            all_stock.extend(page_items)
            if on_progress:
                on_progress(page, total_pages, f"Descargando stock: Página {page}/{total_pages} ({len(all_stock)}/{total_count} registros)")

        return all_stock

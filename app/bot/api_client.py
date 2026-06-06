from __future__ import annotations

import httpx
from io import BytesIO

from app.bot.config import API_BASE_URL


class APIClient:
    def __init__(self):
        self.client = httpx.AsyncClient(base_url=API_BASE_URL, timeout=15)

    async def close(self):
        await self.client.aclose()

    async def search_products(self, query: str):
        resp = await self.client.get("/products", params={"query": query, "limit": 10})
        resp.raise_for_status()
        return resp.json()

    async def get_product(self, product_id: int):
        resp = await self.client.get(f"/products/{product_id}")
        resp.raise_for_status()
        return resp.json()

    async def get_inventory(self, product_id: int):
        resp = await self.client.get(f"/inventory/{product_id}")
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return resp.json()

    async def create_sale(self, payload):
        resp = await self.client.post("/sales", json=payload)
        resp.raise_for_status()
        return resp.json()

    async def confirm_sale(self, sale_id: int):
        resp = await self.client.post(f"/sales/{sale_id}/confirm")
        resp.raise_for_status()
        return resp.json()

    async def create_invoice(self, sale_id: int):
        resp = await self.client.post(f"/documents/invoice/{sale_id}")
        resp.raise_for_status()
        return resp.json()

    async def download_document(self, document_id: int):
        resp = await self.client.get(f"/documents/{document_id}/download")
        resp.raise_for_status()
        filename = resp.headers.get("content-disposition", "").replace("attachment; filename=\"", "").rstrip("\"") or "document.bin"
        return resp.content, filename

    async def import_stock(self, file_bytes: bytes, filename: str) -> dict:
        files = {
            "file": (
                filename,
                file_bytes,
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        }
        resp = await self.client.post(
            "/imports/inventory",
            files=files,
            timeout=httpx.Timeout(600.0, connect=15.0),
        )
        resp.raise_for_status()
        return resp.json()

    async def import_catalog_excel(
        self,
        file_bytes: bytes,
        filename: str,
        header_row: int = 2,
    ) -> dict:
        files = {
            "file": (
                filename,
                file_bytes,
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        }
        resp = await self.client.post(
            "/imports/catalog-excel",
            params={"header_row": header_row},
            files=files,
            timeout=180,
        )
        resp.raise_for_status()
        return resp.json()

    async def lookup_assistant_memory(
        self,
        question: str,
        intent: str | None = None,
        status: str = "approved",
    ) -> dict:
        resp = await self.client.post(
            "/assistant/memory/lookup",
            json={"question": question, "intent": intent, "status": status},
        )
        resp.raise_for_status()
        return resp.json()

    async def store_assistant_memory(
        self,
        question: str,
        intent: str,
        answer_text: str,
        source_product_ids: list[int] | None = None,
        source_document_ids: list[int] | None = None,
        status: str = "draft",
        meta_json: dict | None = None,
    ) -> dict:
        resp = await self.client.post(
            "/assistant/memory/store",
            json={
                "question": question,
                "intent": intent,
                "answer_text": answer_text,
                "source_product_ids": source_product_ids or [],
                "source_document_ids": source_document_ids or [],
                "status": status,
                "meta_json": meta_json,
            },
        )
        resp.raise_for_status()
        return resp.json()

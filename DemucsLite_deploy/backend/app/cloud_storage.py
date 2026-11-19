import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from azure.storage.blob import (
    BlobServiceClient,
    BlobSasPermissions,
    ContentSettings,
    generate_blob_sas,
)
from app.config import settings

class AzureBlobStorage:
    def __init__(self) -> None:
        if not settings.AZURE_STORAGE_CONNECTION_STRING:
            raise ValueError("Thiếu biến môi trường AZURE_STORAGE_CONNECTION_STRING")

        self.client = BlobServiceClient.from_connection_string(
            settings.AZURE_STORAGE_CONNECTION_STRING
        )
        self.container_name = settings.AZURE_CONTAINER_NAME
        self._ensure_container()

    def _ensure_container(self) -> None:
        container_client = self.client.get_container_client(self.container_name)
        if not container_client.exists():
            container_client.create_container()

    def upload_file_and_get_sas(
        self,
        local_path: Path,
        blob_path: str,
        content_type: str = "audio/wav",
    ) -> str:
        blob_client = self.client.get_blob_client(
            container=self.container_name, blob=blob_path
        )
        with open(local_path, "rb") as f:
            blob_client.upload_blob(
                f,
                overwrite=True,
                content_settings=ContentSettings(content_type=content_type),
            )

        sas_token = generate_blob_sas(
            account_name=self.client.account_name,
            container_name=self.container_name,
            blob_name=blob_path,
            account_key=self.client.credential.account_key,
            permission=BlobSasPermissions(read=True),
            expiry=datetime.now(timezone.utc) + timedelta(hours=settings.AZURE_SAS_EXPIRY_HOURS),
        )
        return f"{blob_client.url}?{sas_token}"

    def save_job_state(self, job_id: str, data: dict[str, Any]) -> None:
        blob_path = f"jobs/{job_id}/status.json"
        blob_client = self.client.get_blob_client(
            container=self.container_name, blob=blob_path
        )
        payload = json.dumps(data, ensure_ascii=False).encode("utf-8")
        blob_client.upload_blob(
            payload,
            overwrite=True,
            content_settings=ContentSettings(content_type="application/json"),
        )

    def load_job_state(self, job_id: str) -> dict[str, Any] | None:
        blob_path = f"jobs/{job_id}/status.json"
        blob_client = self.client.get_blob_client(
            container=self.container_name, blob=blob_path
        )
        if not blob_client.exists():
            return None
        raw = blob_client.download_blob().readall()
        return json.loads(raw.decode("utf-8"))

_storage_instance: AzureBlobStorage | None = None

def get_storage() -> AzureBlobStorage:
    global _storage_instance
    if _storage_instance is None:
        _storage_instance = AzureBlobStorage()
    return _storage_instance
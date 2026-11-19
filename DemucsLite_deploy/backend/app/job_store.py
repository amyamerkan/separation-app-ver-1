from datetime import datetime, timezone
from typing import Any
from app.cloud_storage import get_storage

class JobStore:
    def __init__(self) -> None:
        self._memory_cache: dict[str, dict[str, Any]] = {}

    def create_job(self, job_id: str, filename: str) -> dict[str, Any]:
        now = datetime.now(timezone.utc).isoformat()
        job_data = {
            "job_id": job_id,
            "filename": filename,
            "status": "pending",
            "progress": 0,
            "created_at": now,
            "updated_at": now,
            "input_url": None,
            "stems": {},
            "error": None,
        }
        self._memory_cache[job_id] = job_data
        get_storage().save_job_state(job_id, job_data)
        return job_data

    def update_job(self, job_id: str, **kwargs: Any) -> dict[str, Any]:
        job_data = self.get_job(job_id)
        if not job_data:
            raise KeyError(f"Không tìm thấy job {job_id}")
        
        job_data.update(kwargs)
        job_data["updated_at"] = datetime.now(timezone.utc).isoformat()
        self._memory_cache[job_id] = job_data
        get_storage().save_job_state(job_id, job_data)
        return job_data

    def get_job(self, job_id: str) -> dict[str, Any] | None:
        if job_id in self._memory_cache:
            return self._memory_cache[job_id]
        
        remote_data = get_storage().load_job_state(job_id)
        if remote_data:
            self._memory_cache[job_id] = remote_data
        return remote_data

job_store = JobStore()
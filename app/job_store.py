"""
Lưu trạng thái job xử lý tách nhạc.

Bản demo dùng dict trong bộ nhớ (đủ cho 1 tiến trình/1 worker).
Khi triển khai thật với nhiều worker (uvicorn --workers > 1, hoặc scale ngang),
hãy thay JobStore này bằng Redis (redis-py) để mọi worker đọc/ghi chung một
nguồn trạng thái. Interface (get/set) được giữ nguyên nên chỉ cần đổi phần
implement bên trong, không cần sửa các nơi gọi.
"""
from enum import Enum
from typing import Optional, Dict, Any
import threading
import time


class JobStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    DONE = "done"
    FAILED = "failed"


class JobStore:
    def __init__(self):
        self._lock = threading.Lock()
        self._jobs: Dict[str, Dict[str, Any]] = {}

    def create(self, job_id: str, filename: str):
        with self._lock:
            self._jobs[job_id] = {
                "status": JobStatus.PENDING,
                "filename": filename,
                "created_at": time.time(),
                "updated_at": time.time(),
                "result_urls": None,
                "error": None,
            }

    def update(self, job_id: str, **fields):
        with self._lock:
            if job_id not in self._jobs:
                return
            self._jobs[job_id].update(fields)
            self._jobs[job_id]["updated_at"] = time.time()

    def get(self, job_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            job = self._jobs.get(job_id)
            return dict(job) if job else None


# Singleton dùng chung toàn app
job_store = JobStore()

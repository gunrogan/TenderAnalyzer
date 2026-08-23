# storage.py
import os
from pathlib import Path

from fastapi import UploadFile

from config import settings

MAX_SIZE_BYTES = settings.max_file_size_mb * 1024 * 1024


def storage_dir() -> Path:
    path = Path(settings.storage_dir)
    path.mkdir(parents=True, exist_ok=True)
    return path


async def save_upload(file: UploadFile, tender_id: str) -> str:
    """Сохраняет загруженный файл в локальное хранилище и возвращает АБСОЛЮТНЫЙ путь.

    Абсолютный путь критичен: Celery-воркер может работать из другого
    рабочего каталога, и относительный путь "storage/x.pdf" не разрешится.
    """
    content = await file.read()
    if len(content) > MAX_SIZE_BYTES:
        raise ValueError("Файл слишком большой")
    ext = Path(file.filename or "document.pdf").suffix.lower()
    rel_path = storage_dir() / f"{tender_id}{ext}"
    rel_path.write_bytes(content)
    return os.path.abspath(rel_path)
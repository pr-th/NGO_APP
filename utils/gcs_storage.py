from __future__ import annotations

import uuid
from typing import Optional

import anyio
from fastapi import HTTPException, UploadFile
from google.cloud import storage

from core.config import get_settings


settings = get_settings()


def _require_bucket() -> str:
    if not settings.gcs_bucket_name:
        raise HTTPException(
            status_code=500,
            detail="GCS is not configured (missing GCS_BUCKET_NAME / gcs_bucket_name)",
        )
    return settings.gcs_bucket_name


def _extension_from_upload(file: UploadFile) -> str:
    name = (file.filename or "").lower()
    _, dot, ext = name.rpartition(".")
    if dot and ext and len(ext) <= 10:
        return ext
    if file.content_type == "image/jpeg":
        return "jpg"
    if file.content_type == "image/png":
        return "png"
    if file.content_type == "image/webp":
        return "webp"
    return "bin"


def _object_name(prefix: str, file: UploadFile, *, owner_id: Optional[str] = None) -> str:
    ext = _extension_from_upload(file)
    base = uuid.uuid4().hex
    if owner_id:
        return f"{prefix.rstrip('/')}/{owner_id}/{base}.{ext}"
    return f"{prefix.rstrip('/')}/{base}.{ext}"


def _upload_bytes_sync(
    *,
    data: bytes,
    content_type: str,
    object_name: str,
    make_public: bool,
) -> str:
    bucket_name = _require_bucket()
    client = storage.Client(project=settings.gcp_project_id or None)
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(object_name)
    blob.upload_from_string(data, content_type=content_type)

    if make_public:
        blob.make_public()
        return f"https://storage.googleapis.com/{bucket_name}/{object_name}"

    return blob.generate_signed_url(
        version="v4",
        expiration=settings.gcs_signed_url_expire_minutes * 60,
        method="GET",
    )


async def upload_image_and_get_url(
    file: UploadFile,
    *,
    prefix: str = "uploads/images",
    owner_id: Optional[str] = None,
) -> str:
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="Only image uploads are allowed")

    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Empty file")

    object_name = _object_name(prefix, file, owner_id=owner_id)
    try:
        return await anyio.to_thread.run_sync(
            _upload_bytes_sync,
            data=data,
            content_type=file.content_type,
            object_name=object_name,
            make_public=settings.gcs_public_uploads,
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"GCS upload failed: {e}")


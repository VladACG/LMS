from __future__ import annotations

import os
import re
import uuid
from pathlib import Path
from urllib.parse import quote

from app.core.config import settings

ASSIGNMENT_MAX_SIZE_BYTES = 50 * 1024 * 1024
ASSIGNMENT_ALLOWED_EXTENSIONS = {'.pdf', '.docx', '.xlsx', '.jpg', '.jpeg', '.png', '.mp4'}
ASSIGNMENT_ALLOWED_MIME = {
    'application/pdf',
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    'image/jpeg',
    'image/png',
    'video/mp4',
}


def _safe_filename(name: str) -> str:
    base = os.path.basename(name or 'file')
    cleaned = re.sub(r'[^A-Za-z0-9._ -]+', '_', base).strip()
    return cleaned or 'file'


def _local_storage_root() -> Path:
    root = Path(settings.storage_local_path).resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


def _s3_client():
    try:
        import boto3  # type: ignore
    except Exception as exc:  # pragma: no cover - import error path
        raise RuntimeError(f'boto3 is not available: {exc}') from exc

    if not settings.s3_bucket_name or not settings.s3_access_key_id or not settings.s3_secret_access_key:
        raise RuntimeError('S3 credentials are not configured')

    return boto3.client(
        's3',
        endpoint_url=settings.s3_endpoint_url,
        region_name=settings.s3_region,
        aws_access_key_id=settings.s3_access_key_id,
        aws_secret_access_key=settings.s3_secret_access_key,
    )


def is_assignment_file_allowed(file_name: str, content_type: str, size_bytes: int) -> tuple[bool, str]:
    ext = Path(file_name).suffix.lower()
    if size_bytes > ASSIGNMENT_MAX_SIZE_BYTES:
        return False, 'File is too large (max 50 MB)'
    if ext not in ASSIGNMENT_ALLOWED_EXTENSIONS:
        return False, 'Unsupported file extension'
    if content_type and content_type.lower() not in ASSIGNMENT_ALLOWED_MIME:
        return False, 'Unsupported MIME type'
    return True, ''


def upload_bytes(
    *,
    key_prefix: str,
    file_name: str,
    data: bytes,
    content_type: str | None = None,
) -> dict[str, str | int]:
    safe_name = _safe_filename(file_name)
    key = f'{key_prefix.strip("/")}/{uuid.uuid4().hex}_{safe_name}'
    content_type_value = content_type or 'application/octet-stream'
    size_bytes = len(data)

    if settings.storage_backend.lower() == 's3':
        client = _s3_client()
        client.put_object(
            Bucket=settings.s3_bucket_name,
            Key=key,
            Body=data,
            ContentType=content_type_value,
        )
    else:
        root = _local_storage_root()
        target = root / key
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)

    return {
        'key': key,
        'file_name': safe_name,
        'content_type': content_type_value,
        'size_bytes': size_bytes,
    }


def generate_download_url(key: str, expires_in_seconds: int = 3600) -> str:
    if settings.storage_backend.lower() == 's3':
        client = _s3_client()
        return client.generate_presigned_url(
            'get_object',
            Params={'Bucket': settings.s3_bucket_name, 'Key': key},
            ExpiresIn=expires_in_seconds,
        )
    return f'/api/storage/local/{quote(key, safe="/")}'


def local_file_path(key: str) -> Path:
    root = _local_storage_root()
    path = (root / key).resolve()
    if not str(path).startswith(str(root)):
        raise RuntimeError('Invalid file path')
    return path

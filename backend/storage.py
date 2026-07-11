"""S3-compatible object storage. Works unmodified against either Cloudflare
R2 (set S3_ENDPOINT_URL to the R2 account endpoint) or real AWS S3 (leave
S3_ENDPOINT_URL unset) — same code, same function signatures, swap by
environment variable alone. R2 is the default/recommended provider (free
tier, no egress fees), AWS S3 is a drop-in fallback if ever needed.

Replaces the previous Emergent-platform-specific object store. Function
signatures (`put_object`, `get_object`, `delete_object`) are unchanged from
the old implementation so every existing caller in server.py keeps working
without modification.
"""
import logging
import os
from typing import Optional

import boto3
from botocore.client import Config
from botocore.exceptions import ClientError
from fastapi import HTTPException

logger = logging.getLogger(__name__)

S3_ENDPOINT_URL = os.environ.get("S3_ENDPOINT_URL") or None  # unset -> real AWS S3
S3_BUCKET = os.environ.get("S3_BUCKET")
S3_REGION = os.environ.get("S3_REGION", "auto")  # R2 uses "auto"
S3_ACCESS_KEY_ID = os.environ.get("S3_ACCESS_KEY_ID")
S3_SECRET_ACCESS_KEY = os.environ.get("S3_SECRET_ACCESS_KEY")

_client = None


def _get_client():
    global _client
    if _client is None:
        if not (S3_BUCKET and S3_ACCESS_KEY_ID and S3_SECRET_ACCESS_KEY):
            raise HTTPException(500, "File storage is not configured (missing S3_* environment variables)")
        _client = boto3.client(
            "s3",
            endpoint_url=S3_ENDPOINT_URL,
            region_name=S3_REGION,
            aws_access_key_id=S3_ACCESS_KEY_ID,
            aws_secret_access_key=S3_SECRET_ACCESS_KEY,
            config=Config(signature_version="s3v4"),
        )
    return _client


def put_object(path: str, data: bytes, content_type: str) -> dict:
    try:
        _get_client().put_object(Bucket=S3_BUCKET, Key=path, Body=data, ContentType=content_type)
    except ClientError as e:
        logger.error(f"Storage upload failed: {e}")
        raise HTTPException(500, "Upload failed")
    return {"path": path, "size": len(data)}


def get_object(path: str):
    try:
        resp = _get_client().get_object(Bucket=S3_BUCKET, Key=path)
    except ClientError as e:
        logger.error(f"Storage read failed: {e}")
        raise HTTPException(404, "File not found in storage")
    return resp["Body"].read(), resp.get("ContentType", "application/octet-stream")


def delete_object(path: str) -> bool:
    try:
        _get_client().delete_object(Bucket=S3_BUCKET, Key=path)
        return True
    except ClientError as e:
        logger.error(f"Storage delete failed: {e}")
        return False


def presigned_download_url(path: str, filename: Optional[str] = None, expires_in: int = 600) -> str:
    """A short-lived (default 10 min) signed URL — the only way this app
    exposes a downloadable link. Raw bucket URLs are never returned."""
    params = {"Bucket": S3_BUCKET, "Key": path}
    if filename:
        safe_name = filename.replace('"', "")
        params["ResponseContentDisposition"] = f'attachment; filename="{safe_name}"'
    try:
        return _get_client().generate_presigned_url("get_object", Params=params, ExpiresIn=expires_in)
    except ClientError as e:
        logger.error(f"Presign failed: {e}")
        raise HTTPException(500, "Could not generate a download link")

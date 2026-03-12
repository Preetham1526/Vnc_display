from __future__ import annotations

import io
import os
import logging
from typing import BinaryIO
from pathlib import PurePosixPath

import boto3
from botocore.config import Config as BotoConfig
from botocore.exceptions import ClientError
from fastapi import UploadFile

logger = logging.getLogger(__name__)


class S3Client:

    def __init__(
        self,
        bucket: str | None = None,
        endpoint_url: str | None = None,
        access_key: str | None = None,
        secret_key: str | None = None,
        ca_bundle: str | None = None,
        region: str = "us-east-1",
    ) -> None:
        self.bucket = bucket or os.getenv("S3_BUCKET")
        if not self.bucket:
            raise ValueError("S3_BUCKET is not set in environment or constructor.")

        self._endpoint_url = endpoint_url or os.getenv("S3_ENDPOINT") or None
        self._access_key = access_key or os.getenv("S3_ACCESS_KEY")
        self._secret_key = secret_key or os.getenv("S3_SECRET_KEY")
        self._ca_bundle = ca_bundle or os.getenv("AWS_CA_BUNDLE") or None
        self._region = region

        self._client = self._build_client()
        logger.info(
            "S3Client initialised  bucket=%s  endpoint=%s",
            self.bucket,
            self._endpoint_url or "default-aws",
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_client(self):
        """Create the low-level boto3 S3 client."""
        kwargs: dict = {
            "service_name": "s3",
            "region_name": self._region,
            "config": BotoConfig(signature_version="s3v4"),
        }
        if self._endpoint_url:
            kwargs["endpoint_url"] = self._endpoint_url
            kwargs["verify"] = self._ca_bundle if self._ca_bundle else True
        if self._access_key and self._secret_key:
            kwargs["aws_access_key_id"] = self._access_key
            kwargs["aws_secret_access_key"] = self._secret_key
        return boto3.client(**kwargs)

    @staticmethod
    def _build_key(folder: str, filename: str) -> str:
        """Combine *folder* and *filename* into a clean S3 object key.

        >>> S3Client._build_key("reports/2024", "q1.pdf")
        'reports/2024/q1.pdf'
        >>> S3Client._build_key("", "root_file.txt")
        'root_file.txt'
        """
        folder = folder.strip("/") if folder else ""
        filename = filename.strip("/")
        return str(PurePosixPath(folder) / filename) if folder else filename

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def upload(
        self,
        file: UploadFile,
        folder: str = "",
        *,
        filename: str | None = None,
        content_type: str | None = None,
        bucket: str | None = None,
    ) -> str:
        """Upload a FastAPI ``UploadFile`` to S3.

        Parameters
        ----------
        file : UploadFile
            The file received in the request.
        folder : str
            Virtual directory / prefix.  e.g. ``"invoices"`` or ``"reports/2024"``.
        filename : str | None
            Override the original filename.  Defaults to ``file.filename``.
        content_type : str | None
            Override MIME type.  Defaults to ``file.content_type``.
        bucket : str | None
            Override the default bucket for this call.

        Returns
        -------
        str
            The S3 object key that was written.
        """
        target_bucket = bucket or self.bucket
        name = filename or file.filename or "unnamed"
        key = self._build_key(folder, name)
        mime = content_type or file.content_type or "application/octet-stream"

        contents = await file.read()

        self._client.upload_fileobj(
            Fileobj=io.BytesIO(contents),
            Bucket=target_bucket,
            Key=key,
            ExtraArgs={"ContentType": mime},
        )
        logger.info("Uploaded  %s/%s  (%d bytes)", target_bucket, key, len(contents))
        return key

    def upload_bytes(
        self,
        data: bytes | BinaryIO,
        folder: str,
        filename: str,
        *,
        content_type: str = "application/octet-stream",
        bucket: str | None = None,
    ) -> str:
        """Upload raw bytes or a file-like object (synchronous).

        Useful when you already have in-memory data rather than an UploadFile.

        Returns
        -------
        str
            The S3 object key that was written.
        """
        target_bucket = bucket or self.bucket
        key = self._build_key(folder, filename)
        fileobj = io.BytesIO(data) if isinstance(data, bytes) else data

        self._client.upload_fileobj(
            Fileobj=fileobj,
            Bucket=target_bucket,
            Key=key,
            ExtraArgs={"ContentType": content_type},
        )
        logger.info("Uploaded (bytes)  %s/%s", target_bucket, key)
        return key

    def download(
        self,
        key: str,
        *,
        bucket: str | None = None,
    ) -> bytes:
        """Download an object and return its contents as ``bytes``."""
        target_bucket = bucket or self.bucket
        buf = io.BytesIO()
        self._client.download_fileobj(Bucket=target_bucket, Key=key, Fileobj=buf)
        buf.seek(0)
        logger.info("Downloaded  %s/%s", target_bucket, key)
        return buf.read()

    def remove(
        self,
        key: str,
        *,
        bucket: str | None = None,
    ) -> bool:
        """Delete a single object.  Returns ``True`` if successful."""
        target_bucket = bucket or self.bucket
        try:
            self._client.delete_object(Bucket=target_bucket, Key=key)
            logger.info("Deleted  %s/%s", target_bucket, key)
            return True
        except ClientError:
            logger.exception("Failed to delete  %s/%s", target_bucket, key)
            return False

    def remove_folder(
        self,
        folder: str,
        *,
        bucket: str | None = None,
    ) -> int:
        """Delete all objects under a prefix.  Returns count of deleted objects."""
        target_bucket = bucket or self.bucket
        prefix = folder.strip("/") + "/"
        objects = self.list_objects(prefix=prefix, bucket=target_bucket)

        if not objects:
            return 0

        delete_payload = {"Objects": [{"Key": k} for k in objects]}
        resp = self._client.delete_objects(
            Bucket=target_bucket, Delete=delete_payload
        )
        deleted_count = len(resp.get("Deleted", []))
        logger.info("Deleted %d objects under  %s/%s", deleted_count, target_bucket, prefix)
        return deleted_count

    def list_objects(
        self,
        prefix: str = "",
        *,
        bucket: str | None = None,
    ) -> list[str]:
        """List object keys under a prefix."""
        target_bucket = bucket or self.bucket
        paginator = self._client.get_paginator("list_objects_v2")
        keys: list[str] = []
        for page in paginator.paginate(Bucket=target_bucket, Prefix=prefix):
            for obj in page.get("Contents", []):
                keys.append(obj["Key"])
        return keys

    def exists(
        self,
        key: str,
        *,
        bucket: str | None = None,
    ) -> bool:
        """Check whether an object exists."""
        target_bucket = bucket or self.bucket
        try:
            self._client.head_object(Bucket=target_bucket, Key=key)
            return True
        except ClientError:
            return False

    def generate_presigned_url(
        self,
        key: str,
        *,
        expiration: int = 3600,
        bucket: str | None = None,
    ) -> str:
        """Generate a pre-signed GET URL (default 1 hour)."""
        target_bucket = bucket or self.bucket
        return self._client.generate_presigned_url(
            "get_object",
            Params={"Bucket": target_bucket, "Key": key},
            ExpiresIn=expiration,
        )





#routes

# app/routers/files.py
from fastapi import APIRouter, UploadFile, File, HTTPException, Query
from app.dependencies import s3

router = APIRouter(prefix="/files", tags=["files"])


@router.post("/upload")
async def upload_file(
    file: UploadFile = File(...),
    folder: str = Query("general", description="Target folder/prefix in S3"),
):
    """Upload a file into the specified folder."""
    key = await s3.upload(file, folder)
    return {"key": key, "message": "Uploaded successfully"}


@router.get("/download")
def download_file(key: str):
    """Download a file by its full S3 key."""
    if not s3.exists(key):
        raise HTTPException(404, "Object not found")
    data = s3.download(key)
    from fastapi.responses import Response
    return Response(content=data, media_type="application/octet-stream")


@router.delete("/remove")
def remove_file(key: str):
    """Delete a single file by its S3 key."""
    success = s3.remove(key)
    if not success:
        raise HTTPException(500, "Delete failed")
    return {"deleted": key}


@router.delete("/remove-folder")
def remove_folder(folder: str):
    """Delete all files under a folder prefix."""
    count = s3.remove_folder(folder)
    return {"deleted_count": count}


@router.get("/list")
def list_files(prefix: str = ""):
    """List all keys under a prefix."""
    return {"keys": s3.list_objects(prefix)}


@router.get("/presigned-url")
def presigned_url(key: str, expiration: int = 3600):
    """Get a pre-signed URL to share a file temporarily."""
    url = s3.generate_presigned_url(key, expiration=expiration)
    return {"url": url, "expires_in": expiration}
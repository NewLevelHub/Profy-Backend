import asyncio

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError


class S3StorageBackend:
    """S3-compatible backend — identical code path against MinIO locally and
    real S3/R2/Spaces in prod, only endpoint/credentials differ. Uses plain
    (synchronous) boto3 wrapped in asyncio.to_thread rather than aioboto3:
    this pipeline only ever runs as an offline batch script, never on a
    request hot path, so the extra async-native dependency chain isn't worth
    it. No per-object ACL is set — public readability comes from a
    bucket-level policy (see docker-compose.local.yml's minio-init service),
    since per-object ACLs aren't reliably supported across all S3-compatible
    vendors (e.g. Cloudflare R2)."""

    def __init__(
        self,
        *,
        endpoint_url: str | None,
        region: str,
        access_key: str,
        secret_key: str,
        bucket: str,
        use_path_style: bool,
    ) -> None:
        self._bucket = bucket
        self._client = boto3.client(
            "s3",
            endpoint_url=endpoint_url,
            region_name=region,
            aws_access_key_id=access_key or None,
            aws_secret_access_key=secret_key or None,
            config=Config(s3={"addressing_style": "path" if use_path_style else "virtual"}),
        )

    async def put_object(self, key: str, data: bytes, *, content_type: str) -> None:
        await asyncio.to_thread(
            self._client.put_object,
            Bucket=self._bucket,
            Key=key,
            Body=data,
            ContentType=content_type,
        )

    async def object_exists(self, key: str) -> bool:
        try:
            await asyncio.to_thread(self._client.head_object, Bucket=self._bucket, Key=key)
            return True
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") in ("404", "NoSuchKey"):
                return False
            raise

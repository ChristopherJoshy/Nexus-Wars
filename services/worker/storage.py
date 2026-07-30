"""Replay / artifact storage abstraction.

Uses S3/MinIO when MINIO_ENDPOINT is set, otherwise a local filesystem
directory. The same `key` works for both modes.
"""
import json
import os

from config import (STORAGE_DIR, MINIO_ENDPOINT, MINIO_KEY,
                    MINIO_SECRET, MINIO_BUCKET)


def _s3():
    import boto3
    return boto3.client(
        "s3",
        endpoint_url=MINIO_ENDPOINT,
        aws_access_key_id=MINIO_KEY,
        aws_secret_access_key=MINIO_SECRET,
    )


def put_json(key, obj):
    data = json.dumps(obj).encode("utf-8")
    if MINIO_ENDPOINT:
        _s3().put_object(Bucket=MINIO_BUCKET, Key=key, Body=data)
    else:
        full_path = os.path.join(STORAGE_DIR, key)
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        with open(full_path, "wb") as f:
            f.write(data)
    return len(data)


def get_json(key):
    if MINIO_ENDPOINT:
        obj = _s3().get_object(Bucket=MINIO_BUCKET, Key=key)
        return json.loads(obj["Body"].read())
    with open(os.path.join(STORAGE_DIR, key)) as f:
        return json.load(f)


def put_file(key, local_path):
    if MINIO_ENDPOINT:
        _s3().upload_file(local_path, MINIO_BUCKET, key)
    else:
        os.makedirs(STORAGE_DIR, exist_ok=True)
        import shutil
        shutil.copyfile(local_path, os.path.join(STORAGE_DIR, key))


def get_file(key, local_path):
    """Download an object from S3/MinIO to a local file."""
    if MINIO_ENDPOINT:
        os.makedirs(os.path.dirname(local_path) or ".", exist_ok=True)
        _s3().download_file(MINIO_BUCKET, key, local_path)
    else:
        import shutil
        src = os.path.join(STORAGE_DIR, key)
        os.makedirs(os.path.dirname(local_path) or ".", exist_ok=True)
        shutil.copyfile(src, local_path)

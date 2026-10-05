"""Open a products root that is either a local directory or an S3 URI."""

from __future__ import annotations

import os


def s3_options() -> dict:
    """fsspec options for S3: the endpoint from ``AWS_S3_ENDPOINT`` or ``S3_ENDPOINT_URL``.

    Keys come from the usual ``AWS_*`` variables.
    """
    endpoint = os.environ.get("AWS_S3_ENDPOINT") or os.environ.get("S3_ENDPOINT_URL") or ""
    if endpoint and "://" not in endpoint:
        endpoint = f"https://{endpoint}"
    return {"client_kwargs": {"endpoint_url": endpoint}} if endpoint else {}


def filesystem(root: str):
    """``(fsspec filesystem, path)`` for a local directory or ``s3://bucket/prefix``."""
    import fsspec

    if not root.startswith("s3://"):
        return fsspec.filesystem("file"), os.path.expanduser(root).rstrip("/")
    return fsspec.filesystem("s3", **s3_options()), root.removeprefix("s3://").rstrip("/")

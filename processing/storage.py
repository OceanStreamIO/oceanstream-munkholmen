"""Open a products root that is either a local directory or an S3 URI."""

from __future__ import annotations

import os


def filesystem(root: str):
    """``(fsspec filesystem, path)`` for a local directory or ``s3://bucket/prefix``.

    For S3 the endpoint comes from ``AWS_S3_ENDPOINT`` or ``S3_ENDPOINT_URL``
    and the keys from the usual ``AWS_*`` variables.
    """
    import fsspec

    if not root.startswith("s3://"):
        return fsspec.filesystem("file"), os.path.expanduser(root).rstrip("/")
    endpoint = os.environ.get("AWS_S3_ENDPOINT") or os.environ.get("S3_ENDPOINT_URL") or ""
    if endpoint and "://" not in endpoint:
        endpoint = f"https://{endpoint}"
    options = {"client_kwargs": {"endpoint_url": endpoint}} if endpoint else {}
    return fsspec.filesystem("s3", **options), root.removeprefix("s3://").rstrip("/")

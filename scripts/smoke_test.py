#!/usr/bin/env python3
"""Smoke test: post a sample image to /api/analyze and print the result.

Usage:
    python scripts/smoke_test.py --image sample.jpg --lang ur \
        --base-url http://127.0.0.1:8000
"""

from __future__ import annotations

import argparse
import json
import mimetypes
import sys

import httpx


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-It-For-Me smoke test")
    parser.add_argument("--image", required=True, help="Path to a JPEG/PNG/WebP photo")
    parser.add_argument("--lang", default="ur", choices=["ur", "ps", "en"])
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    args = parser.parse_args()

    base = args.base_url.rstrip("/")
    # trust_env=False: talk to the app directly; some sandboxes export
    # proxy/no_proxy values that httpx's env parsing cannot handle.
    client = httpx.Client(timeout=120, trust_env=False)
    health = client.get(f"{base}/api/health")
    print("health:", health.status_code, health.text)

    mime = mimetypes.guess_type(args.image)[0] or "image/jpeg"
    with open(args.image, "rb") as fh:
        files = {"image": (args.image, fh, mime)}
        resp = client.post(
            f"{base}/api/analyze",
            files=files,
            data={"lang": args.lang},
        )
    print("analyze status:", resp.status_code)
    try:
        print(json.dumps(resp.json(), indent=2, ensure_ascii=False))
    except Exception:
        print(resp.text)
        return 1
    return 0 if resp.status_code == 200 else 1


if __name__ == "__main__":
    sys.exit(main())

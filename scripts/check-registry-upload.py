#!/usr/bin/env python3
"""Check Basic-auth upload access, then cancel only the upload created by this check."""
import base64
import json
import os
from pathlib import Path
import re
import runpy
import sys
import urllib.error
import urllib.parse
import urllib.request


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def main():
    resolver = runpy.run_path(str(Path(__file__).with_name("registry-settings.py")))
    host = os.environ.get("REGISTRY_URL", "")
    image = resolver["resolve_image"](host, os.environ.get("REGISTRY_IMAGE", ""))
    username, password = os.environ.get("REGISTRY_USERNAME", ""), os.environ.get("REGISTRY_PASSWORD", "")
    if not username or not password or ":" in username:
        raise ValueError("A nonempty Basic-auth username without a colon and a password are required")
    base = "https://" + host
    repository = image[len(host) + 1:]
    path = "/v2/" + repository + "/blobs/uploads/"
    authorization = "Basic " + base64.b64encode((username + ":" + password).encode()).decode()
    opener = urllib.request.build_opener(NoRedirect())

    def request(url, method):
        # No redirects: registry credentials must never be forwarded to another host.
        req = urllib.request.Request(url, data=b"" if method == "POST" else None,
                                     method=method, headers={"Authorization": authorization})
        try:
            return opener.open(req, timeout=20)
        except urllib.error.HTTPError as error:
            return error

    response = request(base + path, "POST")
    status = response.status
    challenge = (response.headers.get("WWW-Authenticate") or "").split(" ", 1)[0].lower()
    location = response.headers.get("Location")
    response.close()
    print(json.dumps({"image_repository": image, "authenticated_upload_status": status,
                      "authentication_scheme": challenge if challenge in {"basic", "bearer"} else None}))
    if status != 202:
        if status in (401, 403) and challenge == "bearer":
            raise ValueError("This check supports Basic authentication; Bearer-token permission checking requires a separate implementation")
        if status in (401, 403):
            raise ValueError("Registry rejected the configured credentials or upload permission for this image repository")
        raise ValueError("Registry did not accept upload creation; check its repository path and proxy configuration")
    if not location:
        raise ValueError("Registry accepted upload creation without a cancellation location")
    target = urllib.parse.urljoin(base + path, location)
    parsed, expected = urllib.parse.urlsplit(target), urllib.parse.urlsplit(base)
    upload_id = parsed.path[len(path):] if parsed.path.startswith(path) else ""
    if parsed.scheme != "https" or parsed.netloc != expected.netloc or parsed.fragment or not re.fullmatch(r"[A-Za-z0-9_-]+", upload_id):
        raise ValueError("Registry returned an unexpected upload location; no credentials were sent to it")
    cleanup = request(target, "DELETE")
    cleanup_status = cleanup.status
    cleanup.close()
    print(json.dumps({"own_upload_cancellation_status": cleanup_status}))
    if cleanup_status != 204:
        raise ValueError("Upload access succeeded but cancellation failed; no image manifest was published")
    print("Authenticated upload creation and cancellation succeeded. No image was published.")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError) as error:
        # Do not print a network exception: its URL may contain an upload-state token.
        message = str(error) if isinstance(error, ValueError) else "Registry upload check failed because of a network or TLS error"
        print(message, file=sys.stderr)
        sys.exit(2)

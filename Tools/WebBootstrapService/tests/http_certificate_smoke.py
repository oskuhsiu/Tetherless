#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-only
"""Local admission smoke; never starts an Apple account session.

Usage: python3 tests/http_certificate_smoke.py /path/to/release/binary
"""
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request


def main(binary):
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    origin = f"http://127.0.0.1:{port}"
    with tempfile.TemporaryDirectory(prefix="tetherless-certificate-smoke-") as static:
        env = {
            **os.environ,
            "TETHERLESS_BIND": f"127.0.0.1:{port}",
            "TETHERLESS_PUBLIC_HOST": f"127.0.0.1:{port}",
            "FRONTEND_ORIGIN": origin,
            "TETHERLESS_FRONTEND_DIR": static,
        }
        process = subprocess.Popen(
            [os.path.abspath(binary)], env=env,
            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
        )
        checks = 0
        try:
            for _ in range(60):
                if process.poll() is not None:
                    raise RuntimeError("Service exited during local startup")
                try:
                    with urllib.request.urlopen(origin + "/health", timeout=0.2) as response:
                        assert json.load(response)["certificateLifecycle"] == 1
                        assert response.headers["Cache-Control"] == "no-store"
                        checks += 1
                    break
                except urllib.error.URLError:
                    time.sleep(0.05)
            else:
                raise RuntimeError("Local service startup timeout")

            certificate_body = {
                "consent": "register-device-app-ids-and-issue-certificate",
                "teamId": "SYNTHETIC",
                "device": {"udid": "0" * 40, "name": "Synthetic"},
                "csrPem": "synthetic-invalid-csr",
                "machineName": "Synthetic",
                "apps": [{"bundleId": "org.example.synthetic", "name": "Synthetic"}],
            }
            revoke_body = {
                "certificateId": "Synthetic", "certificateSerial": "ABC123",
                "confirmationToken": "00000000-0000-4000-8000-000000000000",
                "consent": "revoke-selected-development-certificate",
            }
            session = "/v1/sessions/unknown"
            catalog = session + "/teams/SYNTHETIC/certificates"
            routes = [
                ("POST", session + "/certificate", certificate_body),
                ("GET", catalog, None),
                ("POST", catalog + "/revoke", revoke_body),
            ]
            for method, path, body in routes:
                for hostile, expected in [(False, 404), (True, 403)]:
                    request = urllib.request.Request(
                        origin + path, method=method,
                        data=None if body is None else json.dumps(body).encode(),
                        headers={
                            "Origin": "https://evil.example" if hostile else origin,
                            "Content-Type": "application/json",
                        },
                    )
                    try:
                        with urllib.request.urlopen(request, timeout=2):
                            raise AssertionError("Request unexpectedly succeeded")
                    except urllib.error.HTTPError as error:
                        assert error.code == expected, (path, error.code)
                        assert error.headers["Cache-Control"] == "no-store"
                        checks += 1
            print(
                f"PASS {checks} optimized-binary HTTP checks: capability/no-store and "
                "all 3 certificate routes unknown-session + hostile-origin admission. "
                "No login or Apple request sent."
            )
        finally:
            process.terminate()
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
            process.stderr.close()


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("Usage: http_certificate_smoke.py /path/to/release/binary")
    main(sys.argv[1])

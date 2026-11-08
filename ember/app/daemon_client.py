"""Tiny blocking client for emberd's JSON-lines socket."""
from __future__ import annotations

import json
import os
import socket

SOCKET = os.environ.get("EMBER_SOCKET", "/run/ember/emberd.sock")


class DaemonError(RuntimeError):
    pass


def request(req: dict, timeout: float = 8.0) -> dict:
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.settimeout(timeout)
    try:
        s.connect(SOCKET)
        s.sendall(json.dumps(req).encode() + b"\n")
        buf = b""
        while not buf.endswith(b"\n"):
            chunk = s.recv(65536)
            if not chunk:
                break
            buf += chunk
    except (OSError, socket.timeout) as e:
        raise DaemonError(f"Ember service unavailable ({e.strerror or e})") from None
    finally:
        s.close()
    try:
        resp = json.loads(buf)
    except ValueError:
        raise DaemonError("bad reply from Ember service") from None
    if not resp.get("ok"):
        raise DaemonError(resp.get("error") or "request failed")
    return resp

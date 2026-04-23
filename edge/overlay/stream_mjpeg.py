from __future__ import annotations

import errno
import sys
import threading
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, HTTPServer
from socketserver import ThreadingMixIn
from typing import Optional

import cv2
import numpy as np


class _ThreadingReuseHTTPServer(ThreadingMixIn, HTTPServer):
    """Thread per request so a stuck /mjpeg client cannot block /health probes."""

    allow_reuse_address = True
    daemon_threads = True


class _Handler(BaseHTTPRequestHandler):
    server_version = "BilliardsAI-MJPEG/0.1"

    def do_GET(self) -> None:  # noqa: N802
        path = self.path.split("?", 1)[0]
        if path == "/health":
            body = b"ok\n"
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)
            return
        if path not in ("/", "/mjpeg"):
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header("Age", "0")
        self.send_header("Cache-Control", "no-cache, private")
        self.send_header("Pragma", "no-cache")
        self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
        self.end_headers()

        srv: "MjpegServer" = self.server.mjpeg_server  # type: ignore[attr-defined]
        while not srv._stop.is_set():
            frame = srv.latest_frame()
            if frame is None:
                srv._stop.wait(0.05)
                continue
            ok, jpg = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), srv.jpeg_quality])
            if not ok:
                continue
            payload = jpg.tobytes()
            try:
                self.wfile.write(b"--frame\r\n")
                self.wfile.write(b"Content-Type: image/jpeg\r\n")
                self.wfile.write(f"Content-Length: {len(payload)}\r\n\r\n".encode("utf-8"))
                self.wfile.write(payload)
                self.wfile.write(b"\r\n")
            except BrokenPipeError:
                break

    def log_message(self, format: str, *args) -> None:  # noqa: A002
        return


def _port_bind_failed_in_use(err: OSError) -> bool:
    if err.errno == errno.EADDRINUSE:
        return True
    if sys.platform == "win32" and err.errno in (10048,):  # WSAEADDRINUSE
        return True
    return "address already in use" in str(err).lower()


@dataclass
class MjpegServer:
    host: str = "0.0.0.0"
    port: int = 8001
    jpeg_quality: int = 80

    _frame: Optional[np.ndarray] = None
    _lock: threading.Lock = threading.Lock()
    _thread: Optional[threading.Thread] = None
    _stop: threading.Event = threading.Event()
    _httpd: Optional[HTTPServer] = None

    def start(self) -> None:
        self._stop.clear()
        try:
            httpd = _ThreadingReuseHTTPServer((self.host, self.port), _Handler)
        except OSError as e:
            if _port_bind_failed_in_use(e):
                raise RuntimeError(
                    f"MJPEG port {self.port} is already in use. Stop the other process (e.g. a previous "
                    f"`edge.main` or a browser tab still holding the stream) or use `--mjpeg-port` with a "
                    f"free port in 8001-8005 (e.g. 8002)."
                ) from e
            raise
        httpd.mjpeg_server = self  # type: ignore[attr-defined]
        self._httpd = httpd
        t = threading.Thread(target=httpd.serve_forever, daemon=True)
        self._thread = t
        t.start()

    def stop(self) -> None:
        self._stop.set()
        if self._httpd is not None:
            self._httpd.shutdown()
        if self._thread is not None:
            self._thread.join(timeout=1.0)

    def update(self, frame_bgr: np.ndarray) -> None:
        with self._lock:
            self._frame = frame_bgr.copy()

    def latest_frame(self) -> Optional[np.ndarray]:
        with self._lock:
            if self._frame is None:
                return None
            return self._frame


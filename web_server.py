# web_server.py

import json
import os
import threading
import urllib.request
from collections import deque
from queue import Empty, Queue
from typing import Optional

from flask import Flask, Response, jsonify, send_from_directory


LEAFLET_VERSION = "1.9.4"
LEAFLET_FILES = {
    "leaflet.js": f"https://unpkg.com/leaflet@{LEAFLET_VERSION}/dist/leaflet.js",
    "leaflet.css": f"https://unpkg.com/leaflet@{LEAFLET_VERSION}/dist/leaflet.css",
}


def ensure_leaflet(vendor_dir: str) -> None:
    os.makedirs(vendor_dir, exist_ok=True)

    for name, url in LEAFLET_FILES.items():
        path = os.path.join(vendor_dir, name)

        if os.path.exists(path):
            continue

        print(f"[WEB] downloading {url}")
        urllib.request.urlretrieve(url, path)


class WebServer:
    """Flask + SSE server. publish(state) で測位データを配信する。"""

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 8000,
        trail_limit: int = 1000,
    ):
        self.host = host
        self.port = port
        self.trail_limit = trail_limit

        self._state: Optional[dict] = None
        self._trail: deque = deque(maxlen=trail_limit)
        self._subscribers: list = []
        self._lock = threading.Lock()

        static_dir = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "static"
        )
        ensure_leaflet(os.path.join(static_dir, "vendor", "leaflet"))

        self.app = Flask(
            __name__,
            static_folder=static_dir,
            static_url_path="/static",
        )
        self._register_routes()

    def _register_routes(self) -> None:
        @self.app.route("/")
        def index():
            return send_from_directory(self.app.static_folder, "index.html")

        @self.app.route("/api/state")
        def state_endpoint():
            with self._lock:
                return jsonify({
                    "state": self._state,
                    "trail": list(self._trail),
                })

        @self.app.route("/api/stream")
        def stream_endpoint():
            q: Queue = Queue(maxsize=64)

            with self._lock:
                self._subscribers.append(q)
                initial = self._state
                initial_trail = list(self._trail)

            def gen():
                try:
                    if initial is not None:
                        payload = {"state": initial, "trail": initial_trail}
                        yield f"data: {json.dumps(payload)}\n\n"

                    while True:
                        try:
                            data = q.get(timeout=15)
                        except Empty:
                            yield ": keepalive\n\n"
                            continue

                        yield f"data: {json.dumps({'state': data})}\n\n"
                finally:
                    with self._lock:
                        if q in self._subscribers:
                            self._subscribers.remove(q)

            return Response(gen(), mimetype="text/event-stream")

    def publish(self, state: dict) -> None:
        with self._lock:
            self._state = state

            lat = state.get("lat")
            lon = state.get("lon")
            if lat is not None and lon is not None:
                self._trail.append([lat, lon])

            subs = list(self._subscribers)

        for q in subs:
            try:
                q.put_nowait(state)
            except Exception:
                pass

    def start(self) -> threading.Thread:
        t = threading.Thread(
            target=self.app.run,
            kwargs={
                "host": self.host,
                "port": self.port,
                "threaded": True,
                "use_reloader": False,
                "debug": False,
            },
            daemon=True,
        )
        t.start()
        print(f"[WEB] serving http://{self.host}:{self.port}")
        return t

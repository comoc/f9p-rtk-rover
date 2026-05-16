# test_web_server.py

import json
import os
import sys
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# pylint: disable=wrong-import-position,import-error
from web_server import WebServer  # noqa: E402


@pytest.fixture
def server(tmp_path, monkeypatch):
    # Leaflet の自動取得をスキップ（オフライン環境でも通すため）
    monkeypatch.setattr("web_server.ensure_leaflet", lambda _vendor_dir: None)
    return WebServer(host="127.0.0.1", port=0)


def test_publish_updates_state(server):
    server.publish({"status": "RTK FIXED", "lat": 35.0, "lon": 139.0})
    assert server._state["status"] == "RTK FIXED"
    assert list(server._trail) == [[35.0, 139.0]]


def test_publish_skips_trail_when_no_position(server):
    server.publish({"status": "NO FIX", "lat": None, "lon": None})
    assert list(server._trail) == []


def test_trail_limit(monkeypatch):
    monkeypatch.setattr("web_server.ensure_leaflet", lambda _vendor_dir: None)
    s = WebServer(trail_limit=3)

    for i in range(5):
        s.publish({"lat": float(i), "lon": 0.0})

    # 古い2点は捨てられて新しい3点だけ残る
    assert list(s._trail) == [[2.0, 0.0], [3.0, 0.0], [4.0, 0.0]]


def test_state_endpoint_returns_snapshot(server):
    server.publish({"status": "DGNSS", "lat": 10.0, "lon": 20.0})

    client = server.app.test_client()
    resp = client.get("/api/state")

    assert resp.status_code == 200
    data = json.loads(resp.data)
    assert data["state"]["status"] == "DGNSS"
    assert data["trail"] == [[10.0, 20.0]]


def test_index_route_serves_html(server, tmp_path, monkeypatch):
    # static/index.html を配信するか確認（存在前提）
    client = server.app.test_client()
    resp = client.get("/")
    assert resp.status_code == 200
    assert b"F9P RTK Rover" in resp.data


def test_ensure_leaflet_downloads_missing_files(tmp_path):
    """ファイルが無ければ urlretrieve が呼ばれること。"""
    import web_server as ws

    vendor_dir = tmp_path / "vendor"

    with patch("web_server.urllib.request.urlretrieve") as m:
        ws.ensure_leaflet(str(vendor_dir))

        assert m.call_count == len(ws.LEAFLET_FILES)


def test_ensure_leaflet_skips_existing(tmp_path):
    """既存ファイルはダウンロードされない。"""
    import web_server as ws

    vendor_dir = tmp_path / "vendor"
    vendor_dir.mkdir()

    for name in ws.LEAFLET_FILES:
        (vendor_dir / name).write_text("cached")

    with patch("web_server.urllib.request.urlretrieve") as m:
        ws.ensure_leaflet(str(vendor_dir))

        assert m.call_count == 0


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))

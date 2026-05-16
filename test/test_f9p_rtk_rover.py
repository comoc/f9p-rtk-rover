# test_f9p_rtk_rover.py

import os
import sys
import threading
import time
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# pylint: disable=wrong-import-position,import-error
from f9p_rtk_rover import (  # noqa: E402
    base_serial_worker,
    build_ntrip_request,
    gga_quality_to_status,
)


def test_gga_quality_known():
    assert gga_quality_to_status(0) == "NO FIX"
    assert gga_quality_to_status(1) == "3D/SINGLE"
    assert gga_quality_to_status(2) == "DGNSS"
    assert gga_quality_to_status(4) == "RTK FIXED"
    assert gga_quality_to_status(5) == "RTK FLOAT"
    assert gga_quality_to_status(6) == "DEAD RECKONING"


def test_gga_quality_unknown():
    assert gga_quality_to_status(9) == "UNKNOWN(9)"
    assert gga_quality_to_status("x") == "UNKNOWN"


def test_build_ntrip_request_without_auth():
    req = build_ntrip_request("example.com", 2101, "MOUNT")
    text = req.decode("ascii")

    assert text.startswith("GET /MOUNT HTTP/1.1\r\n")
    assert "Host: example.com:2101\r\n" in text
    assert "Ntrip-Version: Ntrip/2.0\r\n" in text
    assert "Authorization:" not in text
    assert text.endswith("\r\n\r\n")


def test_build_ntrip_request_with_auth():
    req = build_ntrip_request("h", 2101, "/m", user="u", password="p")
    text = req.decode("ascii")

    assert "GET /m HTTP/1.1" in text
    assert "Authorization: Basic dTpw\r\n" in text  # base64("u:p")


def test_build_ntrip_request_strips_leading_slash():
    req = build_ntrip_request("h", 2101, "///MOUNT")
    assert req.startswith(b"GET /MOUNT HTTP/1.1")


def test_base_serial_worker_forwards_bytes():
    rover = MagicMock()
    rover.write.side_effect = len  # write(b) -> len(b)

    base = MagicMock()
    rtcm_chunks = [b"\xd3\x00\x13RTCM-chunk-1", b"RTCM-chunk-2", b""]

    def fake_read(_n):
        if rtcm_chunks:
            return rtcm_chunks.pop(0)
        time.sleep(0.05)
        return b""

    base.read.side_effect = fake_read

    args = SimpleNamespace(
        base_serial="COM_TEST",
        base_baud=115200,
        reconnect_interval=0.1,
        verbose=False,
    )
    shared = {"rtcm_bytes": 0, "last_rtcm_time": None}
    stop_event = threading.Event()

    with patch("f9p_rtk_rover.serial.Serial", return_value=base):
        t = threading.Thread(
            target=base_serial_worker,
            args=(args, rover, shared, stop_event),
            daemon=True,
        )
        t.start()

        expected_total = len(b"\xd3\x00\x13RTCM-chunk-1") + len(b"RTCM-chunk-2")
        deadline = time.time() + 2.0
        while time.time() < deadline and shared["rtcm_bytes"] < expected_total:
            time.sleep(0.02)

        stop_event.set()
        t.join(timeout=2.0)

    assert shared["rtcm_bytes"] == expected_total
    assert shared["last_rtcm_time"] is not None
    assert rover.write.call_count >= 2


def test_base_serial_worker_reconnects_on_error():
    rover = MagicMock()
    call_count = {"n": 0}

    def serial_factory(*_a, **_kw):
        call_count["n"] += 1
        if call_count["n"] == 1:
            raise OSError("port busy")

        base = MagicMock()
        base.read.return_value = b""
        return base

    args = SimpleNamespace(
        base_serial="COM_TEST",
        base_baud=115200,
        reconnect_interval=0.05,
        verbose=False,
    )
    shared = {"rtcm_bytes": 0, "last_rtcm_time": None}
    stop_event = threading.Event()

    with patch("f9p_rtk_rover.serial.Serial", side_effect=serial_factory):
        t = threading.Thread(
            target=base_serial_worker,
            args=(args, rover, shared, stop_event),
            daemon=True,
        )
        t.start()

        deadline = time.time() + 2.0
        while time.time() < deadline and call_count["n"] < 2:
            time.sleep(0.02)

        stop_event.set()
        t.join(timeout=2.0)

    assert call_count["n"] >= 2  # 失敗後に再接続されている


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))

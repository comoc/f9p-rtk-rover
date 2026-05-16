# test_nmea_forwarder.py

import os
import socket
import sys
import time

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# pylint: disable=wrong-import-position,import-error
from nmea_forwarder import (  # noqa: E402
    NmeaForwarder,
    parse_host_port,
    sentence_id,
)


def test_parse_host_port_basic():
    assert parse_host_port("127.0.0.1:10110") == ("127.0.0.1", 10110)
    assert parse_host_port("example.com:2101") == ("example.com", 2101)


def test_parse_host_port_invalid():
    with pytest.raises(ValueError):
        parse_host_port("no-port-here")


def test_sentence_id_known():
    assert sentence_id(b"$GNGGA,123519,...") == "GGA"
    assert sentence_id(b"$GPRMC,123519,...") == "RMC"
    assert sentence_id(b"$GAGSV,...\r\n") == "GSV"


def test_sentence_id_non_nmea():
    assert sentence_id(b"") is None
    assert sentence_id(b"\xb5\x62\x01\x07") is None
    assert sentence_id(b"$short") is None


def _make_udp_listener():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("127.0.0.1", 0))
    sock.settimeout(1.0)
    return sock, sock.getsockname()


def test_forward_udp_delivers_payload():
    listener, addr = _make_udp_listener()

    fwd = NmeaForwarder(udp_targets=[addr])
    try:
        fwd.forward(b"$GNGGA,123519,3551.65,N,13947.01,E,1,08,0.9,545.4,M,46.9,M,,*47")
        data, _ = listener.recvfrom(2048)
    finally:
        fwd.close()
        listener.close()

    assert data.startswith(b"$GNGGA,")
    assert data.endswith(b"\r\n")


def test_forward_udp_filter_excludes_unmatched_sentence():
    listener, addr = _make_udp_listener()

    fwd = NmeaForwarder(udp_targets=[addr], sentences=["RMC"])
    try:
        fwd.forward(b"$GNGGA,123519,...")  # GGA は除外される

        listener.settimeout(0.3)
        with pytest.raises(socket.timeout):
            listener.recvfrom(2048)

        fwd.forward(b"$GNRMC,123519,...")
        listener.settimeout(1.0)
        data, _ = listener.recvfrom(2048)
    finally:
        fwd.close()
        listener.close()

    assert data.startswith(b"$GNRMC,")


def test_forward_tcp_serves_connected_clients():
    fwd = NmeaForwarder(tcp_host="127.0.0.1", tcp_port=0)
    try:
        host, port = fwd.tcp_bind_address

        client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        client.settimeout(2.0)
        client.connect((host, port))

        # accept_loop が客を取り込むのを待つ
        deadline = time.time() + 1.0
        while time.time() < deadline:
            if fwd._tcp_clients:
                break
            time.sleep(0.02)

        assert fwd._tcp_clients, "TCP client should have been accepted"

        fwd.forward(b"$GNGGA,123519,...")
        data = client.recv(2048)
        client.close()
    finally:
        fwd.close()

    assert data.startswith(b"$GNGGA,")
    assert data.endswith(b"\r\n")


def test_forward_tcp_removes_disconnected_clients():
    fwd = NmeaForwarder(tcp_host="127.0.0.1", tcp_port=0)
    try:
        host, port = fwd.tcp_bind_address

        client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        client.connect((host, port))

        deadline = time.time() + 1.0
        while time.time() < deadline and not fwd._tcp_clients:
            time.sleep(0.02)
        assert fwd._tcp_clients

        client.close()

        # 切れた相手に対して送信 → 自動で除去される
        for _ in range(3):
            fwd.forward(b"$GNGGA,123519,...")
            time.sleep(0.05)

        assert fwd._tcp_clients == []
    finally:
        fwd.close()


def test_forward_appends_crlf():
    listener, addr = _make_udp_listener()
    fwd = NmeaForwarder(udp_targets=[addr])
    try:
        fwd.forward(b"$GNGGA,no-crlf-here")
        data, _ = listener.recvfrom(2048)
    finally:
        fwd.close()
        listener.close()

    assert data == b"$GNGGA,no-crlf-here\r\n"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))

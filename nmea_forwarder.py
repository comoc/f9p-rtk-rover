# nmea_forwarder.py

import socket
import threading
from typing import Iterable, List, Optional, Tuple


def parse_host_port(spec: str) -> Tuple[str, int]:
    """'host:port' を (host, port) に分解する。"""
    if ":" not in spec:
        raise ValueError(f"invalid host:port spec: {spec!r}")

    host, port_str = spec.rsplit(":", 1)
    return host, int(port_str)


def sentence_id(raw: bytes) -> Optional[str]:
    """NMEA センテンス bytes から sentence ID (GGA / RMC など) を返す。

    例: b'$GNGGA,...' -> 'GGA'。
    NMEA でなければ None。
    """
    if not raw.startswith(b"$") or len(raw) < 7:
        return None

    try:
        head = raw[1:6].decode("ascii")
    except UnicodeDecodeError:
        return None

    if "," in head or not head.isalpha():
        return None

    return head[2:5]


class NmeaForwarder:
    """NMEA センテンスを UDP / TCP 経由で外部へ転送する。"""

    def __init__(
        self,
        udp_targets: Optional[Iterable[Tuple[str, int]]] = None,
        tcp_host: Optional[str] = None,
        tcp_port: Optional[int] = None,
        sentences: Optional[Iterable[str]] = None,
    ):
        self.udp_targets: List[Tuple[str, int]] = list(udp_targets or [])
        self.sentences: Optional[set] = (
            {s.strip().upper() for s in sentences} if sentences else None
        )

        self._udp_sock: Optional[socket.socket] = None
        if self.udp_targets:
            self._udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self._udp_sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)

        self._tcp_server: Optional[socket.socket] = None
        self._tcp_clients: List[socket.socket] = []
        self._tcp_lock = threading.Lock()
        self._tcp_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

        self.tcp_bind_address: Optional[Tuple[str, int]] = None

        if tcp_port is not None:
            self._start_tcp_server(tcp_host or "0.0.0.0", tcp_port)

    def _start_tcp_server(self, host: str, port: int) -> None:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind((host, port))
        sock.listen(8)
        sock.settimeout(0.5)

        self._tcp_server = sock
        self.tcp_bind_address = sock.getsockname()

        self._tcp_thread = threading.Thread(
            target=self._accept_loop, daemon=True
        )
        self._tcp_thread.start()

        print(
            f"[NMEA] TCP server listening on "
            f"{self.tcp_bind_address[0]}:{self.tcp_bind_address[1]}"
        )

    def _accept_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                client, addr = self._tcp_server.accept()
            except socket.timeout:
                continue
            except OSError:
                break

            with self._tcp_lock:
                self._tcp_clients.append(client)

            print(f"[NMEA] TCP client connected: {addr}")

    def forward(self, raw: bytes) -> None:
        """1つの NMEA センテンスを登録済みの全送信先へ送出する。"""
        if not raw:
            return

        if self.sentences is not None:
            sid = sentence_id(raw)
            if sid is None or sid not in self.sentences:
                return

        data = raw if raw.endswith(b"\r\n") else raw.rstrip(b"\r\n") + b"\r\n"

        if self._udp_sock is not None:
            for host, port in self.udp_targets:
                try:
                    self._udp_sock.sendto(data, (host, port))
                except OSError:
                    pass

        if self._tcp_clients:
            with self._tcp_lock:
                survivors: List[socket.socket] = []
                for cli in self._tcp_clients:
                    try:
                        cli.sendall(data)
                        survivors.append(cli)
                    except OSError:
                        try:
                            cli.close()
                        except OSError:
                            pass
                self._tcp_clients = survivors

    def close(self) -> None:
        self._stop_event.set()

        if self._tcp_server is not None:
            try:
                self._tcp_server.close()
            except OSError:
                pass

        with self._tcp_lock:
            for cli in self._tcp_clients:
                try:
                    cli.close()
                except OSError:
                    pass
            self._tcp_clients = []

        if self._udp_sock is not None:
            try:
                self._udp_sock.close()
            except OSError:
                pass

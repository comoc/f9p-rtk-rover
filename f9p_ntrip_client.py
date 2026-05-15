# f9p_ntrip_client.py

import argparse
import base64
import socket
import threading
import time
from typing import Optional

import serial
from pyubx2 import UBXReader, NMEA_PROTOCOL, UBX_PROTOCOL


def gga_quality_to_status(q) -> str:
    try:
        q = int(q)
    except Exception:
        return "UNKNOWN"

    return {
        0: "NO FIX",
        1: "3D/SINGLE",
        2: "DGNSS",
        4: "RTK FIXED",
        5: "RTK FLOAT",
        6: "DEAD RECKONING",
    }.get(q, f"UNKNOWN({q})")


def build_ntrip_request(
    host: str,
    port: int,
    mountpoint: str,
    user: Optional[str] = None,
    password: Optional[str] = None,
) -> bytes:
    mountpoint = mountpoint.lstrip("/")

    headers = [
        f"GET /{mountpoint} HTTP/1.1",
        f"Host: {host}:{port}",
        "User-Agent: NTRIP f9p-python-client/1.0",
        "Ntrip-Version: Ntrip/2.0",
        "Connection: close",
    ]

    if user and password:
        token = base64.b64encode(
            f"{user}:{password}".encode("utf-8")
        ).decode("ascii")
        headers.append(f"Authorization: Basic {token}")

    return ("\r\n".join(headers) + "\r\n\r\n").encode("ascii")


def read_ntrip_response(sock: socket.socket) -> bytes:
    data = b""

    while b"\r\n\r\n" not in data and len(data) < 4096:
        chunk = sock.recv(1)
        if not chunk:
            break
        data += chunk

    return data


def ntrip_worker(args, ser: serial.Serial, shared: dict, stop_event: threading.Event):
    if not args.host or not args.mountpoint:
        print("[NTRIP] disabled")
        return

    total_rtcm_bytes = 0

    while not stop_event.is_set():
        sock = None

        try:
            print("[NTRIP] connecting...")

            sock = socket.create_connection((args.host, args.port), timeout=10)
            sock.settimeout(10)

            request = build_ntrip_request(
                host=args.host,
                port=args.port,
                mountpoint=args.mountpoint,
                user=args.user,
                password=args.password,
            )

            sock.sendall(request)

            response = read_ntrip_response(sock)
            response_text = response.decode(errors="ignore")

            if "200" not in response_text and "ICY 200 OK" not in response_text:
                print("[NTRIP] bad response:")
                print(response_text.strip())
                time.sleep(args.reconnect_interval)
                continue

            print("[NTRIP] connected")
            if response_text:
                print(response_text.splitlines()[0])

            last_gga_sent = 0.0
            last_log = time.time()

            while not stop_event.is_set():
                now = time.time()

                if now - last_gga_sent >= args.gga_interval:
                    gga = shared.get("latest_gga")

                    if gga:
                        try:
                            sock.sendall(gga + b"\r\n")
                            if args.verbose:
                                print("[NTRIP] send GGA:", gga.decode(errors="ignore"))
                        except Exception as e:
                            raise ConnectionError(f"failed to send GGA: {e}")

                    last_gga_sent = now

                try:
                    data = sock.recv(4096)
                except socket.timeout:
                    continue

                if not data:
                    raise ConnectionError("NTRIP disconnected")

                written = ser.write(data)
                total_rtcm_bytes += written

                shared["rtcm_bytes"] = total_rtcm_bytes
                shared["last_rtcm_time"] = time.time()

                if args.verbose or time.time() - last_log >= 5:
                    print(f"[NTRIP] RTCM {written} bytes, total={total_rtcm_bytes}")
                    last_log = time.time()

        except Exception as e:
            print(f"[NTRIP] error: {e}")

            if sock:
                try:
                    sock.close()
                except Exception:
                    pass

            time.sleep(args.reconnect_interval)


def main():
    parser = argparse.ArgumentParser(
        description="ZED-F9P NMEA reader with optional NTRIP client"
    )

    parser.add_argument("--serial", required=True, help="例: COM9, /dev/ttyACM0")
    parser.add_argument("--baud", type=int, default=115200)

    # NTRIPは optional
    parser.add_argument("--host", default=None, help="NTRIP caster host")
    parser.add_argument("--port", type=int, default=2101)
    parser.add_argument("--mountpoint", default=None)

    parser.add_argument("--user", default=None)
    parser.add_argument("--password", default=None)

    parser.add_argument("--gga-interval", type=float, default=10.0)
    parser.add_argument("--reconnect-interval", type=float, default=5.0)
    parser.add_argument("--verbose", action="store_true")

    args = parser.parse_args()

    use_ntrip = bool(args.host and args.mountpoint)

    shared = {
        "latest_gga": None,
        "rtcm_bytes": 0,
        "last_rtcm_time": None,
    }

    stop_event = threading.Event()

    ser = serial.Serial(args.serial, args.baud, timeout=1)

    if use_ntrip:
        t = threading.Thread(
            target=ntrip_worker,
            args=(args, ser, shared, stop_event),
            daemon=True,
        )
        t.start()
    else:
        print("[NTRIP] disabled: --host and --mountpoint were not specified")

    ubr = UBXReader(
        ser,
        protfilter=NMEA_PROTOCOL | UBX_PROTOCOL,
    )

    print("reading GNSS messages...")

    try:
        while True:
            raw, msg = ubr.read()

            if msg is None:
                continue

            if msg.identity in ("GNGGA", "GPGGA", "GAGGA", "GLGGA"):
                shared["latest_gga"] = raw.strip()

                lat = getattr(msg, "lat", None)
                lon = getattr(msg, "lon", None)
                alt = getattr(msg, "alt", None)
                quality = getattr(msg, "quality", None)
                num_sv = getattr(msg, "numSV", None)
                hdop = getattr(msg, "HDOP", None)

                status = gga_quality_to_status(quality)

                if use_ntrip:
                    rtcm_bytes = shared.get("rtcm_bytes", 0)
                    last_rtcm_time = shared.get("last_rtcm_time")

                    if last_rtcm_time:
                        rtcm_age = time.time() - last_rtcm_time
                        rtcm_info = f"RTCM={rtcm_bytes} bytes, age={rtcm_age:.1f}s"
                    else:
                        rtcm_info = "RTCM=none"
                else:
                    rtcm_info = "NTRIP=off"

                print(
                    f"{status} | "
                    f"lat={lat:.8f}, lon={lon:.8f}, "
                    f"alt={alt}m, sats={num_sv}, hdop={hdop}, "
                    f"{rtcm_info}"
                )

            elif msg.identity == "NAV-PVT":
                if not args.verbose:
                    continue

                carr_soln = getattr(msg, "carrSoln", None)
                fix_type = getattr(msg, "fixType", None)

                if carr_soln == 2:
                    ubx_status = "RTK FIXED"
                elif carr_soln == 1:
                    ubx_status = "RTK FLOAT"
                elif fix_type == 3:
                    ubx_status = "3D FIX"
                elif fix_type == 2:
                    ubx_status = "2D FIX"
                else:
                    ubx_status = f"fixType={fix_type}, carrSoln={carr_soln}"

                lat = getattr(msg, "lat", None)
                lon = getattr(msg, "lon", None)
                height = getattr(msg, "hMSL", None)

                if height is not None:
                    height = height / 1000.0

                print(
                    f"UBX {ubx_status} | "
                    f"lat={lat}, lon={lon}, hMSL={height}m"
                )

    except KeyboardInterrupt:
        print("stopping...")

    finally:
        stop_event.set()
        ser.close()


if __name__ == "__main__":
    main()
"""動作確認用 UDP listener (実機テスト用、pytest対象外)。"""

import socket


def main() -> None:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("127.0.0.1", 10110))
    sock.settimeout(20)

    for i in range(10):
        try:
            data, addr = sock.recvfrom(2048)
        except socket.timeout:
            print(f"[{i}] timeout")
            break
        print(f"[{i}] from {addr}: {data.decode(errors='replace').strip()}")

    sock.close()


if __name__ == "__main__":
    main()

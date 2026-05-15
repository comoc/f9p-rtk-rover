# f9p_ntrip_client

u-blox ZED-F9P から NMEA / UBX メッセージを読み取り、必要に応じて NTRIP キャスターから受信した RTCM 補正データを受信機にフィードする Python クライアント。

## 機能

- シリアル経由で ZED-F9P の GGA / NAV-PVT を解析・表示
- GGA の Quality からフィックス状態（RTK FIXED / RTK FLOAT / DGNSS / 3D など）を判定
- NTRIP キャスターに接続し RTCM3 を受信機にスルー転送（VRS 対応として GGA を定期送信）
- NTRIP は任意（指定しなければローカル受信のみで動作）
- 切断時の自動再接続

## 動作環境

- Python 3.8 以上
- ZED-F9P など u-blox F9 系受信機（USB シリアル接続）

## インストール

```bash
pip install -r requirements.txt
```

依存ライブラリ:

- `pyserial`
- `pyubx2`

## 使い方

### 1. ローカルのみ（NTRIP 無効）

```bash
python f9p_ntrip_client.py --serial COM9 --baud 115200
```

### 2. NTRIP クライアントとして利用

```bash
python f9p_ntrip_client.py ^
  --serial COM9 ^
  --baud 115200 ^
  --host rtk2go.example.com ^
  --port 2101 ^
  --mountpoint MOUNT_NAME ^
  --user USERNAME ^
  --password PASSWORD
```

`--host` と `--mountpoint` の両方が指定された場合のみ NTRIP スレッドが起動する。

## オプション

| オプション | 既定値 | 説明 |
|------------|--------|------|
| `--serial` | （必須） | シリアルポート（例: `COM9`, `/dev/ttyACM0`） |
| `--baud` | `115200` | ボーレート |
| `--host` | `None` | NTRIP キャスターのホスト名 |
| `--port` | `2101` | NTRIP キャスターのポート |
| `--mountpoint` | `None` | マウントポイント名 |
| `--user` | `None` | NTRIP 認証ユーザー |
| `--password` | `None` | NTRIP 認証パスワード |
| `--gga-interval` | `10.0` | GGA を NTRIP キャスターへ送る間隔（秒） |
| `--reconnect-interval` | `5.0` | NTRIP 切断時の再接続待機時間（秒） |
| `--verbose` | `False` | NAV-PVT や RTCM 受信量の詳細ログを出力 |

## 出力例

```
reading GNSS messages...
[NTRIP] connecting...
[NTRIP] connected
ICY 200 OK
RTK FIXED | lat=xx.xxxxxxxx, lon=xxx.xxxxxxxx, alt=xx.xm, sats=22, hdop=0.6, RTCM=1024 bytes, age=0.2s
```

## 停止方法

`Ctrl+C` で終了。シリアルポートと NTRIP 接続はクローズされる。

## ライセンス

未指定。

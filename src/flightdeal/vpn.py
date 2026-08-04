"""VPN(WireGuard/Surfshark)によるIP切替（要件変更: 多空港対応のため追加）。

投資スクレイパ(nikkei_DB)の v6 の方式を踏襲する:
  - 実行前に外部IP/組織を確認し、自宅IPのままなら中断（VPN必須ゲート）
  - Bot判定を検知したらサーバーを切り替えてIP変化を待って再開
  - v5 でプログラム自動切替(wireguard.exe /installtunnelservice)を試したが
    「このPCでは不安定」だったため、v6 は手動切替方式に落ち着いた。
    本実装は両対応（config の vpn.mode で選ぶ）:
      "manual" … Bot判定時に手動切替を促し、IP変化を待つ（v6と同じ・確実）
      "auto"   … wireguard.exe でトンネルを付け替える（v5方式・要管理者権限）
      "off"    … VPNを使わない（自宅IPで実行）

ネットワークとOSに触れる部分と、純粋な判定ロジックを分離してある
（判定ロジックはテストできるように）。
"""

from __future__ import annotations

import logging
import random
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path

log = logging.getLogger(__name__)

IP_SERVICES = ("https://ipinfo.io/json", "https://api.ipify.org?format=json")
WIREGUARD_EXE_CANDIDATES = (
    r"C:\Program Files\WireGuard\wireguard.exe",
    r"C:\Program Files (x86)\WireGuard\wireguard.exe",
)


@dataclass
class VpnConfig:
    enabled: bool = False
    mode: str = "manual"                 # "manual" | "auto" | "off"
    conf_dir: str = "VPN"                # .conf 置き場（自宅の絶対/相対パス）
    home_ip: str = ""                    # 自宅の外部IP（分かれば）
    home_org_hint: str = ""              # ISP識別子（org にこれが含まれれば自宅とみなす）
    wireguard_exe: str = ""              # 空なら既定パスを探索
    switch_timeout: int = 40             # IP変化を待つ最大秒数

    @classmethod
    def from_dict(cls, raw: dict | None) -> "VpnConfig":
        raw = raw or {}
        return cls(
            enabled=bool(raw.get("enabled", False)),
            mode=str(raw.get("mode", "manual")),
            conf_dir=str(raw.get("conf_dir", "VPN")),
            home_ip=str(raw.get("home_ip", "")),
            home_org_hint=str(raw.get("home_org_hint", "")),
            wireguard_exe=str(raw.get("wireguard_exe", "")),
            switch_timeout=int(raw.get("switch_timeout", 40)),
        )


# --- 純粋ロジック（テスト可能・I/Oなし） ---


def looks_like_home(ip: str | None, org: str | None, cfg: VpnConfig) -> bool:
    """外部IP/組織から「VPN未接続（自宅IP）」かどうかを判定する。

    v6 の looks_like_home を踏襲。home_ip 完全一致、または org に
    home_org_hint が含まれれば自宅とみなす。どちらも未設定なら判定不能（False）。
    """
    if cfg.home_ip and ip and ip == cfg.home_ip:
        return True
    if cfg.home_org_hint and org and cfg.home_org_hint.lower() in org.lower():
        return True
    return False


# --- I/Oを伴う部分 ---


def external_ip_info(timeout: int = 8) -> tuple[str | None, str | None, str | None]:
    """(ip, country, org) を返す。取得できなければ (None, None, None)。"""
    try:
        import requests
    except ImportError:  # pragma: no cover
        return None, None, None

    try:
        j = requests.get(IP_SERVICES[0], timeout=timeout).json()
        return j.get("ip"), j.get("country"), j.get("org")
    except Exception:
        pass
    try:
        j = requests.get(IP_SERVICES[1], timeout=timeout).json()
        return j.get("ip"), None, None
    except Exception:
        return None, None, None


def fetch_with_rotation(fetcher, vpn, origin: str, destination: str, day,
                        max_rotations: int = 3):
    """取得する。Bot判定なら VPN を切り替えて再試行する。

    survey / search など複数のスクリプトから使う共通処理。
    BlockedError（Bot判定）だけを切替対象にする。通常の取得失敗は
    IPを変えても直らないので、そのまま送出して上位の隔離処理に任せる。

    Args:
        fetcher: FlightFetcher
        vpn: VpnController または None（None なら切替せず送出）
        max_rotations: 何回まで切り替えて粘るか
    """
    from .fetchers.base import BlockedError

    for attempt in range(max_rotations + 1):
        try:
            return fetcher.fetch(origin, destination, day)
        except BlockedError:
            if vpn is None or attempt == max_rotations:
                raise
            new_ip = vpn.rotate()
            if not new_ip:
                raise
            # 新しいIPで張り直す（古いセッションは前のIPに紐づいている）
            fetcher.close()

    raise RuntimeError("unreachable")


@dataclass
class VpnController:
    """VPNの状態確認と切替を担う。"""

    cfg: VpnConfig
    base_dir: Path = field(default_factory=Path.cwd)
    _confs: list[Path] = field(default_factory=list)
    _index: int = 0
    _current_ip: str | None = None

    def __post_init__(self) -> None:
        conf_path = Path(self.cfg.conf_dir)
        if not conf_path.is_absolute():
            conf_path = self.base_dir / conf_path
        self._confs = sorted(conf_path.glob("*.conf")) if conf_path.is_dir() else []

    # ---- ゲート ----

    def require_vpn(self) -> None:
        """VPN必須の確認。自宅IPのままなら RuntimeError で止める。

        cfg.enabled が False、または mode が "off" なら何もしない。
        """
        if not self.cfg.enabled or self.cfg.mode == "off":
            return

        ip, country, org = external_ip_info()
        self._current_ip = ip
        log.info("vpn_ip", extra={"ip": ip, "country": country, "org": org})
        print(f"現在の外部IP: {ip}  国: {country}  組織: {org}")

        if ip is None:
            raise RuntimeError("外部IPを取得できませんでした。ネットワークを確認してください。")

        if looks_like_home(ip, org, self.cfg):
            raise RuntimeError(
                "自宅IP（VPN未接続）と判定しました。\n"
                "  Surfshark等で任意のサーバーに接続してから再実行してください。\n"
                "  （config の vpn.home_ip / home_org_hint で判定しています）"
            )
        print("  → VPN接続を確認。処理を開始します。")

    # ---- 切替 ----

    def rotate(self) -> str | None:
        """Bot判定時にIPを切り替える。新しいIPを返す（失敗時 None）。"""
        if self.cfg.mode == "auto":
            return self._rotate_auto()
        return self._rotate_manual()

    def _wait_ip_change(self, prev_ip: str | None) -> str | None:
        deadline = time.time() + self.cfg.switch_timeout
        while time.time() < deadline:
            ip, _, _ = external_ip_info(timeout=6)
            if ip and ip != prev_ip:
                self._current_ip = ip
                return ip
            time.sleep(2)
        return None

    def _rotate_manual(self) -> str | None:
        """v6方式: 手動でサーバーを切り替えてもらい、IP変化を待つ。"""
        prev = self._current_ip
        print("\n" + "=" * 56)
        print("⚠ Bot判定を検知しました。VPNサーバーを切り替えてください。")
        print("  Surfsharkアプリで別のサーバーに接続 → このまま待機します。")
        print(f"  （最大 {self.cfg.switch_timeout} 秒、IPの変化を検出したら自動再開）")
        print("=" * 56)
        new_ip = self._wait_ip_change(prev)
        if new_ip:
            print(f"  → 新しいIP {new_ip} を検出。再開します。\n")
        else:
            print("  → IPの変化を検出できませんでした。\n")
        return new_ip

    def _rotate_auto(self) -> str | None:
        """v5方式: wireguard.exe でトンネルを付け替える（要管理者権限）。"""
        exe = self._wireguard_exe()
        if not exe or not self._confs:
            log.warning("vpn_auto_unavailable",
                        extra={"exe": bool(exe), "confs": len(self._confs)})
            # 自動が使えないなら手動にフォールバック
            return self._rotate_manual()

        prev = self._current_ip
        # 直前のトンネルを外す
        if self._confs:
            self._uninstall(exe, self._confs[self._index].stem)
        self._index = (self._index + 1) % len(self._confs)
        conf = self._confs[self._index]

        print(f"\n⚠ Bot判定を検知。VPNを {conf.stem} に切り替えます...")
        err = self._install(exe, conf)
        if err:
            log.warning("vpn_install_failed", extra={"conf": conf.stem, "error": err})
            print(f"  切替失敗（{err[:60]}）。手動切替に切り替えます。")
            return self._rotate_manual()

        new_ip = self._wait_ip_change(prev)
        if new_ip:
            print(f"  → {conf.stem} に接続、新IP {new_ip}。再開します。\n")
        else:
            print(f"  → {conf.stem} に接続したがIPが変わりません。\n")
        return new_ip

    def close(self) -> None:
        """auto モードで張ったトンネルを片付ける。"""
        if self.cfg.mode != "auto" or not self._confs:
            return
        exe = self._wireguard_exe()
        if exe:
            self._uninstall(exe, self._confs[self._index].stem)

    # ---- WireGuard 実行ヘルパ ----

    def _wireguard_exe(self) -> str | None:
        if self.cfg.wireguard_exe and Path(self.cfg.wireguard_exe).exists():
            return self.cfg.wireguard_exe
        for cand in WIREGUARD_EXE_CANDIDATES:
            if Path(cand).exists():
                return cand
        return shutil.which("wireguard.exe") or shutil.which("wireguard")

    @staticmethod
    def _install(exe: str, conf: Path) -> str:
        try:
            cp = subprocess.run([exe, "/installtunnelservice", str(conf)],
                                capture_output=True, text=True, timeout=60)
        except (OSError, subprocess.TimeoutExpired) as e:
            return str(e)
        if cp.returncode != 0:
            return (cp.stderr or cp.stdout or f"returncode={cp.returncode}").strip()
        return ""

    @staticmethod
    def _uninstall(exe: str, name: str) -> None:
        try:
            subprocess.run([exe, "/uninstalltunnelservice", name],
                           capture_output=True, text=True, timeout=60)
        except Exception:
            pass
        time.sleep(1)

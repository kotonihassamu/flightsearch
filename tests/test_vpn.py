"""VPN判定ロジックのテスト（I/Oを伴わない純粋部分のみ）。

実際のWireGuard操作やIP取得はOS/ネットワーク依存なのでテストしない。
自宅IP判定と設定パースだけを検証する。
"""

from __future__ import annotations

from flightdeal.vpn import VpnConfig, VpnController, looks_like_home


def test_config_from_dict_defaults():
    cfg = VpnConfig.from_dict(None)
    assert cfg.enabled is False
    assert cfg.mode == "manual"
    assert cfg.conf_dir == "VPN"


def test_config_from_dict_values():
    cfg = VpnConfig.from_dict({
        "enabled": True, "mode": "auto", "conf_dir": "C:/vpn",
        "home_ip": "1.2.3.4", "home_org_hint": "SoftBank", "switch_timeout": 60,
    })
    assert cfg.enabled is True
    assert cfg.mode == "auto"
    assert cfg.home_ip == "1.2.3.4"
    assert cfg.switch_timeout == 60


def test_looks_like_home_by_ip():
    cfg = VpnConfig(home_ip="203.0.113.5")
    assert looks_like_home("203.0.113.5", None, cfg) is True
    assert looks_like_home("198.51.100.9", None, cfg) is False


def test_looks_like_home_by_org():
    cfg = VpnConfig(home_org_hint="SoftBank")
    assert looks_like_home("1.2.3.4", "SoftBank Corp.", cfg) is True
    assert looks_like_home("1.2.3.4", "AS12345 Surfshark", cfg) is False


def test_looks_like_home_needs_config():
    """home_ip も home_org_hint も未設定なら判定不能（False）。"""
    cfg = VpnConfig()
    assert looks_like_home("1.2.3.4", "any org", cfg) is False


def test_require_vpn_noop_when_disabled():
    """enabled=False なら何もチェックしない（例外を出さない）。"""
    ctrl = VpnController(VpnConfig(enabled=False))
    ctrl.require_vpn()  # 例外が出なければOK


def test_require_vpn_noop_when_mode_off():
    ctrl = VpnController(VpnConfig(enabled=True, mode="off"))
    ctrl.require_vpn()


def test_controller_finds_conf_files(tmp_path):
    (tmp_path / "VPN").mkdir()
    (tmp_path / "VPN" / "uk-lon.conf").write_text("x", encoding="utf-8")
    (tmp_path / "VPN" / "jp-tok.conf").write_text("x", encoding="utf-8")

    ctrl = VpnController(VpnConfig(conf_dir="VPN"), base_dir=tmp_path)
    assert len(ctrl._confs) == 2

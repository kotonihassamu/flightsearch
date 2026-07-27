# ネットワーク/DNS の切り分け診断
import socket

print("=" * 60)
print("[1] システムDNSで google.com を名前解決できるか")
try:
    ip = socket.gethostbyname("www.google.com")
    print("   OK ->", ip)
    sys_dns_ok = True
except Exception as e:
    print("   NG ->", type(e).__name__, e)
    sys_dns_ok = False

print("\n[2] requests（システムDNS＋通常HTTP）で Google Flights に到達できるか")
try:
    import requests
    r = requests.get("https://www.google.com/travel/flights", timeout=15)
    print("   OK -> status", r.status_code, "/ bytes", len(r.content))
    requests_ok = True
except Exception as e:
    print("   NG ->", type(e).__name__, str(e)[:200])
    requests_ok = False

print("\n[3] primp（fast-flights が内部で使うHTTPクライアント）で到達できるか")
try:
    import primp
    c = primp.Client(impersonate="chrome_131")
    r = c.get("https://www.google.com/travel/flights")
    print("   OK -> status", r.status_code)
    primp_ok = True
except Exception as e:
    print("   NG ->", type(e).__name__, str(e)[:200])
    primp_ok = False

print("\n" + "=" * 60)
print("判定:")
if sys_dns_ok and requests_ok and not primp_ok:
    print("  → システムは通るが primp だけ失敗。primp独自DNSがブロックされている。")
    print("    fast-flights の primp 依存が問題。回避策を検討する。")
elif not sys_dns_ok:
    print("  → システムDNS自体が拒否。ネットワーク（会社FW等）がGoogleを遮断。")
    print("    別ネットワーク（自宅/テザリング）かGitHub Actionsでの実行が必要。")
elif sys_dns_ok and not requests_ok:
    print("  → 名前解決は通るがHTTPが遮断。プロキシ/FWがGoogleを遮断。")
else:
    print("  → 全て到達可能。先ほどのエラーは一時的だった可能性。再実行を。")

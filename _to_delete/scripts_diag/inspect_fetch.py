# 本命: requests で取得 → fast_flights.parser.parse で解析（primp回避）
import requests
from fast_flights import FlightQuery, Passengers, create_filter
from fast_flights.parser import parse

URL = "https://www.google.com/travel/flights"
HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"),
    "Accept-Language": "ja,en-US;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

q = create_filter(
    flights=[FlightQuery(date="2026-08-01", from_airport="HND", to_airport="HIJ")],
    trip="one-way", seat="economy",
    passengers=Passengers(adults=1),
    currency="JPY", language="ja", max_stops=0,
)
params = q.params()
print("params:", params)

resp = requests.get(URL, params=params, headers=HEADERS, timeout=30)
print("status:", resp.status_code, "/ bytes:", len(resp.content))
print("最終URL:", resp.url[:120])

has_script = 'ds:1' in resp.text or r'ds\:1' in resp.text
print("ds:1 スクリプトの存在:", has_script)

try:
    result = parse(resp.text)
except Exception as e:
    import traceback
    print("\nparse エラー:", type(e).__name__, e)
    traceback.print_exc()
    snippet = resp.text[:500]
    print("\nHTML先頭:", snippet)
    raise SystemExit(1)

print("\n解析成功。便数:", len(result))
airlines_meta = {a.code: a.name for a in result.metadata.airlines}
print("メタ(航空会社コード->名):", dict(list(airlines_meta.items())[:10]))

for i, fl in enumerate(result[:5]):
    print(f"\n--- {i+1}件目 ---")
    print("  type:", repr(fl.type))
    print("  price:", repr(fl.price), "(", type(fl.price).__name__, ")")
    print("  airlines:", repr(fl.airlines))
    print("  区間数(stops+1):", len(fl.flights))
    seg = fl.flights[0]
    print("  seg from->to:", seg.from_airport.code, "->", seg.to_airport.code)
    print("  departure:", repr(seg.departure), "| time attr:", repr(getattr(seg.departure, "time", "?")),
          "| date attr:", repr(getattr(seg.departure, "date", "?")))
    print("  arrival:  ", repr(seg.arrival), "| time attr:", repr(getattr(seg.arrival, "time", "?")))
    print("  duration:", repr(seg.duration), "| plane:", repr(seg.plane_type))
    if hasattr(seg.departure, "__dict__"):
        print("  departure vars:", vars(seg.departure))

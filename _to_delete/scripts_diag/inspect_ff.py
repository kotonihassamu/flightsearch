# fast-flights 3.x の API を調べる診断スクリプト（Phase 0 用）
import inspect

print("=" * 60)
try:
    import fast_flights
except Exception as e:
    print("import 自体が失敗:", type(e).__name__, e)
    raise SystemExit(1)

print("version:", getattr(fast_flights, "__version__", "不明"))
print("公開名:", [n for n in dir(fast_flights) if not n.startswith("_")])
print("=" * 60)

for name in ["get_flights", "get_flights_from_filter", "FlightData",
             "Passengers", "TFSData", "create_filter", "Result", "search"]:
    obj = getattr(fast_flights, name, None)
    if obj is None:
        continue
    print(f"\n### {name}")
    try:
        print("  signature:", inspect.signature(obj))
    except (TypeError, ValueError):
        pass
    doc = inspect.getdoc(obj)
    if doc:
        print("  doc:", doc.splitlines()[0][:200])

print("\n" + "=" * 60)
print("実際に1回取得してみる（HND->HIJ / 2026-08-01）")
print("=" * 60)
try:
    from fast_flights import FlightData, Passengers, get_flights
    result = get_flights(
        flight_data=[FlightData(date="2026-08-01", from_airport="HND", to_airport="HIJ")],
        trip="one-way", seat="economy",
        passengers=Passengers(adults=1),
        fetch_mode="fallback",
    )
    print("result type:", type(result).__name__)
    print("result attrs:", [n for n in dir(result) if not n.startswith("_")])
    flights = getattr(result, "flights", None)
    print("flights 件数:", len(flights) if flights is not None else "flights属性なし")
    if flights:
        f = flights[0]
        print("1件目 type:", type(f).__name__)
        print("1件目 attrs:", [n for n in dir(f) if not n.startswith("_")])
        print("1件目 中身:", vars(f) if hasattr(f, "__dict__") else f)
except Exception as e:
    import traceback
    print("取得でエラー:", type(e).__name__, e)
    traceback.print_exc()

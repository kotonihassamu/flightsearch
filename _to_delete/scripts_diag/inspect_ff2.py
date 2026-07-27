# fast-flights 3.x 新API で実際に取得してデータ構造を調べる
import inspect
import fast_flights
from fast_flights import FlightQuery, Passengers, create_filter, get_flights

print("=" * 60)
print("FlightQuery signature:", inspect.signature(FlightQuery))
print("=" * 60)

# クエリ組み立て（引数名が違う場合に備えて2通り試す）
q = None
for kwargs in (
    dict(date="2026-08-01", from_airport="HND", to_airport="HIJ"),
    dict(date="2026-08-01", origin="HND", destination="HIJ"),
):
    try:
        fq = FlightQuery(**kwargs)
        q = create_filter(
            flights=[fq], trip="one-way", seat="economy",
            passengers=Passengers(adults=1),
            currency="JPY", language="ja", max_stops=0,
        )
        print("クエリ組み立て成功。使った引数:", list(kwargs))
        break
    except Exception as e:
        print("試行失敗:", list(kwargs), "->", type(e).__name__, e)

if q is None:
    raise SystemExit("FlightQuery の引数を特定できませんでした")

print("=" * 60)
print("get_flights 実行中...")
try:
    result = get_flights(q)
except Exception as e:
    import traceback
    print("取得エラー:", type(e).__name__, e)
    traceback.print_exc()
    raise SystemExit(1)

print("result type:", type(result).__name__)
print("result attrs:", [n for n in dir(result) if not n.startswith("_")])

flights = getattr(result, "flights", None)
if flights is None:
    # ResultList 自体がリストの可能性
    try:
        flights = list(result)
    except Exception:
        pass

print("flights 件数:", len(flights) if flights is not None else "取得できず")

if flights:
    for idx, f in enumerate(flights[:3]):
        print(f"\n--- {idx+1}件目 ({type(f).__name__}) ---")
        print("attrs:", [n for n in dir(f) if not n.startswith("_")])
        if hasattr(f, "__dict__"):
            print("中身:", vars(f))
        else:
            for a in ("name", "airline", "departure", "arrival", "price", "stops",
                      "duration", "arrival_time_ahead", "is_best"):
                if hasattr(f, a):
                    print(f"  {a} = {getattr(f, a)!r}")

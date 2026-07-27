# fast-flights 3.x の内部構造を調べる（requests で取得できるようにするため）
import inspect
import fast_flights
from fast_flights import FlightQuery, Passengers, create_filter

def dump_source(mod, label):
    print("=" * 60)
    print(f"### {label} のソース")
    print("=" * 60)
    try:
        print(inspect.getsource(mod))
    except Exception as e:
        print("ソース取得不可:", e)

# fetcher と parser のソースを丸ごと見る（小さいはず）
dump_source(fast_flights.fetcher, "fetcher")
dump_source(fast_flights.parser, "parser")

# Query オブジェクトから tfs / URL を取り出せるか
print("=" * 60)
print("### Query オブジェクトの中身")
print("=" * 60)
q = create_filter(
    flights=[FlightQuery(date="2026-08-01", from_airport="HND", to_airport="HIJ")],
    trip="one-way", seat="economy",
    passengers=Passengers(adults=1),
    currency="JPY", language="ja", max_stops=0,
)
print("type:", type(q))
print("attrs:", [n for n in dir(q) if not n.startswith("_")])
for a in ("tfs", "encode", "to_string", "as_b64", "b64"):
    if hasattr(q, a):
        val = getattr(q, a)
        try:
            val = val() if callable(val) else val
        except Exception as ex:
            val = f"(呼び出し失敗: {ex})"
        print(f"  q.{a} = {val!r}")
if hasattr(q, "__dict__"):
    print("  vars:", vars(q))

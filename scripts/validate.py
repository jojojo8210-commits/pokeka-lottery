"""data/ の整合性を検証する。GitHub Actions から自動実行される。失敗すると終了コード1。"""
import json
import os
import sys
from datetime import datetime
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
errors = []

schema = json.loads((ROOT / "data/schema.json").read_text(encoding="utf-8"))
items = json.loads((ROOT / "data/lotteries.json").read_text(encoding="utf-8"))
chains = yaml.safe_load((ROOT / "data/chains.yaml").read_text(encoding="utf-8"))["chains"]
shops = yaml.safe_load((ROOT / "data/shops.yaml").read_text(encoding="utf-8"))["shops"]
chain_ids = {c["id"] for c in chains}
shop_ids = {s["id"] for s in shops}

try:
    import jsonschema
except ImportError:
    jsonschema = None
    if os.environ.get("CI"):
        errors.append("jsonschema が未導入です")
    else:
        print("注意: jsonschema 未導入のため、スキーマ検証はスキップします")


def parse(v):
    return datetime.fromisoformat(v) if v else None


seen = set()
for it in items:
    i = it.get("id", "(idなし)")
    if jsonschema:
        try:
            jsonschema.validate(it, schema)
        except jsonschema.ValidationError as e:
            errors.append(f"{i}: スキーマ違反: {e.message}")
    if i in seen:
        errors.append(f"{i}: idが重複しています")
    seen.add(i)
    if it.get("shop_id") not in shop_ids:
        errors.append(f"{i}: shop_id '{it.get('shop_id')}' が shops.yaml にありません")
    if it.get("chain_id") and it["chain_id"] not in chain_ids:
        errors.append(f"{i}: chain_id '{it['chain_id']}' が chains.yaml にありません")
    for k in ("entry_start", "entry_end", "result_date", "purchase_start", "purchase_end", "first_seen_at", "last_verified_at"):
        try:
            parse(it.get(k))
        except ValueError:
            errors.append(f"{i}: {k} が日時として読めません")
    try:
        s, e = parse(it.get("entry_start")), parse(it.get("entry_end"))
        if s and e and e < s:
            errors.append(f"{i}: 受付終了が開始より前です")
    except ValueError:
        pass
    if not it.get("entry_end") and not it.get("review_needed"):
        errors.append(f"{i}: 締切が不明なのに review_needed が false です")
    if it.get("source_grade") == "third_party" and not it.get("review_needed"):
        errors.append(f"{i}: 第三者の出典なのに review_needed が false です")

for s in shops:
    if s.get("chain_id") and s["chain_id"] not in chain_ids:
        errors.append(f"shops.yaml {s['id']}: chain_id '{s['chain_id']}' が chains.yaml にありません")

if errors:
    print("検証に失敗しました:")
    for m in errors:
        print(" -", m)
    sys.exit(1)
print(f"検証OK: 抽選{len(items)}件 / 店舗{len(shops)}件 / チェーン{len(chains)}件")

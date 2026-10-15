#!/usr/bin/env python3
"""ゴールドセット(正解付きの告知30件ほど)で、抽出の精度を測る。

使い方:
  ANTHROPIC_API_KEY=... python scripts/eval_gold.py            # gold/ のすべて
  python scripts/eval_gold.py --gold-dir /path/to/gold --case case-001

ゴールドセットは告知文や画像のコピーを含むため、公開リポジトリには置かない(.gitignore 済みの gold/ か、手元で管理)。
合格基準(環境変数で変更可): 日付系 99% / 全体 95%
"""
from __future__ import annotations

import argparse
import json
import mimetypes
import os
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import collect  # noqa: E402

CRITICAL = ["entry_start", "entry_end", "result_date", "purchase_start", "purchase_end"]
OTHER = [
    "method", "entry_channel", "window_type", "price_yen", "limit_per_person",
    "payment.restriction", "shrink", "may_close_early", "exclusive_group",
    "requirements", "entry_steps",
]
DEFAULTS = {"method": "unknown", "entry_channel": "unknown", "window_type": "fixed", "shrink": "unknown",
            "may_close_early": False, "payment.restriction": "unknown"}
CRIT_MIN = float(os.environ.get("GOLD_CRITICAL_MIN", "0.99"))
ALL_MIN = float(os.environ.get("GOLD_ALL_MIN", "0.95"))


def get(d: dict, dotted: str):
    cur = d
    for k in dotted.split("."):
        if not isinstance(cur, dict) or k not in cur:
            return None
        cur = cur[k]
    return cur


def comparable(field: str, lot: dict):
    """正解・抽出結果を、比べられる形にそろえる。"""
    v = get(lot, field)
    if field in CRITICAL:
        iso, _, _ = collect.normalize_dt(field, v)
        d = collect.parse_dt(iso)
        return d.isoformat() if d else None
    if field == "requirements":
        return sorted(r["key"] if isinstance(r, dict) else r for r in (v or []))
    if field == "entry_steps":
        return sorted(s["type"] if isinstance(s, dict) else s for s in (v or []))
    if field == "exclusive_group":
        return bool(v)
    if v is None:
        return DEFAULTS.get(field)
    return v


def pair(expected: list, got: list):
    """正解と抽出結果の抽選を、商品名と受付開始で対応づける。"""
    used, pairs = set(), []
    for e in expected:
        best = None
        for i, g in enumerate(got):
            if i in used:
                continue
            same_prod = collect.norm(e.get("product", "")) in collect.norm(g.get("product", "")) or \
                collect.norm(g.get("product", "")) in collect.norm(e.get("product", ""))
            if same_prod and (best is None or comparable("entry_start", e) == comparable("entry_start", g)):
                best = i
        if best is None and len(expected) == len(got) and len(got) - len(used) > 0:
            best = next(i for i in range(len(got)) if i not in used)  # 商品名が違っても件数が同じなら順番で対応
        if best is not None:
            used.add(best)
            pairs.append((e, got[best]))
        else:
            pairs.append((e, None))
    extras = [g for i, g in enumerate(got) if i not in used]
    return pairs, extras


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--gold-dir", default=str(collect.ROOT / "gold"))
    ap.add_argument("--case", help="case_id を指定して1件だけ評価")
    ap.add_argument("--no-cache", action="store_true", default=True)
    args = ap.parse_args()

    gold_dir = Path(args.gold_dir)
    files = sorted(p for p in gold_dir.glob("*.json") if not p.name.startswith("_"))
    if args.case:
        files = [p for p in files if p.stem == args.case]
    if not files:
        print(f"ゴールドセットが見つかりません: {gold_dir}")
        return 2

    import anthropic

    ctx = collect.make_ctx(anthropic.Anthropic(), use_cache=False)
    ctx["extractions"] = -10_000  # 評価では上限を適用しない
    crit_hit = crit_total = oth_hit = oth_total = extra_total = unverified = 0
    for p in files:
        case = json.loads(p.read_text(encoding="utf-8"))
        src = {"id": case["case_id"], "type": "html", **case["source"]}
        src.setdefault("url", "https://example.invalid/")
        now = datetime.fromisoformat(case["now"]) if case.get("now") else collect.now_jst()
        text, image = case["input"].get("text"), None
        if case["input"].get("image"):
            ip = gold_dir / case["input"]["image"]
            image = (mimetypes.guess_type(ip.name)[0] or "image/png", ip.read_bytes())
        cands = collect.process_document(ctx, src, text, now, [], image)
        got = [c["lottery"] for c in cands]
        pairs, extras = pair(case["expected"]["lotteries"], got)
        extra_total += len(extras)
        unverified += sum(1 for c in cands for r in c["reasons"] if r.startswith("根拠を原文で確認できない"))
        misses = []
        for e, g in pairs:
            for f in CRITICAL:
                crit_total += 1
                ok = g is not None and comparable(f, e) == comparable(f, g)
                crit_hit += ok
                if not ok:
                    misses.append((f, comparable(f, e), comparable(f, g) if g else "(抽出なし)"))
            for f in OTHER:
                oth_total += 1
                ok = g is not None and comparable(f, e) == comparable(f, g)
                oth_hit += ok
                if not ok:
                    misses.append((f, comparable(f, e), comparable(f, g) if g else "(抽出なし)"))
        status = "OK " if not misses and not extras else "NG "
        print(f"{status}{case['case_id']}  抽選{len(pairs)}件 / 余分な抽出{len(extras)}件")
        for f, exp, act in misses:
            print(f"     - {f}: 正解={exp} / 抽出={act}")

    crit = crit_hit / crit_total if crit_total else 0
    allr = (crit_hit + oth_hit) / (crit_total + oth_total) if (crit_total + oth_total) else 0
    print("\n===== 結果 =====")
    print(f"ケース数: {len(files)}  (30件未満だと参考値)")
    print(f"日付系の一致率: {crit:.1%}  (合格 {CRIT_MIN:.0%})")
    print(f"全体の一致率:   {allr:.1%}  (合格 {ALL_MIN:.0%})")
    print(f"余分に抽出された抽選: {extra_total}件 / 根拠を原文で確認できなかった項目: {unverified}件")
    return 0 if (crit >= CRIT_MIN and allr >= ALL_MIN and extra_total == 0) else 1


if __name__ == "__main__":
    sys.exit(main())

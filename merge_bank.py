#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
把 bank/ 下的各分组题库合并成 bank/all.json（按 id 去重，先到先得）。

为什么单独出一个文件：GitHub Actions 的 YAML 缩进块里没法干净地用 heredoc，
之前把 python 塞进 run: | 里踩过 IndentationError，单独成文件后本地也能复用：

    python3 merge_bank.py            # 在仓库根目录跑
    python3 merge_bank.py --dir bank

规则：
  · 只收 bank/*.json 里带 items 的题库文件
  · 跳过 all.json 自己、跳过文件名含「复核」的文件（那是给老师看的待定清单）
  · 同一道题（同 id）只保留第一次出现的那份
"""
import argparse
import datetime
import glob
import json
import os
import sys

SKIP_WORDS = ("复核", "review", "all")


def load_items(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            doc = json.load(f)
    except Exception as e:
        print("  跳过 %s：%s" % (os.path.basename(path), e))
        return []
    if isinstance(doc, list):
        return doc
    items = doc.get("items") or doc.get("bank") or []
    return items if isinstance(items, list) else []


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default="bank", help="题库目录，默认 bank")
    ap.add_argument("--out", default="", help="输出路径，默认 <dir>/all.json")
    ap.add_argument("--pretty", action="store_true", help="缩进输出（体积大约多三成，仅用于人看）")
    a = ap.parse_args()

    out_path = a.out or os.path.join(a.dir, "all.json")
    files = []
    for f in sorted(glob.glob(os.path.join(a.dir, "*.json"))):
        name = os.path.basename(f).lower()
        if os.path.abspath(f) == os.path.abspath(out_path):
            continue
        if any(w in os.path.basename(f) or w in name for w in SKIP_WORDS):
            continue
        files.append(f)

    if not files:
        print("没有找到可合并的题库文件：%s/*.json" % a.dir)
        return 1

    seen, items, per = set(), [], {}
    bad_type = 0
    for f in files:
        n0 = len(items)
        for q in load_items(f):
            if not isinstance(q, dict) or not q.get("id"):
                bad_type += 1
                continue
            k = str(q["id"])
            if k in seen:
                continue
            seen.add(k)
            items.append(q)
        per[os.path.basename(f)] = len(items) - n0

    doc = {
        "format": "zx-trainer-bank-v1",
        "source": "题庄真题库 · 自动更新",
        "updatedAt": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
        "stats": {"usable": len(items), "files": len(files), "perFile": per,
                  "dropped": bad_type},
        "items": items,
    }
    os.makedirs(os.path.dirname(os.path.abspath(out_path)) or ".", exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        if a.pretty:
            json.dump(doc, f, ensure_ascii=False, indent=1)
        else:
            json.dump(doc, f, ensure_ascii=False, separators=(",", ":"))

    kb = os.path.getsize(out_path) / 1024.0
    print("合并完成 → %s，共 %d 道（来自 %d 个文件，%.0f KB）" % (out_path, len(items), len(files), kb))
    for k, v in per.items():
        print("  %-28s +%d" % (k, v))
    if bad_type:
        print("  · %d 条不是合法题目对象，已丢弃" % bad_type)
    return 0


if __name__ == "__main__":
    sys.exit(main())

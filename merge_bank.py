#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
把 bank/ 下的各分组题库合并成 bank/all.json（按 id + 内容去重，先到先得）。

为什么单独出一个文件：GitHub Actions 的 YAML 缩进块里没法干净地用 heredoc，
之前把 python 塞进 run: | 里踩过 IndentationError，单独成文件后本地也能复用：

    python3 merge_bank.py            # 在仓库根目录跑
    python3 merge_bank.py --dir bank

规则：
  · 只收 bank/*.json 里带 items 的题库文件
  · 跳过 all.json 自己、跳过文件名含「复核」的文件（那是给老师看的待定清单）
  · 同一道题（同 id）只保留第一次出现的那份
  · 同一道题换了 id（题庄重采、换年份重发）也拦掉：按内容指纹去重。
    指纹优先用题目自带的 question_fingerprint（题庄 content_hash），
    没有就用「题干 + 正确答案」的哈希，避免同一道题在 all.json 里出现两次、
    平板每次下载都要再跑一遍去重。
"""
import argparse
import datetime
import glob
import gzip
import hashlib
import json
import os
import re
import sys

# "meta" 一定要在里面：meta.json 也是 bank/*.json，不跳过的话它会当成题库文件
# 读进来（虽然没有 items，会被过滤成空），perFile 里白白多一行 0，看着像出错。
SKIP_WORDS = ("复核", "review", "all", "meta")


def content_key(q):
    """内容指纹：宁可放过，不可误杀。

    只用「题干 + 正确答案」两段，不含解析、出处、年份 ——
    这几项题庄会随整理规则变，带进去会让同一道题算出不同指纹。
    清洗掉空白与标点后再哈希，避免全角/半角、换行差异导致漏判。
    """
    fp = str(q.get("question_fingerprint") or "").strip()
    if fp:
        return "fp:" + fp
    stem = q.get("stem") or ""
    if not stem:
        p = q.get("passage") or ""
        m = re.search(r"【题干原文】\s*\n?(.*?)(?:\n\s*【|$)", p, re.S) if isinstance(p, str) else None
        stem = (m.group(1) if m else (p if isinstance(p, str) else ""))[:400]
    ans = ""
    opts = q.get("options") or []
    if isinstance(opts, list):
        for o in opts:
            if isinstance(o, dict) and o.get("is_correct"):
                ans = str(o.get("text") or o.get("key") or "")
                break
    if not ans:
        ans = str(q.get("reference_answer") or "")[:80]
    raw = re.sub(r"[\s\u3000·、，。；：！？,.;:!?\"'“”‘’()（）\[\]【】]+", "", str(stem) + "|" + ans)
    if len(raw) < 8:            # 题干都没取到就别乱合并
        return "id:" + str(q.get("id"))
    return "txt:" + hashlib.md5(raw.encode("utf-8")).hexdigest()[:16]


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
    dup_id, dup_txt, bad_type = 0, 0, 0
    for f in files:
        n0 = len(items)
        for q in load_items(f):
            if not isinstance(q, dict) or not q.get("id"):
                bad_type += 1
                continue
            k = str(q["id"])
            if k in seen:
                dup_id += 1
                continue
            ck = content_key(q)
            if ck in seen:
                dup_txt += 1
                continue
            seen.add(k)
            seen.add(ck)
            items.append(q)
        per[os.path.basename(f)] = len(items) - n0

    doc = {
        "format": "zx-trainer-bank-v1",
        "source": "题庄真题库 · 自动更新",
        "updatedAt": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
        "stats": {"usable": len(items), "files": len(files), "perFile": per,
                  "dropped": bad_type, "dupId": dup_id, "dupContent": dup_txt},
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

    # ---- 顺带产出两个给手机端省流量的文件 ----
    # 为什么必须做这一步：手机到 GitHub 本来就不稳，每次更新都下 1.38 MB，
    # 弱网下一断就白下。改成「先问 1 KB 的版本号，一样就不下」，成功率完全不同。
    #
    # 指纹只算 items，不算 updatedAt / stats：这两个字段每轮都会变，
    # 拿整个文件算哈希，结果是「一道新题都没有，手机也照样重下 148 KB」。
    # 排序 + 紧凑分隔符，保证同样一批题在任何机器上算出同一个值。
    key_src = json.dumps(items, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    sha = hashlib.sha256(key_src.encode("utf-8")).hexdigest()[:12]

    raw = open(out_path, "rb").read()
    gz_path = out_path + ".gz"
    # mtime=0：不然每次生成的 gz 字节都不同，白白让 CDN 缓存失效
    with open(gz_path, "wb") as fg:
        with gzip.GzipFile(filename="", mode="wb", fileobj=fg, compresslevel=9, mtime=0) as gz:
            gz.write(raw)

    meta = {
        "format": doc["format"],
        "sha": sha,
        "bytes": len(raw),
        "gz": os.path.getsize(gz_path),
        "items": len(items),
        "at": doc["updatedAt"],
    }
    meta_path = os.path.join(os.path.dirname(os.path.abspath(out_path)) or ".", "meta.json")
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, separators=(",", ":"))
    print("  版本 %s · all.json.gz %.0f KB · meta.json 已写完" % (sha, meta["gz"] / 1024.0))
    for k, v in per.items():
        print("  %-28s +%d" % (k, v))
    if bad_type:
        print("  · %d 条不是合法题目对象，已丢弃" % bad_type)
    if dup_id or dup_txt:
        print("  · 去重：同 id %d 条、同内容换 id %d 条" % (dup_id, dup_txt))
    return 0


if __name__ == "__main__":
    sys.exit(main())

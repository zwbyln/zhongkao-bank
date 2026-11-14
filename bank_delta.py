#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""算「本轮采集实际新增了多少道」。

为什么不用 stats.added：
    采集脚本是 `--append` 模式（新题并进旧文件）。文件里的 `stats.added` 记的是
    「那一次写入时新增几道」，追加之后它仍然是上一次的值，不是本轮的。
    拿它统计会出现「九组全部因额度 429 失败，却报新增 110 道」——任务照样打绿勾。

这里的判定很朴素：把每个分组文件当前的 items 条数，和 git HEAD 里的比。
多出来的才算本轮新增。不碰网络、不读 Key、不需要任何参数。

用法：
    python3 bank_delta.py          # 打印一个整数，供 shell 里 NEW=$(...) 使用
    python3 bank_delta.py --detail # 打印每组的明细，人工排查用
"""

import json
import os
import subprocess
import sys

# 工作流里 pick 出来的九个文件。顺序无关，只是为了和 yml 里对得上。
GROUPS = [
    "bank/zk-yuwen-8.json",
    "bank/zk-yuwen-9.json",
    "bank/zk-lishi-8.json",
    "bank/zk-lishi-9.json",
    "bank/tb-yuwen-7.json",
    "bank/tb-lishi-7.json",
    "bank/zk-yingyu-8.json",
    "bank/zk-yingyu-9.json",
    "bank/tb-yingyu-7.json",
]


def count_worktree(path):
    """当前工作区文件里的题目条数。文件不存在按 0 算。"""
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return len(json.load(f).get("items") or [])
    except Exception:
        return None


def count_head(path):
    """git HEAD 里同一个文件的题目条数。新文件/读不到都按 0 算。"""
    try:
        r = subprocess.run(
            ["git", "show", "HEAD:%s" % path],
            capture_output=True, text=True, timeout=30,
        )
        if r.returncode != 0 or not r.stdout.strip():
            return 0
        return len(json.loads(r.stdout).get("items") or [])
    except Exception:
        return 0


def main():
    detail = "--detail" in sys.argv
    total = 0
    rows = []
    # 注意：这里每个变量都靠元组解包重新赋值，不要沿用循环外的同名变量。
    for path in GROUPS:
        if not os.path.exists(path):
            # 本轮没产出这个文件（整组失败），不算新增
            rows.append((path, "-", "缺", 0))
            continue
        before = count_head(path)
        now = count_worktree(path)
        if now is None:
            rows.append((path, before, "坏", 0))
            continue
        # 只算增长。文件变小说明采集脚本做了清洗，不该记成负增长。
        delta = max(0, now - before)
        total += delta
        rows.append((path, before, now, delta))

    if detail:
        print("%-26s %8s %8s %6s" % ("分组文件", "HEAD", "现在", "新增"))
        for path, before, now, delta in rows:
            print("%-26s %8s %8s %6s" % (path, before, now, delta))
        print("%-26s %8s %8s %6s" % ("合计", "", "", total))
    else:
        # 只输出数字，shell 里直接赋值
        print(total)


if __name__ == "__main__":
    main()

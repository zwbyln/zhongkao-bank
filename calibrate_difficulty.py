#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""calibrate_difficulty.py —— 2.15 校正难度标注（上一轮 P1-10）

上一轮实测到的两处异常：
  · 历史八年级平均难度 1.24，低于七年级 3.30、九年级 2.88——八年级拿到最"水"的题；
  · 英语七八九三档平均难度 3.45 / 3.36 / 3.41，几乎没有梯度，
    相当于"按年级自动出题"在英语上不起作用。

本脚本不重写人工标注的难度（那是原题的判断），只修两类明显失真：
  ① 全学科同分值一律 1：题庄采集时没带难度，统一落到 1，
     这批题占了八年级 60/79，把年级均值拽下去。
  ② 整学段没方差：用一个可解释的结构化打分重估，而不是随机数。

打分口径（可复核）：分值 + 题型基础难度 + 记忆类型 + 题干长度 + 选项数
  base = 1 + (总分-2)/4                     # 4 分题 → 1.5；12 分 → 3.5
  + 采分点模式 +0.8（主观题天然比选择题难）
  + memory_type: fact 0 / concept +0.5 / sequence +0.7 / source +1.0
  + 题干 > 80 字 +0.5；> 160 字 +1.0
  + 选项 > 4 个 +0.3
最后 clamp 到 1..5，取一位小数。

用法：
  python3 calibrate_difficulty.py --dir bank            # 就地修改各分组文件
  python3 calibrate_difficulty.py --dir bank --dry      # 只看统计
"""
import argparse
import glob
import json
import os
import statistics

MT = {"fact": 0.0, "concept": 0.5, "sequence": 0.7, "source": 1.0}


def score(q):
    total = float(q.get("total_score") or 2)
    base = 1.0 + (total - 2) / 4.0
    if q.get("mode") == "points":
        base += 0.8
    base += MT.get(q.get("memory_type") or "", 0.3)
    stem = str(q.get("stem") or "")
    if len(stem) > 160:
        base += 1.0
    elif len(stem) > 80:
        base += 0.5
    opts = q.get("options") or []
    if isinstance(opts, list) and len(opts) > 4:
        base += 0.3
    return max(1.0, min(5.0, round(base, 1)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default="bank")
    ap.add_argument("--dry", action="store_true")
    a = ap.parse_args()
    files = [f for f in glob.glob(os.path.join(a.dir, "*.json"))
             if not any(k in os.path.basename(f) for k in ("all", "meta"))]
    changed = 0
    for f in files:
        doc = json.load(open(f, encoding="utf-8"))
        items = doc.get("items") if isinstance(doc, dict) else doc
        if not items:
            continue
        # 按「学科 + 年级」分档看：整档同一值 / 几乎没有方差 → 整档重估。
        # 上一版按学科分档，八年级恰好有 1~2 分的少量差异，pstdev 刚过 0.25，
        # 于是 60/75 道标成 1 分的题被放过去了——均值仍被拽到 1.37。
        by = {}
        for x in items:
            by.setdefault((x.get("subject"), x.get("grade")), []).append(x)
        for sub, arr in by.items():
            vals = [x.get("difficulty") or 1 for x in arr]
            flat = len(set(vals)) <= 1 or statistics.pstdev(vals) < 0.25
            for x in arr:
                # 显式覆盖：同一学科同一年级里 60% 以上都是 1 分，也按「整档失真」处理。
                # （八年级历史 60/75 标 1 分，靠 pstdev 判不出来）
                ones = sum(1 for y in arr if (y.get("difficulty") or 1) <= 1)
                flat = flat or (len(arr) >= 10 and ones / len(arr) >= 0.6)
                if flat:
                    nd = score(x)
                else:
                    # 只有明显失真的（1 分却配 4 分以上大题）才重估
                    old = x.get("difficulty") or 1
                    nd = score(x)
                    if old <= 1 and nd >= 3.0:
                        pass
                    else:
                        continue
                if x.get("difficulty") != nd:
                    x["difficulty"] = nd
                    x["difficultyWhy"] = "2.15 结构重估（原标注无梯度或明显偏低）"
                    changed += 1
        if not a.dry:
            json.dump(doc, open(f, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print(os.path.basename(f), "处理", len(items), "道")
    print("改动难度标注", changed, "处")
    if a.dry:
        return
    # 复核
    alldoc = json.load(open(os.path.join(a.dir, "all.json"), encoding="utf-8")) if os.path.exists(
        os.path.join(a.dir, "all.json")) else None
    if alldoc:
        g = {}
        for x in alldoc["items"]:
            g.setdefault((x.get("subject"), x.get("grade")), []).append(x.get("difficulty") or 1)
        for k in sorted(g, key=lambda k: (str(k[0]), str(k[1]))):
            print(k, len(g[k]), round(statistics.mean(g[k]), 2))


if __name__ == "__main__":
    main()

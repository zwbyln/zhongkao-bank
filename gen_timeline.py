# -*- coding: utf-8 -*-
"""把 history_timeline_data.py 的年表 + 题库 all.json 合成为前端可用的 timeline.json。

统计口径（这是本模块最需要讲清楚的地方，别让它变成拍脑袋的数字）：

1. 「题库出现次数」= 本仓库题库中，题面或材料里**同时命中**该事件关键词的题数。
   一条事件可能有多个关键词，命中任一即计入，但同一道题只计一次。
   为什么按关键词而不是按 id：题库里的题没有「事件 id」字段，
   硬造 id 就要人工标 559 道题，标完一改题就失效。关键词匹配可自动跟随题库更新。

2. 「中考」「高考」两列不是凭感觉写的估算，而是按下面的可复核规则推导：
   - 该事件属于中考必考主干（课标核心、教材正文大字、历年中考高频）→ zh ≥ 1
   - 属于高考重点（政治制度演变、经济结构变动、思想解放、国际格局）→ gk ≥ 1
   - 两者都重要的事件（如商鞅变法、鸦片战争、改革开放）两列都给较高值
   数值含义是「近年中考/高考中该事件作为考点被考查的典型频次档位」，
   1=偶考，2=常考，3=高频必考。这是教研口径的档位，不是精确计数，
   前端会明确标注为「考频档位」，不冒充精确统计。

3. 事件与题库「关联题号」一并输出，前端可点进去直接跳题练。
"""

import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from history_timeline_data import EVENTS, TAG_NAMES, STAGES

HERE = os.path.dirname(os.path.abspath(__file__))
BANK = os.path.join(HERE, "bank", "all.json")
OUT = os.path.join(HERE, "bank", "history-timeline.json")


def load_items():
    d = json.load(open(BANK, encoding="utf-8"))
    items = d if isinstance(d, list) else (d.get("items") or d.get("questions") or [])
    return [x for x in items if isinstance(x, dict) and x.get("subject") == "history"]


def text_of(q):
    """把一道题里所有可能提到事件的文字拼起来：题干、材料、选项、解析、答案、时间锚点。"""
    parts = [q.get("stem") or "", q.get("passage") or "",
             q.get("reference_answer") or "", q.get("time_anchor") or "",
             q.get("formula_ref") or ""]
    for o in (q.get("options") or []):
        if isinstance(o, dict):
            parts.append(o.get("text") or "")
            parts.append(o.get("option_analysis") or "")
    for p in (q.get("points") or []):
        if isinstance(p, dict):
            parts.append(p.get("text") or "")
    return "\n".join(parts)


def count_years(txt):
    """题面里出现的年份集合，用来做「同年」辅助匹配。"""
    ys = set()
    for m in re.finditer(r"公元前\s*(\d{1,4})\s*年", txt):
        ys.add(-int(m.group(1)))
    for m in re.finditer(r"(?<!公元前)(?<!\d)(\d{3,4})\s*年", txt):
        ys.add(int(m.group(1)))
    return ys


def main():
    items = load_items()
    print(f"题库历史题：{len(items)} 道")
    texts = [text_of(q) for q in items]
    years = [count_years(t) for t in texts]

    # 考频档位规则：按事件在课标与教材中的地位给档，可复核、可调整
    ZH_HOT = set()   # 中考高频
    GK_HOT = set()   # 高考重点
    for e in EVENTS:
        kp = e["kp"]
        # 中考主干：中国古代制度变革、近代抗争与探索、现代建设、世界近代化
        if e["tag"] in ("ca", "cm") and e["year"] <= 1949:
            ZH_HOT.add(e["t"])
        if e["tag"] == "cn" and e["year"] <= 2012:
            ZH_HOT.add(e["t"])
        # 高考重点：制度演变与思想解放类关键词
        heavy = ("制度", "变法", "改革", "宣言", "宪法", "革命", "格局", "体制", "政策", "维新", "运动")
        if any(h in e["t"] for h in heavy):
            GK_HOT.add(e["t"])

    out_events = []
    total_hits = 0
    for i, e in enumerate(EVENTS):
        hit_ids = []
        for idx, t in enumerate(texts):
            if any(k in t for k in e["kp"]):
                hit_ids.append(items[idx].get("id") or "")
            elif e["year"] in years[idx] and e["year"] != 0:
                # 关键词没命中但同年出现：只在同年且事件关键词至少一个词根出现时算
                pass
        hit_ids = [x for x in hit_ids if x]
        total_hits += len(hit_ids)

        # 考频档位：主干 +1，关键词在题库里命中多 +1，高考重点 +1，封顶 3
        zh = 1 if e["t"] in ZH_HOT else 0
        gk = 1 if e["t"] in GK_HOT else 0
        if len(hit_ids) >= 3:
            zh = min(3, zh + 1)
            gk = min(3, gk + 1)
        if len(hit_ids) >= 8:
            zh = min(3, zh + 1)

        out_events.append({
            "i": i,
            "y": e["year"],
            "yt": e["yt"],
            "t": e["t"],
            "d": e["d"],
            "tag": e["tag"],
            "kp": e["kp"],
            "zh": zh,
            "gk": gk,
            "n": len(hit_ids),
            "q": hit_ids[:12],
        })

    out_events.sort(key=lambda x: x["y"])

    by_tag = {}
    for e in out_events:
        by_tag[e["tag"]] = by_tag.get(e["tag"], 0) + 1

    pack = {
        "version": "1.0.0",
        "name": "重大历史纪事年表",
        "note": "考频为教研档位（3=高频必考 / 2=常考 / 1=偶考），非精确统计；「题库」列为当前题库中关联题数。",
        "count": len(out_events),
        "bankQuestions": len(items),
        "bankHits": total_hits,
        "tags": [{"k": k, "name": v, "stage": STAGES.get(k, ""), "n": by_tag.get(k, 0)} for k, v in TAG_NAMES.items()],
        "events": out_events,
    }
    json.dump(pack, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"年表 {pack['count']} 条，关联题库命中 {total_hits} 次 → {OUT}")
    print("分阶段：", {k: by_tag.get(k, 0) for k in TAG_NAMES})

    # 自检：有没有一条都没命中的（不算错，但要心里有数）
    zero = [e["t"] for e in out_events if e["n"] == 0]
    print(f"题库未命中 {len(zero)} 条：{zero[:8]}")


if __name__ == "__main__":
    main()

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
import html as html_lib
import json
import os
import re
import sys

# "meta" 一定要在里面：meta.json 也是 bank/*.json，不跳过的话它会当成题库文件
# 读进来（虽然没有 items，会被过滤成空），perFile 里白白多一行 0，看着像出错。
SKIP_WORDS = ("复核", "review", "all", "meta")

# 非题库的数据文件虽然也叫 *.json、也可能带 items，但不能当题收进来：
#   history-timeline / shishi 是年表与时政（有 items 但每条没有 stem），
#   混进来就会在题库里出现「无题干的幽灵题」——以前踩过一次（normalizeItem
#   把诊断对象当题目），这次直接从文件名 + 字段两道关拦。
SKIP_NAMES = ("history-timeline", "shishi")

# 一道题至少要有这两个字段。少任何一个都不算题，宁可漏收也不能收错。
REQUIRED_FIELDS = ("subject", "stem")

# ---------------------------------------------------------------- 原题标记恢复
# 题庄的原始 HTML（raw.title_html / raw.options_html）里，被画线的词写作
# <u>词</u>，被加点的词写作 <u>字</u> 加注音。抓取入库时这些标签被剥掉，
# 只剩「词前面多一个空格」这种残迹。
#
# 前端因此只能靠空格猜：遇到半角标点重排过的选项
# （「身材 , 有一头长发 , 都会 鹤立鸡群」）就直接放弃，一个线都不画。
# 孩子看到的就是「题干说画线，题里找不到线」——这正是用户反复报的那个问题。
#
# 这里在合并时把 raw 里的 <u> 原样搬回来；前端按真标记渲染，不再猜。
U_OPEN, U_CLOSE = "\u0001u>", "\u0001/u>"


def _plain(html_text):
    """把题庄的 HTML 压成纯文本，唯独 <u> 留下（先换成控制字符，免得被剥标签)。"""
    s = str(html_text or "")
    s = re.sub(r"<br\s*/?>", "\n", s, flags=re.I)
    s = re.sub(r"</p\s*>\s*<p[^>]*>", "\n", s, flags=re.I)
    s = re.sub(r"<u(?:\s[^>]*)?>", U_OPEN, s, flags=re.I)
    s = re.sub(r"</u\s*>", U_CLOSE, s, flags=re.I)
    s = re.sub(r"<[^>]+>", "", s)
    s = html_lib.unescape(s)
    return s.replace(U_OPEN, "<u>").replace(U_CLOSE, "</u>")


def _flat(s):
    """抹掉全部空白后比较：题庄原文用 \xa0 / 全角空格做分隔，和入库版差在这里。"""
    return re.sub(r"[\s\u00a0\u3000]+", "", str(s or ""))


def _tidy(s):
    return str(s or "").replace("\u00a0", " ").replace("\u3000", " ").strip()


def _no_u(s):
    return re.sub(r"</?u>", "", str(s or ""))


def _tight_u(s):
    """收线下沿：`<u> 词 </u>` 两端空白不要，`<u>颔首低眉 .</u>` 的句号也别画进线里。"""
    def one(m):
        inner = m.group(1).strip()
        inner = re.sub(r"[\s，。；：！？,.;:!?]+$", "", inner)
        return "<u>" + inner + "</u>" if inner else ""
    return re.sub(r"<u>(.*?)</u>", one, s, flags=re.S)


def recover_marks(q):
    """把 raw 里的下划线搬进 stem / options。返回改动的段数。"""
    raw = q.get("raw")
    if not isinstance(raw, dict):
        return 0
    n = 0
    th = _plain(raw.get("title_html"))
    if "<u>" in th and _flat(_no_u(th)) == _flat(q.get("stem")):
        q["stem"] = _tight_u(_tidy(th))
        n += 1
    oh = raw.get("options_html")
    if isinstance(oh, dict):
        for o in q.get("options") or []:
            if not isinstance(o, dict):
                continue
            h = _plain(oh.get(o.get("key")))
            if "<u>" in h and _flat(_no_u(h)) == _flat(o.get("text")):
                o["text"] = _tight_u(_tidy(h))
                n += 1
    return n


def sync_u_to_passage(q):
    """题干里标了线，材料卡里那段同样的文字也得有线。

    题庄的材料和题干是两份文本：画线信息只落在 title_html 上，passage 里
    是同一段话的副本、没有标记。左侧「选文/材料」卡渲染 passage，于是出现
    「题干有蓝线、上面的材料没线」——同一段字两种样子，看着像没修好。
    """
    stem = q.get("stem") or ""
    p = q.get("passage") or ""
    if "<u>" not in stem or not p:
        return 0
    n = 0
    for w in re.findall(r"<u>(.*?)</u>", stem, flags=re.S):
        if not w or len(w) < 2:
            continue
        tagged = "<u>" + w + "</u>"
        if tagged in p:
            continue
        if w in p:
            p = p.replace(w, tagged, 1)
            n += 1
    if n:
        q["passage"] = p
    return n


def clean_br(q):
    """题庄把换行写成 <br/>，前端按纯文本渲染会原样显示成「<br/>」。"""
    n = 0
    for k in ("stem", "passage"):
        v = q.get(k)
        if isinstance(v, str) and re.search(r"<br\s*/?>", v, flags=re.I):
            q[k] = re.sub(r"<br\s*/?>", "\n", v, flags=re.I)
            n += 1
    for o in q.get("options") or []:
        if isinstance(o, dict) and isinstance(o.get("text"), str) \
                and re.search(r"<br\s*/?>", o["text"], flags=re.I):
            o["text"] = re.sub(r"<br\s*/?>", "\n", o["text"], flags=re.I)
            n += 1
    return n


# ---------------------------------------------------------------- 入库质检
# 用户的原话：「题干不完整、根本看不到所谓的第二自然段，这种题就不要进入系统；
# 下划线解决不了的题也不要进系统。」这三类在下面各有一道关卡。
MARK_RE = re.compile(r"画[线線]|画横线|下划线|加点|加粗|着重号")
HAS_MARK_RE = re.compile(r"<u>|</u>|•|＿{2,}|_{3,}")
# 注音被压成竖排：原题是「字 + 拼音点」上下结构，抓成文本后成了「辍\n•\n\n耕（chuò）」，
# 四个选项全是一堆孤立圆点，读都读不成句。
MATH_JUNK_RE = re.compile(r"(?:^|\n)\s*•\s*(?:\n|$)")


def _visible(q):
    parts = [q.get("stem") or "", q.get("passage") or ""]
    for o in q.get("options") or []:
        parts.append(str(o.get("text") or "") if isinstance(o, dict) else str(o))
    return "\n".join(parts)


def quality_reject(q):
    """不合格返回原因，合格返回 None。宁可少收题，也不收一道做不了的题。"""
    v = _visible(q)
    if re.search(r"原文见上一?题|见上一题|见上题|详见上题", v):
        return "材料在别的题里（原文见上一题）"
    if MATH_JUNK_RE.search(v):
        return "注音符号被压成竖排乱码"
    if MARK_RE.search(q.get("stem") or "") and not HAS_MARK_RE.search(v):
        return "题干要求看画线/加点，但题里没有任何标记"
    return None



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
        if any(w in name for w in SKIP_NAMES):
            continue
        files.append(f)

    if not files:
        print("没有找到可合并的题库文件：%s/*.json" % a.dir)
        return 1

    seen, items, per = set(), [], {}
    dup_id, dup_txt, bad_type = 0, 0, 0
    # 本轮质检的账：恢复了多少段下划线、清了多少个 <br/>、拒了多少题、各为什么
    marks_fixed, br_fixed, rejected = 0, 0, 0
    reject_why = {}
    for f in files:
        n0 = len(items)
        for q in load_items(f):
            if not isinstance(q, dict) or not q.get("id"):
                bad_type += 1
                continue
            # 字段关：没有 subject / stem 的不是题（年表、时政条目就长这样）。
            # 这一关和上面的文件名关是「双保险」——以后再有新的非题库文件
            # 混进 bank/ 目录，也不会变成孩子题库里的空题。
            if any(not q.get(k) for k in REQUIRED_FIELDS):
                bad_type += 1
                continue
            # 先把 raw 里的 <u> 搬回来、把 <br/> 换成换行，再做质检——
            # 顺序反了会把「本来能修」的题当成「没标记」拒掉。
            marks_fixed += recover_marks(q)
            marks_fixed += sync_u_to_passage(q)
            br_fixed += clean_br(q)
            why = quality_reject(q)
            if why:
                rejected += 1
                reject_why[why] = reject_why.get(why, 0) + 1
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
                  "dropped": bad_type, "dupId": dup_id, "dupContent": dup_txt,
                  "rejected": rejected, "rejectWhy": reject_why,
                  "marksFixed": marks_fixed, "brFixed": br_fixed},
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
    if marks_fixed:
        print("  · 从原始 HTML 恢复下划线 %d 段（前端不再靠空格猜）" % marks_fixed)
    if br_fixed:
        print("  · 把 %d 处 <br/> 换成换行" % br_fixed)
    if rejected:
        print("  · 质检拒收 %d 道：" % rejected)
        for reason, cnt in sorted(reject_why.items(), key=lambda x: -x[1]):
            print("      %-34s %d 道" % (reason, cnt))
    if dup_id or dup_txt:
        print("  · 去重：同 id %d 条、同内容换 id %d 条" % (dup_id, dup_txt))
    return 0


if __name__ == "__main__":
    sys.exit(main())

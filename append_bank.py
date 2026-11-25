#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把新抓的题追加进 bank/all.json，并同步 meta.json / all.json.gz。

为什么不重跑 merge_bank.py 全量合并：
  all.json 是「已经过质检」的产物，bank/ 下还躺着几份更早的原始分组文件。
  全量重合并等于让所有题再被质检一次，规则哪怕微调过一点，也会把上次
  保留的题重新判掉——题库数量莫名变少，排查起来极难。这里只对新题把关，
  老题一个字节都不动。

用法：
    python3 append_bank.py /tmp/fill_九年级.json /tmp/fill_七年级.json ...
    python3 append_bank.py --bank bank /tmp/fill_九年级.json      # CI 里指定题库目录

一个刻意的设计：本轮一道新题都没有（额度用完、全是重复）时，直接退出 2，
**不碰 all.json**。否则每天夜里 CI 都会因为 updatedAt 变化而提交一次，
仓库里堆满「题库没变但时间戳变了」的空提交，meta.at 也跟着变，
客户端就会误以为有新版本、重下 1.38 MB。
"""
import argparse
import datetime
import gzip
import hashlib
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from merge_bank import clean_br, content_key, quality_reject, recover_marks, sync_u_to_passage  # noqa: E402


def main(paths, bank_dir):
    ALL = os.path.join(bank_dir, 'all.json')
    META = os.path.join(bank_dir, 'meta.json')
    GZ = os.path.join(bank_dir, 'all.json.gz')
    doc = json.load(open(ALL, encoding='utf-8'))
    items = doc['items']
    seen_id = {str(q['id']) for q in items}
    seen_ck = {content_key(q) for q in items}
    before = len(items)

    added, dup_id, dup_ck, rejected = 0, 0, 0, 0
    why = {}
    per_file = {}
    for p in paths:
        d = json.load(open(p, encoding='utf-8'))
        batch = d['items'] if isinstance(d, dict) else d
        n0 = added
        for q in batch:
            if not isinstance(q, dict) or not q.get('id'):
                continue
            if any(not q.get(k) for k in ('subject', 'stem')):
                continue
            recover_marks(q)
            sync_u_to_passage(q)
            clean_br(q)
            r = quality_reject(q)
            if r:
                rejected += 1
                why[r] = why.get(r, 0) + 1
                continue
            k = str(q['id'])
            if k in seen_id:
                dup_id += 1
                continue
            ck = content_key(q)
            if ck in seen_ck:
                dup_ck += 1
                continue
            seen_id.add(k)
            seen_ck.add(ck)
            items.append(q)
            added += 1
        per_file[os.path.basename(p)] = added - n0

    doc['items'] = items
    if added == 0:
        # 见文件头：没新题就别动文件，否则每天一次空提交 + meta.at 变化
        print(f"本轮没有新题（重复 id {dup_id} / 重复内容 {dup_ck} / 质检拒 {rejected}），题库保持原样 {before} 道")
        return 2

    doc['updatedAt'] = datetime.datetime.now().astimezone().isoformat(timespec='seconds')
    st = doc.get('stats') or {}
    st['usable'] = len(items)
    st['appendIn'] = {'added': added, 'dupId': dup_id, 'dupContent': dup_ck,
                      'rejected': rejected, 'rejectWhy': why, 'perFile': per_file}
    doc['stats'] = st

    raw = json.dumps(doc, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
    open(ALL, 'wb').write(raw)
    with gzip.open(GZ, 'wb', compresslevel=9) as f:
        f.write(raw)

    sha = hashlib.sha256(raw).hexdigest()[:12]
    meta = {
        'format': 'zx-trainer-bank-v1',
        'sha': sha,
        'bytes': len(raw),
        'gz': os.path.getsize(GZ),
        'items': len(items),
        'at': datetime.datetime.now().astimezone().isoformat(timespec='seconds'),
    }
    open(META, 'w', encoding='utf-8').write(json.dumps(meta, ensure_ascii=False, separators=(',', ':')))

    print(f"原始 {before} 道 → 现在 {len(items)} 道（新增 {added}）")
    print(f"  跳过：重复 id {dup_id} / 重复内容 {dup_ck} / 质检拒 {rejected}")
    if why:
        for k, v in why.items():
            print(f"    · {v} 道：{k}")
    print(f"  all.json {len(raw)} B / gz {meta['gz']} B / sha {sha}")
    print(f"  meta.json：{len(items)} 道 @ {meta['at']}")
    return 0


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description="把新抓的题追加进 all.json（不改动老题）")
    ap.add_argument('files', nargs='+', help='新抓的题库 JSON')
    ap.add_argument('--bank', default=os.path.join(os.path.dirname(os.path.abspath(__file__)), 'bank'),
                    help='题库目录（默认与本脚本同级的 bank/）')
    a = ap.parse_args()
    sys.exit(main(a.files, a.bank))

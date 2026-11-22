#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把主页里内嵌的 window.BANK 与合并后的题库对齐。

为什么要单独一步：内嵌那 88 道是「完全没网也能做题」的兜底，但它是一份
独立副本，之前就和 all.json 漂过——题库里已经剔掉的「原文见上一题」还留在
内嵌里，用户照样能看到。这里用 merge_bank.py 的同一套规则处理它：
恢复 <u> 下划线、清 <br/>、跑质检，保证两份数据口径一致。
"""
import collections
import io
import json
import sys

sys.path.insert(0, '/workspace/上传到GitHub')
from merge_bank import clean_br, quality_reject, recover_marks  # noqa: E402

HTML = '/workspace/专项训练.html'
ALL = '/workspace/上传到GitHub/bank/all.json'
META = '/workspace/上传到GitHub/bank/meta.json'


def main():
    s = io.open(HTML, encoding='utf-8').read()

    # ---- 元信息
    mi = s.index('window.BANK_META = ')
    start_m = mi + len('window.BANK_META = ')
    km = s.index('\n};', start_m)
    meta = json.loads(s[start_m:km] + '}')

    # ---- 内嵌题库
    bi = s.index('window.BANK = [')
    start_b = bi + len('window.BANK = ')
    kb = s.index('\n];', start_b)
    arr = json.loads(s[start_b:kb] + ']')

    kept, dropped = [], []
    marks = br = 0
    for q in arr:
        marks += recover_marks(q)
        br += clean_br(q)
        why = quality_reject(q)
        if why:
            dropped.append((q.get('id'), why))
            continue
        kept.append(q)

    def tally(field):
        return dict(collections.Counter(
            q.get(field) for q in kept if q.get(field)))

    meta['total'] = len(kept)
    meta['subjects'] = tally('subject')
    meta['grades'] = tally('grade')
    meta['genres'] = tally('genre')
    meta['memory_types'] = tally('memory_type')
    meta['modes'] = tally('mode')

    m = json.load(open(META, encoding='utf-8'))
    bank = json.load(open(ALL, encoding='utf-8'))
    meta['bankSha'] = m.get('sha', '')
    meta['bankItems'] = len(bank.get('items') or [])

    new_meta = json.dumps(meta, ensure_ascii=False, indent=2)
    new_arr = json.dumps(kept, ensure_ascii=False, indent=1)

    s = s[:mi] + 'window.BANK_META = ' + new_meta + s[km + 2:]
    bi = s.index('window.BANK = [')
    start_b = bi + len('window.BANK = ')
    kb = s.index('\n];', start_b)
    s = s[:start_b] + new_arr + s[kb + 2:]

    io.open(HTML, 'w', encoding='utf-8').write(s)

    print('内嵌题库 %d → %d 道（恢复下划线 %d 段，清 <br/> %d 处）' % (
        len(arr), len(kept), marks, br))
    for qid, why in dropped:
        print('  剔除 %s：%s' % (qid, why))
    print('bankSha → %s · bankItems → %d' % (meta['bankSha'], meta['bankItems']))


if __name__ == '__main__':
    main()

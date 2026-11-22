#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把 bank/shishi.json 内嵌进主页的 window.SHISHI_BUILTIN。

为什么要单独一个脚本：时政包有两份（磁盘上的 json 给镜像/本机路由用，
页面里的内嵌副本给「完全没网」时兜底）。两份不同步过一次——页面内嵌
还是 17 条，json 已经 23 条，于是「电脑端 23、手机端 17」看起来像同步坏了，
其实是随包的那份没跟着更新。以后每次 gen_shishi.py 之后都跑一下这个。
"""
import io
import json
import os

HTML = '/workspace/专项训练.html'
SRC = '/workspace/上传到GitHub/bank/shishi.json'


def main():
    pack = json.load(open(SRC, encoding='utf-8'))
    js = 'window.SHISHI_BUILTIN = ' + json.dumps(
        pack, ensure_ascii=False, separators=(',', ':')) + ';'
    s = io.open(HTML, encoding='utf-8').read()
    marker = 'window.SHISHI_BUILTIN = '
    i = s.index(marker)
    j = s.index('\n', i)
    s = s[:i] + js + s[j:]
    io.open(HTML, 'w', encoding='utf-8').write(s)
    print('内嵌 %d 条 · version %s · %d 字节' % (
        len(pack.get('items', [])), pack.get('version'), len(js)))


if __name__ == '__main__':
    main()

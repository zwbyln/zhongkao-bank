#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成内容层 OTA 的远端清单：把当前主页复制到 ota/，算出 sha256 和大小。

发布纪律：内容每次改动都要把 build 加 1，且 build 与 APK 的 versionCode 对齐。
App 端只有「远端 build > 本地 build」才下载，忘了加号用户就收不到更新。
"""
import hashlib
import json
import os
import shutil
from datetime import datetime

ROOT = '/workspace/上传到GitHub'
SRC = '/workspace/专项训练.html'
OTA = os.path.join(ROOT, 'ota')
HTML = os.path.join(OTA, 'train.html')
MANIFEST = os.path.join(OTA, 'manifest.json')

VERSION = '2.28'
BUILD = 39  # 与 APK versionCode 一致
NOTE = ('补齐「动名词作宾语 / 状语从句 / 形容词与副词 / 一般过去时」四个最薄的口诀考点：'
        '内置题库里这四个原来只有 0 / 1 / 1 / 1 道四选一题（动名词作宾语一道都没有），'
        '口诀写得再对也弹不出来。现按考点自编 17 道，每个补到 5 道。'
        '另修题库镜像：jsDelivr 的 @main 缓存卡在旧版本时，改为用不可变版本标签兜底。')


def main():
    os.makedirs(OTA, exist_ok=True)
    shutil.copyfile(SRC, HTML)
    # 章节包也进 OTA：AssetPages.bookChapters() 走 OtaClient.open，
    # 覆盖文件落在 files/ota/bank_book-chapters.json，无网时自动回退 assets。
    chapters_src = os.path.join(ROOT, 'bank', 'book-chapters.json')
    chapters_dst = os.path.join(OTA, 'bank', 'book-chapters.json')
    os.makedirs(os.path.dirname(chapters_dst), exist_ok=True)
    shutil.copyfile(chapters_src, chapters_dst)
    # 时政包同样进 OTA：时政更新频率远高于 APK，必须能热更，
    # 否则每加一条新闻都要重新发版，等于把这个模块做死。
    shishi_src = os.path.join(ROOT, 'bank', 'shishi.json')
    shishi_dst = os.path.join(OTA, 'bank', 'shishi.json')
    shutil.copyfile(shishi_src, shishi_dst)
    files = []
    for rel, path in [('train.html', HTML),
                      ('bank/book-chapters.json', chapters_dst),
                      ('bank/shishi.json', shishi_dst)]:
        raw = open(path, 'rb').read()
        files.append({
            'path': rel,
            'sha256': hashlib.sha256(raw).hexdigest(),
            'size': len(raw),
        })
        print(rel, len(raw), '字节 sha256', files[-1]['sha256'][:16])
    manifest = {
        'version': VERSION,
        'build': BUILD,
        'time': datetime.now().strftime('%Y-%m-%d %H:%M'),
        'note': NOTE,
        'files': files,
    }
    with open(MANIFEST, 'w', encoding='utf-8') as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    print('清单', MANIFEST)


if __name__ == '__main__':
    main()

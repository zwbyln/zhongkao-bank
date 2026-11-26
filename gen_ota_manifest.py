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

VERSION = '2.30'
BUILD = 44  # 与 APK versionCode 一致
NOTE = ('词卡新增「联想记忆」：能拆的词给两截熟词（air + port，各带中文），'
        '具体名词配一个 emoji 当图像锚点，其余的词给三个问题让孩子自己编；'
        '写下的那一句存在档案里，复习时先看到自己的句子，说明页可一键复制整本联想。'
        '素材只做「原材料」不做现成故事：翻了 GitHub 上 6.4k star 的 CC BY-SA 单词书，'
        '1662 条「记忆辅助」抽样大半是「把 climb 和 climber 联系起来就记住了」这种循环解释，'
        '搬进来只会占地方，还带传染性协议；CC0 图库实测只有 25 张。'
        '所以只借方法、不搬文本，拆分规则也硬：拆出来的两截必须都是这孩子词表里的真词。'
        '审核时又抓出两处会教错的：breakfast 被拆成「休息 + 快速的」，'
        'accountant 被讲成「账户 + 蚂蚁」，backward 成了「back + 病房」——'
        '词典义放到合成词里就偏了，这类给人工释义覆盖；词尾另标「表示人 / 表示朝…方向」。'
        '讲不通的 7 条（forbid、withdraw、fireworks 等）直接删掉。'
        '另外修了两处「看不见的错」：some- 类词（somebody = some + body）'
        '曾被注成「词尾，表示…的」，因为词尾表按字符串查，some 恰好也在里面——'
        '改成只认末段；「我的画面」保存时读的是全局当前词，孩子写好句子后'
        '若发生一次重绘，句子会拐到另一张词卡上，改成以输入框绑定的词为准。'
        '词表页同时多了「有联想」筛选（551 词）。')


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

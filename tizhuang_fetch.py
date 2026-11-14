#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
题庄真题库 → 「初中专项训练系统」题库适配器

作用：从题庄（tizhuang.qcscience.cc）拉取**真实考题**，转换为 index.html
「题库 → 导入」可直接读取的 JSON，让孩子在安卓平板上做选择题练习。

设计原则（对应题庄官方保真契约）：
  1. 题干、选项、答案、解析一律取自题庄原始字段，只做 HTML 标签清洗，
     不改写、不重排、不重算答案、不编造解析。
  2. 答案与解析明显冲突的题（例如标答 D、解析写「因此选B」）默认不入库，
     单独写进「复核」文件交给老师判断，脚本不擅自更正。
  3. 只取 question_type=选择题 + auto_gradable=true + has_images=false 的题，
     保证是四选一、可自动批改、不依赖图片。
  4. formula_ref / memory_type / content_scope / genre / trap_type 属于本系统的
     调度元数据，由脚本按关键词推断，属于教学标注而非原题内容，建议教师复核。
  5. 干扰项的 option_analysis 是系统占位提示语，不是伪造的原题解析；
     原题解析原文只放在正确项与 reference_answer 里。

用法：
  # 匿名试用（24 小时内 50 题，无需注册，自动缓存凭证）
  python3 tizhuang_fetch.py --subject 语文 --grade 七 --limit 15
  python3 tizhuang_fetch.py --subject 历史 --grade 九 --limit 15

  # 一次跑完 6 个组合（注意匿名额度只有 50 题）
  python3 tizhuang_fetch.py --all --limit 6 --outdir ./tizhuang_bank

  # 注册后用自己的 Key（每日 150 题起）。推荐把 Key 放进本地凭据文件，别写进聊天/脚本/URL：
  #   Linux/macOS: printf '你的Key' > ~/.tizhuang_license && chmod 600 ~/.tizhuang_license
  #   Windows:      setx QUESTION_SERVICE_LICENSE 你的Key
  # 读取优先级：--api-key > 环境变量 QUESTION_SERVICE_LICENSE > ~/.tizhuang_license
  python3 tizhuang_fetch.py --subject 历史 --grade 八年级 --limit 40
  python3 tizhuang_fetch.py --api-key 你的Key --subject 语文 --grade 九年级 --limit 40

  # 只看元数据（免费，不消耗额度）
  python3 tizhuang_fetch.py --meta

生成的 *_题库.json 用 index.html 的「题库 → 选择 .json 文件」导入即可。
生成的 *_复核.json 是被跳过的题及原因，供老师核对，不要直接导入。
"""

import argparse
import datetime
import hashlib
import html
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

BASE = os.environ.get("QUESTION_SERVICE_URL", "https://tizhuang.qcscience.cc/api").rstrip("/")
CACHE = os.path.expanduser("~/.tizhuang_trial.json")
LICENSE_FILE = os.path.expanduser("~/.tizhuang_license")


def read_local_license():
    """从本地 600 权限文件读取注册 Key；不回显、不写进任何输出文件。"""
    try:
        if os.path.isfile(LICENSE_FILE):
            return open(LICENSE_FILE, "r", encoding="utf-8").read().strip()
    except Exception:
        pass
    return ""

# ----------------------------- HTTP -----------------------------

def http(method, path, headers=None, body=None):
    data = None
    hdr = {"Accept": "application/json"}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        hdr["Content-Type"] = "application/json"
    hdr.update(headers or {})
    req = urllib.request.Request(BASE + path, data=data, headers=hdr, method=method)
    try:
        with urllib.request.urlopen(req, timeout=35) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "ignore")[:300]
        if e.code == 429:
            raise RuntimeError("题庄额度已用尽或触发限流：%s\n匿名试用为 24 小时 50 题；"
                               "注册仍免费、每日 150 题起：https://tizhuang.qcscience.cc/account?mode=register\n%s"
                               % (e.code, detail))
        if e.code in (401, 403):
            raise RuntimeError("认证失败（HTTP %s）。检查 ~/.tizhuang_license 或环境变量里的 Key "
                               "是否有效、是否含多余空格/换行：%s" % (e.code, detail))
        raise RuntimeError("题庄接口 HTTP %s：%s" % (e.code, detail))
    except urllib.error.URLError as e:
        raise RuntimeError("无法连接题庄接口：%s" % e.reason)


def get(path, headers):
    return http("GET", path, headers)


def trial_valid(exp):
    if not exp:
        return False
    try:
        e = datetime.datetime.fromisoformat(str(exp).replace("Z", "+00:00"))
        now = datetime.datetime.now().astimezone()
        if e.tzinfo is None:
            e = e.replace(tzinfo=now.tzinfo)
        return e > now
    except Exception:
        return True  # 解析不了就先复用，接口报 401 时再重建


def auth_headers(api_key):
    """返回 (headers, 取题路径前缀, 说明文字)"""
    if api_key:
        return {"X-API-Key": api_key}, "/v1/questions", "注册 Key（每日 150 题起）"
    cid, token, expires = load_trial()
    if not (token and trial_valid(expires)):
        saved_cid = cid
        cid, token, expires = create_trial(saved_cid)
    return {"X-Trial-Token": token}, "/v1/trial/questions", "匿名试用（24 小时 50 题）"


def load_trial():
    try:
        d = json.load(open(CACHE, "r", encoding="utf-8"))
        return d.get("client_id"), d.get("token"), d.get("expires_at")
    except Exception:
        return None, None, None


def create_trial(old_cid=None):
    # 官方要求：稳定复用同一个 client id，不得为绕过额度而轮换身份
    cid = old_cid or ("zx-trainer-" + hashlib.md5(
        (os.environ.get("USER", "user") + os.path.expanduser("~")).encode("utf-8")).hexdigest()[:20])
    d = http("POST", "/v1/trials", {"X-Anonymous-Client-ID": cid}, {})
    token, exp = d.get("trial_token"), d.get("expires_at")
    if not token:
        raise RuntimeError("题庄未返回试用令牌")
    os.makedirs(os.path.dirname(CACHE) or ".", exist_ok=True)
    with open(CACHE, "w", encoding="utf-8") as f:
        json.dump({"client_id": cid, "token": token, "expires_at": exp}, f, ensure_ascii=False)
    print("  · 已创建匿名试用凭证，缓存于 %s（额度 %s 题）" % (CACHE, d.get("question_limit")))
    return cid, token, exp


def resolve_meta(headers):
    """名称 → ID 精确解析，绝不靠猜。"""
    subjects = get("/v1/meta/subjects", headers)
    grades = get("/v1/meta/grades", headers)
    smap = {x["name"]: x["id"] for x in subjects}
    gmap = {x["name"]: x["id"] for x in grades}
    return smap, gmap


# ----------------------------- 清洗 / 读取 -----------------------------

def clean_html(s):
    """只去标签与实体转义，不改任何一个字的顺序与内容。"""
    if s is None:
        return ""
    if not isinstance(s, str):
        s = json.dumps(s, ensure_ascii=False)
    s = re.sub(r"(?i)<br\s*/?>", "\n", s)
    s = re.sub(r"(?i)</(?:p|div|li|tr|h[1-6]|ul|ol|table|blockquote)\s*>", "\n", s)
    s = re.sub(r"(?i)<[^>]+>", "", s)
    s = html.unescape(s)
    s = s.replace("\xa0", " ").replace("\u3000", " ").replace("\r", "\n").replace("\t", " ")
    lines = [re.sub(r" {2,}", " ", ln).strip() for ln in s.split("\n")]
    out, blank = [], False
    for ln in lines:
        if not ln:
            if blank or not out:
                continue
            blank = True
        else:
            blank = False
        out.append(ln)
    return "\n".join(out).strip()


ANSWER_PREFIX = re.compile(r"^\s*(?:【答案】|答案[：:]|正确答案[：:]?)\s*")

def read_answer(raw):
    """只读取题庄给出的标答字母；读不出就放弃，绝不推断答案。"""
    if not isinstance(raw, str):
        return None
    a = ANSWER_PREFIX.sub("", raw.strip())
    a = re.sub(r"\s+", "", a).strip("。.,，、；;：:）)]】")
    return a if re.fullmatch(r"[A-D]", a) else None


CONFLICT_PATTERNS = [
    r"故\s*选\s*([A-D])(?![A-Za-z])",
    r"因此\s*选\s*([A-D])(?![A-Za-z])",
    r"所以\s*选\s*([A-D])(?![A-Za-z])",
    r"正确答案\s*[是为：:]?\s*([A-D])(?![A-Za-z])",
    r"答案\s*[是为：:]\s*([A-D])(?![A-Za-z])",
    r"答案为\s*([A-D])(?![A-Za-z])",
    r"(?<!不)选\s*([A-D])(?![A-Za-z0-9])",
]

def detect_conflict(ans, analysis_text):
    """解析里出现明确答案线索却与标答不符 → 交老师复核，脚本不更正。"""
    hits = []
    for p in CONFLICT_PATTERNS:
        hits += re.findall(p, analysis_text)
    uniq = set(hits)
    if not uniq or ans in uniq:
        return None
    return "解析中的答案线索 %s 与题庄标答 %s 不一致" % ("/".join(sorted(uniq)), ans)


# ----------------------------- 教学元数据推断 -----------------------------

# 顺序有意义：先判现代史 → 近代史 → 世界史，都没命中才默认中国古代史。
# 题庄的 grade_id 与真实内容经常错位（九年级卷里大量元谋人/青铜器题），
# 所以内容范围只按题干与考点的史实关键词判断，绝不按 grade_id 猜。
SCOPE_WORDS = [
    ("中国现代史", ["1949", "1950", "1953", "1954", "1956", "1958", "1978", "新中国成立", "开国大典",
                "西藏和平解放", "土地改革", "抗美援朝", "一五计划", "一五", "三大改造", "人民代表大会",
                "人民公社", "大跃进", "文化大革命", "文革", "改革开放", "十一届三中全会", "家庭联产承包",
                "经济特区", "深圳", "国企改革", "香港回归", "澳门回归", "两弹一星", "万隆会议", "尼克松",
                "重返联合国", "恢复联合国", "市场经济体制", "社会主义建设", "雷锋", "焦裕禄", "王进喜",
                "邓稼先", "袁隆平", "籼型杂交水稻", "863计划", "科教兴国", "社会保障", "义务教育法"]),
    ("中国近代史", ["1840", "1839", "1851", "1860", "1894", "1895", "1898", "1900", "1901", "1911",
                "1912", "1915", "1919", "1921", "1926", "1927", "1931", "1934", "1935", "1936",
                "1937", "1945", "1946", "1947", "1948", "鸦片战争", "林则徐", "虎门销烟", "南京条约",
                "火烧圆明园", "太平天国", "洪秀全", "洋务运动", "洋务", "自强", "求富", "李鸿章",
                "左宗棠", "收复新疆", "甲午", "马关条约", "邓世昌", "戊戌", "百日维新", "康有为",
                "梁启超", "义和团", "八国联军", "辛丑条约", "辛亥革命", "同盟会", "孙中山", "武昌起义",
                "中华民国", "民国", "北洋", "袁世凯", "新文化运动", "陈独秀", "五四运动", "中共一大",
                "共产党成立", "国共合作", "北伐", "南昌起义", "秋收起义", "井冈山", "长征", "遵义会议",
                "九一八", "七七事变", "卢沟桥", "南京大屠杀", "抗日战争", "抗战", "台儿庄", "百团大战",
                "平型关", "中共七大", "重庆谈判", "蒋介石", "毛泽东", "双十协定", "内战", "解放战争",
                "挺进大别山", "三大战役", "辽沈", "淮海", "平津", "渡江战役", "张謇", "詹天佑",
                "侯德榜", "魏源", "严复", "京师大学堂", "废除科举", "剪辫", "近代民族工业"]),
    ("世界史", ["阿拉伯", "天方夜谭", "一千零一夜", "伊斯兰", "穆罕默德", "古罗马", "罗马帝国",
             "希腊", "雅典", "斯巴达", "亚历山大", "古埃及", "金字塔", "法老", "巴比伦", "汉谟拉比",
             "种姓", "婆罗门", "释迦牟尼", "基督教", "耶稣", "法兰克", "查理曼", "庄园", "西欧",
             "中世纪", "文艺复兴", "但丁", "神曲", "达芬奇", "莎士比亚", "新航路", "哥伦布",
             "麦哲伦", "达伽马", "迪亚士", "三角贸易", "殖民扩张", "英国资产阶级革命", "权利法案",
             "克伦威尔", "光荣革命", "华盛顿", "独立宣言", "美国独立", "1776", "法国大革命",
             "攻占巴士底狱", "人权宣言", "拿破仑", "滑铁卢", "工业革命", "蒸汽机", "瓦特", "珍妮机",
             "马克思", "恩格斯", "共产党宣言", "巴黎公社", "林肯", "南北战争", "解放黑人奴隶",
             "废除农奴制", "亚历山大二世", "明治维新", "大化改新", "彼得一世", "第一次世界大战",
             "萨拉热窝", "凡尔登", "十月革命", "列宁", "苏维埃", "新经济政策", "斯大林模式",
             "罗斯福新政", "经济大危机", "1929", "法西斯", "希特勒", "慕尼黑", "第二次世界大战",
             "二战", "诺曼底", "斯大林格勒", "珍珠港", "雅尔塔", "联合国", "冷战", "杜鲁门",
             "马歇尔", "北约", "华约", "苏联解体", "欧盟", "第三次科技革命", "经济全球化",
             "世界贸易组织", "古巴", "印度民族大起义", "章西女王", "玻利瓦尔", "拉美独立",
             "非洲独立", "巴拿马", "苏联"]),
]

GRADE_SCOPE = {"七": {"中国古代史"}, "八": {"中国近代史", "中国现代史"}, "九": {"世界史"}}

SEQ_WORDS = r"先后|顺序|排序|按时间|时间先后|依次|排列|时间轴|按先后|最早发生|发生在.*之前"
SOURCE_WORDS = r"材料|史料|据此|这则|上述|记载|出土|文物|碑文|文献|图表|下表|图片"
FACT_WORDS = r"(?:公元前|前)?\d{3,4}年|\d+世纪|\d+年代|哪一年|哪年|何时|公元"

CH_GENRE = [
    ("文言文", r"文言|实词|虚词|一词多义|通假|古今异义|词类活用|课内古文|翻译句子|《论语》|《世说新语》|《陋室铭》|《爱莲说》|《岳阳楼记》|《醉翁亭记》|《出师表》|《桃花源记》|《三峡》|《记承天寺夜游》"),
    ("说明文", r"说明对象|说明方法|说明顺序|列数字|举例子|作比较|打比方|下定义|说明文|准确性"),
    ("议论文", r"论点|论据|论证|议论文|中心论点|驳论|道理论证|举例论证"),
    ("散文", r"散文|抒情散文|形散神聚|托物言志|借景抒情"),
    ("非连续性文本", r"非连续|图表|材料一|材料二|统计图|表格|海报|说明书"),
    ("记叙文", r"记叙|人物描写|环境描写|插叙|伏笔|线索|标题含义|句子赏析|修辞手法|小说"),
]

FORMULA_CH = [
    (r"修辞|赏析|比喻|拟人|排比", "手法（修辞/描写/用词）→ 写出了……特点 → 表现了……情感"),
    (r"文言|实词|虚词|翻译", "留删换调补贯六字诀 + 语境推断/组词推断/课内迁移；先判实词四大类"),
    (r"概括|主要内容|情节", "何人 + 何事 + 何结果 +（情感主旨）"),
    (r"标题|题目", "表层义 + 深层义；线索/概括内容/设置悬念/揭示主旨/激发兴趣"),
    (r"插叙|环境描写|景物描写", "补充了……内容 + 突出了……主题（或烘托了人物……性格/情感）"),
    (r"说明", "说明对象 + 说明方法 + 说明顺序 + 语言准确性"),
    (r"论点|论证", "亮明论点 → 找论据 → 辨论证方法 → 回扣结论"),
]
FORMULA_CH_DEFAULT = "审设问方向 → 回原文定位依据 → 逐项核对选项（警惕绝对化、以偏概全、无中生有）"

FORMULA_HI = [
    (r"先后|顺序|排序|朝代更替", "首尾锚定 → 逐项插入 → 相邻校验；警惕相邻互换、首尾错置、跨朝代插入"),
    (r"原因|背景|为何|为什么|根本", "根本原因（经济基础/社会矛盾）→ 直接原因（导火索）→ 回材料验证"),
    (r"影响|意义|作用|评价", "对当时 → 对后世；政治/经济/思想分层，注意程度词是否绝对化"),
    (r"史料|材料|据此|可信|价值|实物|文献", "先判史料类型（实物/文献/口述/图像）→ 再判一手/二手 → 最后评估可信度"),
    (r"相同|不同|比较|异同", "先定比较维度（背景/内容/性质/影响）→ 逐维比对 → 排除张冠李戴"),
]
FORMULA_HI_DEFAULT = "先看时间/人物是否匹配，再看程度词是否绝对化，最后回材料找依据"

# ------------------------- 英语 -------------------------
# 结构类优先于时态：「被动语态 一般现在时」这类标注，真正要考的是结构。
# 与客户端 tizhuang.js 的 FORMULA_EN 保持一致，两边改规则要同步。
FORMULA_EN = [
    (r"情态动词.*被动|must be|should be|can be", "情态动词被动"),
    (r"被动语态|被动", "被动语态"),
    (r"动名词|v-ing", "动名词作主语"),
    (r"不定式|to do", "不定式表目的"),
    (r"非谓语|分词", "分词作定语"),
    (r"宾语从句", "宾语从句"),
    (r"定语从句|关系代词|关系副词", "定语从句"),
    (r"状语从句", "状语从句"),
    (r"主语从句", "主语从句"),
    (r"主谓一致", "主谓一致"),
    (r"感叹句", "感叹句"),
    (r"反意疑问|附加疑问", "反意疑问句"),
    (r"强调句", "强调句"),
    (r"倒装", "倒装句"),
    (r"补全对话|情景交际|交际用语|日常交际", "情景交际 · 邀请与建议"),
    (r"固定搭配|固定短语", "固定搭配"),
    (r"短语动词|动词短语", "短语动词"),
    (r"词义辨析|近义|词汇运用|单词拼写|词形", "近义词辨析"),
    (r"冠词|a/an", "冠词"),
    (r"代词", "代词"),
    (r"形容词|副词|比较级|最高级", "形容词与副词"),
    (r"介词", "介词"),
    (r"名词|数词|单复数", "名词与数"),
    (r"连词|并列句", "连词"),
    (r"现在完成", "现在完成时"),
    (r"过去完成", "过去完成时"),
    (r"过去进行", "过去进行时"),
    (r"现在进行", "现在进行时"),
    (r"一般将来|将来时", "一般将来时"),
    (r"一般过去|过去式", "一般过去时"),
    (r"一般现在|第三人称单数|三单", "一般现在时"),
    (r"句子成分|句子结构|简单句|句子理解|划线部分", "句子成分"),
]
FORMULA_EN_DEFAULT = "句子成分"

# 语法板块（与 formulas.js 的 FORMULA_GROUPS.english 一致）
EN_GROUP = {
    "一般现在时": "动词时态", "一般过去时": "动词时态", "一般将来时": "动词时态",
    "现在进行时": "动词时态", "过去进行时": "动词时态", "现在完成时": "动词时态",
    "过去完成时": "动词时态", "被动语态": "被动语态", "情态动词被动": "被动语态",
    "动名词作主语": "非谓语动词", "不定式表目的": "非谓语动词", "分词作定语": "非谓语动词",
    "宾语从句": "从句", "定语从句": "从句", "状语从句": "从句", "主语从句": "从句",
    "冠词": "词法", "代词": "词法", "形容词与副词": "词法", "介词": "词法",
    "名词与数": "词法", "连词": "词法", "主谓一致": "主谓一致",
    "感叹句": "句型与倒装", "反意疑问句": "句型与倒装", "强调句": "句型与倒装", "倒装句": "句型与倒装",
    "近义词辨析": "词汇辨析", "短语动词": "词汇辨析", "固定搭配": "词汇辨析",
    "情景交际 · 感谢与道歉": "情景交际", "情景交际 · 邀请与建议": "情景交际",
    "句子成分": "句子理解", "长难句拆分": "句子理解",
}
# 干扰项陷阱类型：让错题本能按「时态/语态/从句」归类，而不是全堆在「未分类」
EN_TRAP = {
    "动词时态": "时态误判", "被动语态": "语态误判", "非谓语动词": "非谓语误判",
    "从句": "关系词误判", "主谓一致": "词形误判", "词法": "词形误判",
    "句型与倒装": "语序错误", "词汇辨析": "近义词混淆", "情景交际": "交际用语误用",
    "句子理解": "句意理解偏差",
}


def infer_scope(text):
    for scope, words in SCOPE_WORDS:
        if any(w in text for w in words):
            return scope
    return "中国古代史"


def infer_memory_type(text):
    if re.search(SEQ_WORDS, text):
        return "sequence"
    if re.search(SOURCE_WORDS, text) and not re.search(r"选项|下列", text[:20]):
        return "source"
    if re.search(FACT_WORDS, text):
        return "fact"
    return "concept"


def infer_ch_genre(text, knowledges):
    blob = text + " " + (knowledges or "")
    for g, pat in CH_GENRE:
        if re.search(pat, blob):
            return g
    return "记叙文"


SUBJECT_OF = {"语文": "chinese", "历史": "history", "英语": "english"}
SUBJECT_LABEL = {"chinese": "语文", "history": "历史", "english": "英语"}


def formula_for(subject, text, memory_type):
    if subject == "english":
        for pat, f in FORMULA_EN:
            if re.search(pat, text):
                return f
        return FORMULA_EN_DEFAULT
    table = FORMULA_CH if subject == "chinese" else FORMULA_HI
    default = FORMULA_CH_DEFAULT if subject == "chinese" else FORMULA_HI_DEFAULT
    for pat, f in table:
        if re.search(pat, text):
            return f
    if subject == "history" and memory_type == "fact":
        return "史实记忆 = 时间锚点 + 前后事件夹逼（上承什么、下启什么）"
    return default


def group_of_en(point):
    return EN_GROUP.get(point, "句子理解")


def trap_of_en(point):
    return EN_TRAP.get(group_of_en(point), "句意理解偏差")


def infer_en_genre(text, point):
    if re.search(r"补全对话|情景交际|交际用语", text):
        return "情景交际"
    g = group_of_en(point)
    if g == "词汇辨析":
        return "词汇辨析"
    if g == "句子理解":
        return "句子理解"
    return "语法单选"


def time_anchor(text):
    m = re.search(r"(?:公元前|前)?\d{3,4}年|\d{1,2}世纪(?:初|末|中叶|前期|后期)?", text)
    return m.group(0) if m else None


def score_of(title):
    m = re.search(r"[（(]\s*(\d+)\s*分\s*[）)]", title) or re.search(r"(\d+)\s*分", title)
    return int(m.group(1)) if m else 2


# ----------------------------- 转换 -----------------------------

def split_inline_options(text):
    """题庄有一部分语文题（尤其文言文）把选项直接写在题干里，options 字段是空的，
    形如「A．…… B．…… C．…… D．……」。
    这里只把题干里**已经存在**的四段拆出来，不改字、不补字；拆不出四个就原样返回，
    交给上层按「非标准四选一」剔除。返回 ({'A':..,'B':..,'C':..,'D':..}, 去掉选项后的题干)。"""
    marks = [(m.group(1), m.start(1), m.end())
             for m in re.finditer(r"(?:^|\s)([A-D])\s*[．.、:：)）]\s*", text)]
    seq = [m[0] for m in marks]
    for i in range(len(marks) - 3):
        if seq[i:i + 4] == ["A", "B", "C", "D"]:
            picked = marks[i:i + 4]
            stem = re.sub(r"\[\s*\]", "", text[:picked[0][1]]).strip()
            if len(stem) < 4:
                return None, text
            out = {}
            for j, (k, s, e) in enumerate(picked):
                end = picked[j + 1][1] if j < 3 else len(text)
                v = text[e:end].strip(" \n\u3000;；。")
                if not v:
                    return None, text
                out[k] = v
            return out, stem
    return None, text


def convert(it, subject, grade, keep_out_of_scope=False, include_conflicts=False, with_raw=True):
    """返回 (题目 dict 或 None, 跳过原因 或 None)"""
    qid = it.get("id")
    title_html = it.get("title_html") or it.get("title") or ""
    analysis_html = it.get("analysis_html") or it.get("analysis") or ""
    if re.search(r"(?i)<img\b", title_html) or it.get("has_images"):
        return None, "含图片，平板离线打开会缺图"
    title = clean_html(title_html)
    analysis = clean_html(analysis_html)
    if not title or len(title) < 8:
        return None, "题干为空或过短"

    opts_raw = it.get("options") or {}
    if isinstance(opts_raw, dict) and set(opts_raw.keys()) == {"A", "B", "C", "D"}:
        opts_text = {k: clean_html(v) for k, v in opts_raw.items()}
        stem_text = title
    else:
        parsed, stem_text = split_inline_options(title)
        if not parsed:
            return None, "不是标准 A/B/C/D 四选一（选项数 %d）" % (
                len(opts_raw) if isinstance(opts_raw, dict) else 0)
        opts_text = parsed
    if any(not v for v in opts_text.values()):
        return None, "存在空选项"

    ans = read_answer(it.get("answer") or it.get("answer_html"))
    if not ans:
        return None, "标答不是明确的单个 A—D 字母，脚本不推断答案"

    conflict = detect_conflict(ans, analysis)
    if conflict and not include_conflicts:
        return None, conflict

    knowledges = str(it.get("knowledges") or "")
    source = str(it.get("source") or "题庄题库")
    blob = title + " " + knowledges + " " + analysis[:300]
    sub_label = SUBJECT_LABEL.get(subject, "语文")
    gpoint = None

    if subject == "english":
        # 英语不按内容范围筛（七/八/九 都是同一套语法体系，只是难度递进），
        # 也没有 memory_type；改成标注语法点 + 语法板块，供错题按板块聚合。
        scope, mem = None, None
        gpoint = formula_for("english", title + " " + knowledges, None)
        genre = infer_en_genre(title + " " + knowledges, gpoint)
    elif subject == "history":
        scope = infer_scope(blob)
        allowed = GRADE_SCOPE.get(grade, set())
        if scope not in allowed and not keep_out_of_scope:
            return None, "内容范围推断为「%s」，与 %s年级要求的 %s 不匹配（可用 --keep-out-of-scope 保留）" % (
                scope, grade, "/".join(sorted(allowed)))
        mem = infer_memory_type(title + " " + knowledges)
        genre = "历史时序排序" if (mem == "sequence" and re.search(r"先后|顺序|排序|依次|排列", title)) else "历史选择"
    else:
        scope, mem = None, None
        genre = infer_ch_genre(title, knowledges)

    if subject == "english":
        neutral = "本题标答为 %s。这一项与题干的时间、主语或搭配对不上（原题解析见正确项）。" % ans
    else:
        neutral = "本题标答为 %s。该项请回到题干与材料核对依据（原题解析原文见正确项）。" % ans
    correct_analysis = analysis[:700] or "题庄原题未提供解析，请以试卷标准答案为准。"
    ref = "标答：%s\n原题解析：%s" % (ans, analysis or "（原题未提供解析）")

    # 题干排第一，来源压到最后一行：和客户端「题干优先」的显示顺序对齐，
    # 这样导入后不必再靠前端的迁移逻辑重排一遍。
    tail = " · ".join(x for x in [source, str(it.get("year") or ""),
                                  ("题庄题号 %s" % qid) if qid else ""] if x)
    passage = "\n".join([
        "【题干原文】",
        stem_text,
        "",
        "【考点】" + (knowledges or "未标注"),
        "【出处】" + tail,
    ])

    q = {
        "id": "TZ%s" % qid,
        "source": "题庄真题 · " + source,
        "subject": subject,
        "stage": "初中",
        "grade": grade,
        "genre": genre,
        "content_scope": scope,
        "memory_type": mem,
        "grammar_group": group_of_en(gpoint) if subject == "english" else None,
        "grammar_point": gpoint if subject == "english" else None,
        "mode": "single",
        "stem": stem_text,
        "passage": passage,
        "options": [
            {"key": k, "text": opts_text[k], "is_correct": (k == ans),
             "trap_type": (None if k == ans else (trap_of_en(gpoint) if subject == "english" else None)),
             "option_analysis": correct_analysis if k == ans else neutral}
            for k in "ABCD"
        ],
        "points": [],
        "formula_ref": formula_for(subject, stem_text + " " + knowledges, mem),
        "total_score": score_of(stem_text),
        "reference_answer": ref,
        "time_anchor": time_anchor(stem_text + " " + analysis[:200]) if subject == "history" else None,
        "tags": ["题庄真题", sub_label, grade + "年级", "需教师校对"],
        "difficulty": max(1, min(5, round(float(it.get("difficulty") or 3)))),
        "question_fingerprint": str(it.get("content_hash") or hashlib.md5(stem_text.encode("utf-8")).hexdigest()[:12]),
    }
    if with_raw:
        q["raw"] = {k: it.get(k) for k in (
            "id", "title_html", "options_html", "answer", "answer_html", "analysis_html",
            "content_hash", "source", "question_type", "is_auto_gradable", "knowledges", "year")}
    return q, None


# ----------------------------- 主流程 -----------------------------

NOTE = (
    "本文件由 tizhuang_fetch.py 从题庄真题库生成。题干、选项、标答、解析均取自题庄原始字段，"
    "仅做 HTML 标签清洗，未改写/重排/重算；每道题的 raw 字段保留原始 HTML 供核对。"
    "formula_ref、genre、content_scope、memory_type、time_anchor 是训练系统的调度与教学标注，"
    "由脚本按关键词推断，建议教师复核；干扰项的 option_analysis 为本系统占位提示语，非原题解析。"
    "答案与解析冲突、含图片、非标准四选一、内容范围不匹配的题已剔除并写入同目录的复核文件。"
    "英语题的 grammar_group / grammar_point 由关键词推断（结构类优先于时态类），"
    "口语交际与语法填空等主观题不在采集范围内。"
)


def fetch_batch(api_key, subject_label, grade_label, limit, keep_out, include_conflicts, with_raw):
    headers, base_path, mode_desc = auth_headers(api_key)
    smap, gmap = resolve_meta(headers)
    if subject_label not in smap or grade_label not in gmap:
        raise RuntimeError("元数据里找不到 %s / %s；可用 --meta 查看实际名称" % (subject_label, grade_label))
    sid, gid = smap[subject_label], gmap[grade_label]
    subject = SUBJECT_OF.get(subject_label, "chinese")
    grade = {"七年级": "七", "八年级": "八", "九年级": "九"}[grade_label]

    # 三科都只取「选择题」：它们是唯一能自动批改的标准四选一。
    # 英语的语法填空/句型转换/改错在题庄是主观题（answer 不是单个字母），
    # 客户端也没有可靠的自动判分依据，宁可不收，也不给孩子一个判错的答案。
    qs = urllib.parse.urlencode({
        "subject_id": sid, "grade_id": gid, "question_type": "选择题",
        "auto_gradable": "true", "has_images": "false",
        "limit": limit, "random_order": "true",
    })
    data = get(base_path + "?" + qs, headers)
    raw_items = data.get("items") or []
    print("  · %s/%s 取回 %d 道（%s，剩余额度 %s）" % (
        subject_label, grade_label, len(raw_items), mode_desc, data.get("quota_remaining_today", "?")))

    items, review, seen = [], [], set()
    for it in raw_items:
        fp = str(it.get("content_hash") or it.get("id"))
        if fp in seen:
            review.append({"id": it.get("id"), "reason": "本批次重复题"})
            continue
        seen.add(fp)
        q, reason = convert(it, subject, grade, keep_out, include_conflicts, with_raw)
        if q:
            items.append(q)
        else:
            review.append({"id": it.get("id"), "reason": reason,
                           "title": clean_html(it.get("title_html") or it.get("title") or "")[:160],
                           "answer": it.get("answer"),
                           "analysis": clean_html(it.get("analysis_html") or it.get("analysis") or "")[:300]})
    return items, review


def write_out(path, items, review_path, review, extra_stats=None, append=False):
    """append=True 时把新题并进已有题库文件，而不是覆盖。
    题庄接口带 random_order，每次取回的是不同的一批；只有累加才谈得上「攒题库」。
    合并按 id 去重，旧题永远保留（新批次不会把以前采到的题冲掉）。"""
    old = []
    if append and os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                old = json.load(f).get("items") or []
        except Exception:
            old = []
    if old:
        seen = {str(q.get("id")) for q in old}
        fresh = [q for q in items if str(q.get("id")) not in seen]
        merged = old + fresh
        added = len(fresh)
    else:
        merged = list(items)
        added = len(items)
    doc = {
        "format": "zx-trainer-bank-v1",
        "source": "题庄真题库（tizhuang.qcscience.cc）",
        "generatedAt": datetime.datetime.now().astimezone().isoformat(),
        "note": NOTE,
        "stats": {"usable": len(merged), "skipped": len(review),
                  "thisRun": len(items), "added": added, **(extra_stats or {})},
        "items": merged,
    }
    os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=2)
    if review:
        with open(review_path, "w", encoding="utf-8") as f:
            json.dump({"note": "以下题未入库，供教师人工复核；脚本不擅自更正答案。",
                       "items": review}, f, ensure_ascii=False, indent=2)
    return doc


def reclassify_file(path):
    """用最新关键词表离线重标已生成题库（不消耗题庄额度，依赖题目里的 raw 字段）。"""
    with open(path, "r", encoding="utf-8") as f:
        doc = json.load(f)
    items = doc.get("items") or []
    changed, no_raw = 0, 0
    for q in items:
        if q.get("subject") != "history":
            continue
        raw = q.get("raw") or {}
        if not raw:
            no_raw += 1
        title = clean_html(raw.get("title_html") or q.get("stem", ""))
        know = str(raw.get("knowledges") or "")
        analysis = clean_html(raw.get("analysis_html") or "")[:300]
        blob = " ".join([title, know, analysis])
        old = q.get("content_scope")
        q["content_scope"] = infer_scope(blob)
        if q["content_scope"] != old:
            changed += 1
        q["memory_type"] = infer_memory_type(title + " " + know)
        q["genre"] = ("历史时序排序" if (q["memory_type"] == "sequence" and
                       re.search(r"先后|顺序|排序|依次|排列", title)) else "历史选择")
        q["formula_ref"] = formula_for("history", title + " " + know, q["memory_type"])
        q["time_anchor"] = time_anchor(title + " " + analysis)
    doc["reclassifiedAt"] = datetime.datetime.now().astimezone().isoformat()
    doc["stats"] = dict(doc.get("stats") or {}, reclassifiedScope=changed)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=2)
    return len(items), changed, no_raw


def main():
    ap = argparse.ArgumentParser(description="题庄真题 → 专项训练系统题库 JSON")
    ap.add_argument("--subject", choices=["语文", "历史", "英语"], default="语文")
    ap.add_argument("--grade", choices=["七年级", "八年级", "九年级"], default="七年级")
    ap.add_argument("--limit", type=int, default=15, help="本次最多取多少道（每道消耗 1 次额度）")
    ap.add_argument("--out", default="", help="输出题库 JSON 路径")
    ap.add_argument("--outdir", default=".", help="--all 时的输出目录")
    ap.add_argument("--api-key",
                    default=os.environ.get("QUESTION_SERVICE_LICENSE", "") or read_local_license(),
                    help="题庄注册 Key；优先用环境变量 QUESTION_SERVICE_LICENSE 或 ~/.tizhuang_license")
    ap.add_argument("--all", action="store_true", help="一次跑完 语文/历史/英语 × 七/八/九 共 9 组")
    ap.add_argument("--meta", action="store_true", help="只打印学科/年级/题型元数据（免费）")
    ap.add_argument("--keep-out-of-scope", action="store_true", help="保留内容范围与年级不匹配的历史题")
    ap.add_argument("--include-conflicts", action="store_true", help="连答案/解析冲突的题也入库（不推荐）")
    ap.add_argument("--no-raw", action="store_true", help="不保留原始 HTML 字段（文件更小）")
    ap.add_argument("--append", action="store_true",
                    help="把本次结果并入已有题库文件（按 id 去重，旧题保留），适合每天跑一点慢慢攒")
    ap.add_argument("--reclassify", nargs="+", default=[], metavar="FILE",
                    help="离线重标已有题库的内容范围/记忆类型（不消耗额度，需含 raw 字段）")
    a = ap.parse_args()

    if a.reclassify:
        for f in a.reclassify:
            try:
                n, ch, nr = reclassify_file(f)
                print("%s：%d 道题，修正内容范围 %d 道%s" %
                      (f, n, ch, "（%d 道缺 raw，仅按题干重标）" % nr if nr else ""))
            except Exception as e:
                print("  ✗ %s：%s" % (f, e))
        return 0

    if a.meta:
        headers, _, _ = auth_headers(a.api_key)
        smap, gmap = resolve_meta(headers)
        print("学科：", json.dumps(smap, ensure_ascii=False))
        print("年级：", json.dumps(gmap, ensure_ascii=False))
        for s in ("语文", "历史", "英语"):
            if s in smap:
                ts = get("/v1/meta/question-types?subject_id=%d" % smap[s], headers)
                names = sorted({x["name"] for x in ts}) if isinstance(ts, list) else ts
                print("%s 题型：" % s, json.dumps(names, ensure_ascii=False)[:800])
        return 0

    combos = ([(s, g) for s in ("语文", "历史", "英语") for g in ("七年级", "八年级", "九年级")]
              if a.all else [(a.subject, a.grade)])
    if a.all and not a.api_key and a.limit * len(combos) > 48:
        print("提示：匿名试用 24 小时只有 50 题，本次将请求 %d 题，可能触发 429。"
              "建议 --limit 6 以内，或配置注册 Key（每日 150 题）。" % (a.limit * len(combos)))

    total_ok = total_skip = failed = 0
    for s, g in combos:
        print("\n[%s · %s]" % (s, g))
        try:
            items, review = fetch_batch(a.api_key, s, g, a.limit,
                                        a.keep_out_of_scope, a.include_conflicts, not a.no_raw)
        except RuntimeError as e:
            print("  ✗", e)
            failed += 1
            continue
        if a.all:
            out = os.path.join(a.outdir, "题庄_%s_%s_题库.json" % (s, g))
            rev = os.path.join(a.outdir, "题庄_%s_%s_复核.json" % (s, g))
        else:
            out = a.out or ("题庄_%s_%s_题库.json" % (s, g))
            rev = os.path.splitext(out)[0] + "_复核.json"
        write_out(out, items, rev, review, append=a.append)
        total_ok += len(items); total_skip += len(review)
        print("  ✓ 本次可用 %d 道%s → %s" % (
            len(items), "（已并入旧题）" if a.append else "", out))
        if review:
            print("  · 待复核 %d 道 → %s" % (len(review), rev))
            for r in review[:3]:
                print("      - 题庄 %s：%s" % (r["id"], r["reason"]))

    print("\n完成：共 %d 道可导入，%d 道待复核%s。" % (
        total_ok, total_skip, "，%d 组失败" % failed if failed else ""))
    print("把「*_题库.json」用 index.html 的「题库 → 选择 .json 文件」导入即可。")
    return 2 if (failed and not total_ok) else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n已中断")
        sys.exit(130)
    except Exception as e:
        print("失败：%s" % e, file=sys.stderr)
        sys.exit(1)

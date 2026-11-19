#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成原创英语阅读理解种子题（湖南中考风格）。

湖南 2025 修订考纲（2026 起）：英语阅读 15 题 ×2 分 = 30 分，是全卷第一大板块。
本系统不练听力/写作，阅读必须补。这里按「整篇短文 + 拆成多道单选题」的
结构与 cloze-original.json 完全对齐，复用同一套 passage 渲染与判分引擎。

每篇 5 小题，覆盖中考阅读四大常考题型：细节理解 / 推理判断 / 主旨大意 / 词义猜测。
输出 reading-original.json，由 merge_bank.py 并入 all.json。
"""
import datetime
import hashlib
import json
import os

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                   '..', '..', '上传到GitHub', 'bank', 'reading-original.json')

FORMULA = '阅读理解 = 先看题干定位 → 回原文找依据 → 细节比对 / 逻辑推理 / 概括主旨'
GENRE = '阅读理解'

# 每篇：title, grade, tags(题材), passage, questions[5]
# 每个 question: (qtype, stem_en, options[(text, correct, why_wrong_or_right)], answer_key, analysis)
ARTICLES = [
    {
        "id": "RD001",
        "title": "The Old Bike",
        "grade": "八",
        "topic": "记叙文 · 亲情与成长",
        "passage": (
            "Last Saturday, I found an old bike in the corner of our garage. It was covered "
            "with dust and its paint had faded. I almost walked away, but something made me stop. "
            "It was the bike my father used to ride to work twenty years ago.\n\n"
            "I cleaned it carefully and took it to a small shop nearby. The owner, an old man "
            "with grey hair, looked at it for a long time. \"This is a Forever bike,\" he said. "
            "\"People once waited months to buy one.\" He repaired the wheels and polished the "
            "frame for only fifty yuan.\n\n"
            "When I rode it home, I felt something I had never felt before. The bike was slow "
            "and the bell was loud, but every turn seemed to tell a story. My father saw it and "
            "smiled. \"I bought it with my first month's salary,\" he said. That evening he told "
            "me about the long rides to the factory, about the rain and the cold winter mornings.\n\n"
            "Now the bike stands in our living room, not in the garage. It is too old to ride "
            "every day, but to my father it is the most valuable thing in our home."
        ),
        "questions": [
            ("细节理解",
             "Where did the writer find the old bike at first?",
             [("In a small repair shop", False, "修理店是后来才去的地方，不是最初发现自行车的地方"),
              ("In the corner of the garage", True, "对应首句「in the corner of our garage」，正确"),
              ("On the street near home", False, "文中未说在街上发现"),
              ("In the factory", False, "factory 只出现在父亲骑车的回忆里")],
             "B", "定位第一段首句：old bike 在自家车库角落（in the corner of our garage）。"),
            ("词义猜测",
             "The underlined word \"faded\" in Paragraph 1 probably means \"___\".",
             [("became less bright", True, "前文说蒙尘、后文又提到旧，faded 指颜色变淡、褪色，正确"),
              ("became much heavier", False, "与 paint（油漆）搭配不当"),
              ("was completely new", False, "与 old、dust 语义相反"),
              ("was broken into pieces", False, "若已碎裂就不会只是 cleaned 后拿去修")],
             "A", "由 covered with dust 和 old bike 的语境可推断 faded 是「褪色、失去光泽」。"),
            ("推理判断",
             "Why did the shop owner look at the bike for a long time?",
             [("He had never seen a bike before", False, "不合常理，文中也无依据"),
              ("He wanted to buy it from the writer", False, "文中是他帮着修理，并未提出购买"),
              ("He recognized it as a valuable old model", True, "他随后说这是 Forever 牌、当年要等几个月才能买，说明他认出了它的价值"),
              ("He was too tired to work", False, "无中生有")],
             "C", "老板看了很久后说「这是永久牌，以前要等几个月才能买到」，可推断他认出这是有价值的旧款。"),
            ("主旨大意",
             "What is the best title for the passage?",
             [("A Bike Full of Stories", True, "全文借一辆旧车串起父亲的往事与亲情，概括最准"),
              ("How to Repair an Old Bike", False, "修理只是中间一小段，不是主旨"),
              ("A Busy Saturday", False, "只对应开头时间，过于片面"),
              ("My Father's Factory", False, "factory 只是回忆里的地点，以偏概全")],
             "A", "文章核心是旧自行车承载的回忆与父爱，A 最能概括全文。"),
            ("推理判断",
             "What can we learn from the last paragraph?",
             [("The bike is useless and should be thrown away", False, "与 valuable 直接矛盾"),
              ("The father no longer likes the bike", False, "与父亲的珍惜态度相反"),
              ("The bike is precious to the family though it is old", True, "too old to ride 却 the most valuable，正说明它珍贵"),
              ("The writer will sell the bike one day", False, "文中没有要卖的意思")],
             "C", "末段「太旧不能常骑，却是家里最珍贵的东西」直接点明：旧但珍贵。"),
        ],
    },
    {
        "id": "RD002",
        "title": "Why Sleep Matters",
        "grade": "八",
        "topic": "说明文 · 健康与科学",
        "passage": (
            "Sleep is not a waste of time. While you are asleep, your body is still working "
            "hard. It repairs tired muscles, fights off illness and stores what you learned "
            "during the day. Scientists say that teenagers need about eight to ten hours of "
            "sleep every night.\n\n"
            "But many students get far less. Staying up late with phones or homework has "
            "become common. Research shows that less sleep can make it harder to pay attention "
            "in class, slow down your reactions and even change your mood. Students who sleep "
            "well usually remember new words better and do well in sports.\n\n"
            "So how can you sleep better? First, keep a regular bedtime, even on weekends. "
            "Second, put away your phone at least half an hour before bed — the bright screen "
            "tells your brain that it is still daytime. Third, keep your room cool and quiet. "
            "Small changes can make a big difference.\n\n"
            "Remember, sleep is not the enemy of hard work. It is part of it."
        ),
        "questions": [
            ("细节理解",
             "How many hours of sleep do teenagers need every night according to scientists?",
             [("About five to six hours", False, "数字与原文不符"),
              ("About eight to ten hours", True, "对应第一段末句 eight to ten hours，正确"),
              ("About twelve hours", False, "数字偏大，文中未提"),
              ("As many as possible", False, "文中给的是明确区间，不是越多越好")],
             "B", "第一段末句：teenagers need about eight to ten hours of sleep every night。"),
            ("细节理解",
             "Which of the following is NOT mentioned as a result of less sleep?",
             [("Harder to pay attention in class", False, "原文明确提到 pay attention 变难"),
              ("Slower reactions", False, "原文提到 slow down your reactions"),
              ("Better memory of new words", True, "记忆更好是「睡得好」的结果，属于反向干扰"),
              ("Changes in mood", False, "原文提到 even change your mood")],
             "C", "原文说睡得好才 remember new words better，睡不好不会让记忆更好，故选 C。"),
            ("词义猜测",
             "What does the underlined phrase \"Staying up late\" mean in Chinese?",
             [("早睡", False, "与 late 矛盾"),
              ("熬夜", True, "与后半句 with phones or homework 及 sleep less 对应，意为熬夜"),
              ("睡懒觉", False, "睡懒觉不会导致 get far less sleep"),
              ("午休", False, "与语境无关")],
             "B", "由 get far less sleep 与「玩手机/赶作业」可推断是「熬夜」。"),
            ("推理判断",
             "Why should you put away your phone before bed?",
             [("Because phones are expensive", False, "文中未提价格"),
              ("Because the bright screen makes the brain think it is still daytime", True, "第三段明确解释了屏幕亮光的影响"),
              ("Because phones cannot be charged in bed", False, "无中生有"),
              ("Because phones will wake you up with calls", False, "文中未提来电")],
             "B", "第三段：the bright screen tells your brain that it is still daytime。"),
            ("主旨大意",
             "What is the main idea of the passage?",
             [("Sleep is important and we should sleep well", True, "全文讲睡眠的作用、不足的危害和改善方法，概括最全"),
              ("Students should do more homework", False, "与文章主旨无关"),
              ("Phones are bad for everyone", False, "手机只是影响睡眠的一个因素，以偏概全"),
              ("Teenagers like staying up late", False, "只是现象描述，不是文章要传达的核心")],
             "A", "文章从作用、危害到建议都在说明「睡眠重要、要睡好」，A 最全面。"),
        ],
    },
    {
        "id": "RD003",
        "title": "Should Students Use Phones at School?",
        "grade": "九",
        "topic": "议论文 · 校园与规则",
        "passage": (
            "More and more students bring smartphones to school. Should they be allowed to "
            "use them in class? People hold different views.\n\n"
            "Some students think phones help them learn. They can look up new words, take "
            "photos of key points and check information quickly. When a problem is hard, a "
            "phone can be a useful tool.\n\n"
            "Others, however, worry that phones cause trouble. Games and short videos can "
            "easily draw students' attention away from lessons. Chatting in class may disturb "
            "both the user and classmates. Worse still, some students compare phones and feel "
            "unhappy about what they own.\n\n"
            "In my opinion, the key is self-control, not the phone itself. Schools can set "
            "clear rules: keep phones silent during class and use them only for learning with "
            "a teacher's permission. If students can manage themselves, phones can stay; if "
            "not, they should be kept at home. Technology is neither good nor bad — it depends "
            "on how we use it."
        ),
        "questions": [
            ("细节理解",
             "What is one reason some students support using phones at school?",
             [("They can play games between classes", False, "游戏是反对者担心的问题，不是支持理由"),
              ("They can look up new words and check information", True, "第二段列举了查单词、拍重点、查资料等学习用途"),
              ("They can compare phones with classmates", False, "这是反对者提到的负面现象"),
              ("They can chat freely in class", False, "课堂聊天是作者反对的行为")],
             "B", "第二段：look up new words, take photos of key points and check information。"),
            ("词义猜测",
             "The underlined word \"disturb\" in Paragraph 3 is closest to \"___\".",
             [("help", False, "语义相反"),
              ("trouble", True, "课堂上聊天会打扰自己和同学，disturb 意为打扰、干扰"),
              ("protect", False, "语义相反"),
              ("follow", False, "与语境不符")],
             "B", "由 Chatting in class 影响 user 和 classmates 可知 disturb 意为「打扰、干扰」。"),
            ("推理判断",
             "What is the writer's opinion about phones at school?",
             [("Phones should be banned completely", False, "作者没有主张完全禁止"),
              ("Phones should be used freely anytime", False, "作者强调规则和自我控制"),
              ("It depends on students' self-control", True, "第四段首句 the key is self-control 是核心观点"),
              ("Only teachers may bring phones", False, "文中无此主张")],
             "C", "第四段明确：关键在于 self-control，能自控就可带、不能自控就留在家。"),
            ("推理判断",
             "Which rule would the writer probably agree with?",
             [("Use phones for fun in every class", False, "与作者主张相悖"),
              ("Keep phones silent in class and use them for learning with permission", True, "与第四段提出的规则完全一致"),
              ("Ban all technology at school", False, "作者认为技术本身无好坏"),
              ("Allow phone comparisons in class", False, "比较手机是作者提到的负面影响")],
             "B", "第四段：keep phones silent during class and use them only for learning with a teacher's permission。"),
            ("主旨大意",
             "Which is the best title for the passage?",
             [("Phones at School: A Balanced View", True, "文章呈现正反两方并给出折中观点，标题最贴切"),
              ("Phones Are Good for Study", False, "只写了一个方面"),
              ("Never Bring Phones to School", False, "只写了反对观点"),
              ("How to Buy a Smartphone", False, "完全无关")],
             "A", "文章既讲好处也讲担忧，最后给出平衡观点，A 概括最准。"),
        ],
    },
    {
        "id": "RD004",
        "title": "School Clubs Fair",
        "grade": "八",
        "topic": "应用文 · 海报与广告",
        "passage": (
            "SUNSHINE MIDDLE SCHOOL — CLUBS FAIR\n"
            "Friday, September 12 | 3:30 p.m. – 5:00 p.m. | School Hall\n\n"
            "Come and find a club you love! All students are welcome. Each club will show "
            "what they do and you can sign up on the spot.\n\n"
            "• Green Club — Learn to protect the environment. We meet every Wednesday "
            "after school and plant trees in spring. (Open to Grade 7–9)\n"
            "• English Drama Club — Put on a short play at the school art festival. "
            "Practice every Tuesday. No experience needed! (Grade 8–9 only)\n"
            "• Robot Club — Build and program your own robot. Space is limited to 20 "
            "members. Bring your own computer. (Grade 7–8 only)\n"
            "• Reading Club — Read one book a month and share your ideas over tea. "
            "Every Thursday afternoon. (All grades)\n\n"
            "Free entry. Bring a friend and join us!"
        ),
        "questions": [
            ("细节理解",
             "When will the Clubs Fair be held?",
             [("On Friday, September 12", True, "海报顶部时间：Friday, September 12"),
              ("On Tuesday, September 12", False, "Tuesday 是戏剧社活动时间，不是博览会时间"),
              ("On Wednesday after school", False, "这是环保社活动时间"),
              ("On the school art festival", False, "艺术节是戏剧社演出的场合")],
             "A", "海报第一行时间栏写明 Friday, September 12。"),
            ("细节理解",
             "Which club can a Grade 7 student join?",
             [("English Drama Club", False, "戏剧社限 Grade 8–9，七年级不符合"),
              ("English Drama Club and Green Club", False, "戏剧社限 Grade 8–9，七年级不能加入"),
              ("Green Club, Robot Club and Reading Club", True, "环保社 Grade 7–9、机器人社 Grade 7–8、读书社 All grades，七年级三个都可参加"),
              ("Only the Reading Club", False, "不完整——七年级还可参加环保社和机器人社")],
             "C", "逐条核对：环保社 7–9 ✓、机器人社 7–8 ✓、读书社 All grades ✓；戏剧社限 8–9 ✗。"),
            ("细节理解",
             "What should members of the Robot Club bring?",
             [("A book", False, "读书社才需要读书"),
              ("Their own computer", True, "机器人社说明中写明 Bring your own computer"),
              ("A robot", False, "机器人是去做的，不是自带的"),
              ("Some tea", False, "茶是读书社分享时的")],
             "B", "Robot Club 条目：Bring your own computer。"),
            ("推理判断",
             "Which club would be best for a student who loves acting but has no experience?",
             [("Green Club", False, "环保社与表演无关"),
              ("English Drama Club", True, "戏剧社说 put on a short play 且 No experience needed，正符合"),
              ("Robot Club", False, "与表演无关且需电脑"),
              ("Reading Club", False, "读书社是读书分享，不上台表演")],
             "B", "戏剧社明说无需经验、会在艺术节演短剧，最适合想表演的新手。"),
            ("主旨大意",
             "What is the main purpose of this passage?",
             [("To invite students to join clubs", True, "海报开头 Come and find a club you love、结尾 join us，目的是招募"),
              ("To teach students how to plant trees", False, "植树只是环保社的一项活动"),
              ("To introduce a new school", False, "学校只是背景"),
              ("To sell computers to students", False, "电脑是学生自备，不出售")],
             "A", "这是一则社团招新海报，核心目的是邀请学生参加社团。"),
        ],
    },
    {
        "id": "RD005",
        "title": "My New Friend Lisa",
        "grade": "七",
        "topic": "记叙文 · 校园与友谊（七年级）",
        "passage": (
            "Lisa is my new classmate. She came to our school last month from Canada. "
            "At first, she was very quiet. She sat alone and did not talk much. I wanted "
            "to help her feel at home.\n\n"
            "One day, I brought some Chinese cookies to school and gave her one. She "
            "smiled and said \"thank you\" in Chinese. Then she told me she loved our "
            "school lunch, especially the dumplings. We started to eat together every day.\n\n"
            "Lisa is good at drawing. She drew a small picture of our classroom and gave "
            "it to me. In the picture, everyone is smiling. I was surprised because I "
            "never thought she watched us so carefully. Now we are best friends. She "
            "teaches me English and I teach her Chinese.\n\n"
            "I learn one thing from Lisa: a friend is someone who shares your cookies "
            "and sees the smile on your face."
        ),
        "questions": [
            ("细节理解",
             "Where did Lisa come from?",
             [("Canada", True, "首段 from Canada，正确"),
              ("China", False, "中国是作者所在的地方，不是 Lisa 的来源"),
              ("England", False, "文中未提"),
              ("Australia", False, "文中未提")],
             "A", "定位第一段：She came to our school last month from Canada。"),
            ("词义猜测",
             "What does the underlined word \"alone\" mean in Chinese?",
             [("开心地", False, "与 quiet、did not talk much 的语境不符"),
              ("独自地", True, "她刚来、安静、不多说话，sat alone 意为独自坐着"),
              ("大声地", False, "与 quiet 矛盾"),
              ("匆忙地", False, "与语境无关")],
             "B", "由 she was very quiet 和 did not talk much 可推断 alone 是「独自」。"),
            ("细节理解",
             "What did the writer give Lisa first?",
             [("A picture", False, "picture 是 Lisa 后来送给作者的"),
              ("Some Chinese cookies", True, "第二段 brought some Chinese cookies and gave her one"),
              ("A dumpling", False, "dumplings 是学校午餐，不是作者给的"),
              ("An English book", False, "文中未提")],
             "B", "第二段首句：I brought some Chinese cookies to school and gave her one。"),
            ("推理判断",
             "Why was the writer surprised?",
             [("Because Lisa drew very fast", False, "文中没说画得快"),
              ("Because Lisa was good at drawing", False, "这是事实，但不是作者惊讶的原因"),
              ("Because Lisa watched the class carefully and drew everyone smiling", True, "作者没想到她把大家观察得这么仔细、画里人人都在笑"),
              ("Because Lisa left the school", False, "与文中不符")],
             "C", "第三段：I was surprised because I never thought she watched us so carefully。"),
            ("主旨大意",
             "What is the passage mainly about?",
             [("How to draw nice pictures", False, "画画只是其中一个细节"),
              ("How the writer made a new friend", True, "全文讲作者和 Lisa 从陌生到成为好朋友的过程"),
              ("Chinese food at school", False, "食物是友谊的线索，不是全文主旨"),
              ("A hard school day", False, "与文章温暖基调不符")],
             "B", "文章围绕作者如何与 Lisa 成为朋友展开，B 最贴切。"),
        ],
    },
    {
        "id": "RD006",
        "title": "The Clever Crow",
        "grade": "七",
        "topic": "记叙文 · 动物故事（七年级）",
        "passage": (
            "It was a hot summer day. A crow was very thirsty. He flew everywhere to "
            "find water, but he could not find any. At last, he saw a bottle under a "
            "tree. There was a little water in it.\n\n"
            "The crow was happy, but then he had a problem. The bottle was tall and "
            "his beak could not reach the water. He thought and thought. He saw some "
            "small stones on the ground.\n\n"
            "Suddenly, he had an idea. He picked up the stones one by one and put "
            "them into the bottle. Slowly, the water came up. At last, the crow could "
            "reach the water and drank it.\n\n"
            "This story tells us that we should never give up. When we have a problem, "
            "we should think carefully and try different ways. Even a small, clever "
            "step can help us win."
        ),
        "questions": [
            ("细节理解",
             "What did the crow want to find?",
             [("Food", False, "文中说的是 thirsty 想找水"),
              ("Water", True, "首段 He flew everywhere to find water"),
              ("A friend", False, "文中未提"),
              ("A tree", False, "树只是瓶子所在的地方")],
             "B", "定位第一段：A crow was very thirsty... to find water。"),
            ("细节理解",
             "Why could the crow not drink the water at first?",
             [("The water was dirty", False, "文中没说水脏"),
              ("The bottle was tall and his beak could not reach it", True, "第二段明确说明瓶子高、喙够不到"),
              ("There was no water in the bottle", False, "瓶里其实有一点水"),
              ("The crow was not thirsty", False, "与首段 thirsty 矛盾")],
             "B", "第二段：The bottle was tall and his beak could not reach the water。"),
            ("推理判断",
             "How did the stones help the crow?",
             [("They made the water come up", True, "石头放进瓶里，水位上升，乌鸦才够得到"),
              ("They made the water clean", False, "文中没说净化水"),
              ("They broke the bottle", False, "与原文不符"),
              ("They gave the crow food", False, "无关")],
             "A", "第三段：He put stones into the bottle... the water came up。"),
            ("词义猜测",
             "The phrase \"give up\" in the last paragraph means \"___\".",
             [("尝试", False, "与 never 搭配和全文主旨不符"),
              ("放弃", True, "never give up 是「永不放弃」，符合故事寓意"),
              ("成功", False, "语义不通"),
              ("休息", False, "与语境无关")],
             "B", "由结尾寓意「遇到问题要多想办法」可知 give up 是「放弃」。"),
            ("主旨大意",
             "What does the story want to tell us?",
             [("Crows like drinking water", False, "只是故事表层"),
              ("Never give up and think of clever ways", True, "末段明确点出寓意"),
              ("Stones are useful", False, "石头是方法，不是道理"),
              ("Summer is hot", False, "天气只是背景")],
             "B", "末段：we should never give up... think carefully and try different ways。"),
        ],
    },
]


def make_item(art, idx, q):
    qtype, stem, opts, key, analysis = q
    qno = idx + 1
    total = len(art["questions"])
    keys = "ABCD"
    options = []
    for i, (text, correct, why) in enumerate(opts):
        options.append({
            "key": keys[i],
            "text": text,
            "is_correct": bool(correct),
            "trap_type": None if correct else qtype,
            "option_analysis": ("正确。" + why) if correct else ("不选「%s」：%s" % (text, why)),
        })
    fp = "%s_%d" % (art["id"], qno)
    return {
        "id": "RD%03d_%d" % (int(art["id"][2:]), qno),
        "source": "原创阅读 · %s（%s） · 第%d/%d题" % (art["title"], art["topic"], qno, total),
        "subject": "english",
        "stage": "初中",
        "grade": art["grade"],
        "genre": GENRE,
        "content_scope": None,
        "memory_type": None,
        "grammar_group": "阅读理解",
        "grammar_point": qtype,
        "mode": "single",
        "stem": "第 %d 题（%s）：%s" % (qno, qtype, stem),
        "passage": art["passage"],
        "options": options,
        "points": [],
        "formula_ref": FORMULA,
        "total_score": 2,
        "reference_answer": "标答：%s. %s\n解析：%s" % (
            key, dict((k, t) for k, t, _ in [(keys[i], o[0], o[1]) for i, o in enumerate(opts)])[key], analysis),
        "time_anchor": None,
        "tags": ["阅读理解", "原创", art["topic"], "第%d题" % qno, qtype],
        "difficulty": 3 if qtype == "细节理解" else 4,
        "question_fingerprint": fp,
        "reading_group": art["id"],
        "reading_title": art["title"],
        "reading_no": qno,
        "reading_total": total,
        "reading_type": qtype,
        "raw": "",
    }


def main():
    items = []
    for art in ARTICLES:
        for i, q in enumerate(art["questions"]):
            items.append(make_item(art, i, q))
    doc = {
        "name": "原创阅读理解种子题",
        "note": "整篇短文拆成多道单选题，共享 passage。merge_bank 并入 all.json，每天更新不会冲掉。",
        "updatedAt": datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).isoformat(),
        "items": items,
    }
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False)
    print("生成 %s：%d 篇 / %d 题" % (os.path.basename(OUT), len(ARTICLES), len(items)))


if __name__ == "__main__":
    main()

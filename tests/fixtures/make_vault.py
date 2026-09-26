"""生成可重复的演示 Vault，供截图对比、端到端和手工验收使用（不含任何真实数据）。

    python3 tests/fixtures/make_vault.py --out /tmp/omrs-fixture              # full：约 40 题 + 标记 + 反馈 + 展示板
    python3 tests/fixtures/make_vault.py --out /tmp/omrs-empty --profile empty # 空库，用来看空状态

full 档内容：4 科 12 个分类、LaTeX 行内/块级、长题面、中英混排、3 张生成的示意图、3 个标记、
3 轮反馈（对错混合，产生熟练度差异与时间线）、1 道停用题、1 块展示板。题目直接调用
omrs.creation.create_question 创建；标记、反馈、停用和展示板通过临时启动的本地实例走 HTTP API，
与真实用户路径一致。同一 --seed 生成的题目集合、标记和反馈分数完全相同（时间戳随运行时刻变化）。
"""
import argparse
import base64
import io
import json
import os
import random
import shutil
import socket
import subprocess
import tempfile
import sys
import time
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

LONG = ("这是一道题干较长的题目，用来观察长文本在表格、画廊卡片、详情页和展示板中的换行、截断与行高是否合理，"
        "同时混入 English words 与数字 12345 检查中英混排的基线对齐。")

QUESTIONS = [
    ("数学", "三角函数", r"已知 $\sin\alpha+\cos\alpha=\frac{1}{5}$，且 $0<\alpha<\pi$，求 $\tan\alpha$。",
     r"平方得 $2\sin\alpha\cos\alpha=-\frac{24}{25}$，$\alpha$ 在第二象限，$\tan\alpha=-\frac{4}{3}$。", ["同角关系"]),
    ("数学", "三角函数", r"求 $y=\sin 2x+\sqrt{3}\cos 2x$ 的最小正周期与最大值。",
     r"$y=2\sin\left(2x+\frac{\pi}{3}\right)$，周期 $\pi$，最大值 $2$。", ["辅助角公式"]),
    ("数学", "三角函数", r"在 $\triangle ABC$ 中，$a=3,b=4,C=60^\circ$，求 $c$。" + LONG,
     r"$$c^2=a^2+b^2-2ab\cos C=13,\quad c=\sqrt{13}$$", ["余弦定理"]),
    ("数学", "数列", r"等比数列 $\{a_n\}$ 中 $a_2=2,a_5=16$，求 $S_n$。", r"$q=2,a_1=1,S_n=2^n-1$。", ["等比数列"]),
    ("数学", "数列", r"已知 $a_{n+1}=2a_n+1,a_1=1$，求通项。", r"$a_n+1=2^n$，故 $a_n=2^n-1$。", ["构造法"]),
    ("数学", "数列", r"求 $\sum_{k=1}^{n}\frac{1}{k(k+1)}$。", r"裂项得 $1-\frac{1}{n+1}$。", ["裂项相消"]),
    ("数学", "函数", r"设 $f(x)=\ln x-ax$ 在 $(0,+\infty)$ 上单调递减，求 $a$ 的范围。" + LONG,
     r"$f'(x)=\frac1x-a\le 0$ 恒成立，需 $a\ge\sup\frac1x$，无解；题设应为 $[1,+\infty)$ 上递减，得 $a\ge1$。", ["导数与单调性"]),
    ("数学", "函数", r"求 $f(x)=x^3-3x$ 的极值。", r"$f'(x)=3x^2-3$，极大值 $f(-1)=2$，极小值 $f(1)=-2$。", ["极值"]),
    ("数学", "函数", r"比较 $\log_2 3$ 与 $\log_3 4$ 的大小。", r"作商或借助中间量 $\frac{3}{2}$，得 $\log_2 3>\log_3 4$。", ["对数比较"]),
    ("数学", "解析几何", r"椭圆 $\frac{x^2}{4}+\frac{y^2}{3}=1$ 的离心率。", r"$e=\frac{c}{a}=\frac12$。", ["椭圆"]),
    ("数学", "解析几何", r"抛物线 $y^2=4x$ 焦点弦长公式推导。", r"$|AB|=x_1+x_2+p$。", ["抛物线"]),
    ("数学", "立体几何", "正方体 $ABCD-A_1B_1C_1D_1$ 中，求异面直线 $A_1B$ 与 $B_1C$ 所成角。", r"平移得 $60^\circ$。", ["异面直线"]),
    ("物理", "力学", r"质量为 $m$ 的物块在倾角 $\theta$ 的光滑斜面上下滑，求加速度。", r"$a=g\sin\theta$。", ["牛顿第二定律"]),
    ("物理", "力学", r"平抛运动初速度 $v_0$，下落高度 $h$，求水平位移。", r"$x=v_0\sqrt{\frac{2h}{g}}$。", ["平抛"]),
    ("物理", "力学", "轻绳连接两物块跨过定滑轮，求加速度与绳子拉力。" + LONG, r"$a=\frac{(m_1-m_2)g}{m_1+m_2}$。", ["连接体"]),
    ("物理", "力学", r"圆周运动最高点恰好通过的条件。", r"$mg=\frac{mv^2}{r}$，$v=\sqrt{gr}$。", ["圆周运动"]),
    ("物理", "电磁学", r"长 $L$ 的导体棒以速度 $v$ 垂直切割磁感线，求电动势。", r"$E=BLv$。", ["电磁感应"]),
    ("物理", "电磁学", r"带电粒子垂直进入匀强磁场，求轨道半径。", r"$r=\frac{mv}{qB}$。", ["洛伦兹力"]),
    ("物理", "电磁学", "闭合电路中滑动变阻器滑片右移，判断各表示数变化。", "外电阻增大，干路电流减小，路端电压增大。", ["动态电路"]),
    ("物理", "热学", r"理想气体等温压缩，体积减半，压强如何变化？", r"$pV=C$，压强加倍。", ["气体定律"]),
    ("化学", "有机", "写出乙醇催化氧化的化学方程式。",
     r"$2\mathrm{CH_3CH_2OH}+\mathrm{O_2}\xrightarrow{\mathrm{Cu}}2\mathrm{CH_3CHO}+2\mathrm{H_2O}$", ["醇的性质"]),
    ("化学", "有机", "判断下列物质能否使酸性高锰酸钾褪色：苯、甲苯、乙烯。", "甲苯、乙烯能；苯不能。", ["苯的同系物"]),
    ("化学", "有机", "写出乙酸乙酯在碱性条件下水解的方程式。" + LONG,
     r"$\mathrm{CH_3COOC_2H_5+NaOH\to CH_3COONa+C_2H_5OH}$", ["酯的水解"]),
    ("化学", "反应原理", r"$N_2+3H_2\rightleftharpoons 2NH_3$ 增大压强，平衡如何移动？", "向气体分子数减少的方向（正向）移动。", ["化学平衡"]),
    ("化学", "反应原理", "原电池中电子与阳离子的移动方向。", "电子由负极经导线流向正极；阳离子移向正极。", ["原电池"]),
    ("化学", "反应原理", r"$0.1\,\mathrm{mol/L}$ 醋酸加水稀释，$c(H^+)$ 与电离度如何变化？", "$c(H^+)$ 减小，电离度增大。", ["弱电解质"]),
    ("化学", "物质结构", "比较 Na、Mg、Al 的第一电离能。", "Mg > Al > Na（Mg 为全满 3s²）。", ["电离能"]),
    ("英语", "语法", "Choose: If I ___ you, I would take the offer.", "were（与现在事实相反的虚拟语气）", ["虚拟语气"]),
    ("英语", "语法", "It was not until midnight ___ he finished the report.", "that（强调句 not until）", ["强调句"]),
    ("英语", "语法", "The number of students ___ increased this year.", "has（the number of 作主语谓语用单数）", ["主谓一致"]),
    ("英语", "语法", "___ from the top of the hill, the town looks beautiful.", "Seen（过去分词作状语，与主语被动关系）", ["非谓语动词"]),
    ("英语", "词汇", "辨析 affect / effect。", "affect 动词“影响”；effect 名词“效果”，effect 作动词意为“实现”。", ["易混词"]),
    ("英语", "词汇", "辨析 rise / raise。", "rise 不及物；raise 及物。", ["易混词"]),
    ("英语", "阅读", "Main idea question: what is the passage mainly about? " + LONG, "抓首尾段与段落主题句。", ["主旨题"]),
    ("数学", "概率统计", r"掷两枚骰子，点数和为 7 的概率。", r"$\frac{6}{36}=\frac16$。", ["古典概型"]),
    ("数学", "概率统计", r"$X\sim B(10,0.3)$，求 $E(X)$ 与 $D(X)$。", r"$E=3,\;D=2.1$。", ["二项分布"]),
    ("数学", "向量", r"$|\vec a|=2,|\vec b|=1,\vec a\cdot\vec b=1$，求夹角。", r"$\cos\theta=\frac12$，$\theta=\frac{\pi}{3}$。", ["数量积"]),
    ("物理", "光学", "光从水射入空气，入射角增大到一定程度会发生什么？", "全反射，临界角 $\\sin C=\\frac1n$。", ["全反射"]),
    ("化学", "实验", "配制一定物质的量浓度溶液，定容时俯视刻度线，浓度偏大还是偏小？", "体积偏小，浓度偏大。", ["误差分析"]),
    ("英语", "写作", "写一句含定语从句的句子描述你的学校。", "My school, which was founded in 1950, has a beautiful library.", ["定语从句"]),
]
IMAGE_FOR = {1: "sine", 12: "incline", 36: "vector"}  # 题目序号 → 生成的示意图
LABELS = [("考前必看", "#dc2626"), ("计算失误", "#ca8a04"), ("概念不清", "#2563eb")]


def make_image(kind):
    from PIL import Image, ImageDraw
    img = Image.new("RGB", (480, 220), "white")
    d = ImageDraw.Draw(img)
    d.line([(20, 110), (460, 110)], fill="black", width=2)
    d.line([(40, 200), (40, 20)], fill="black", width=2)
    if kind == "sine":
        import math
        pts = [(40 + x, 110 - 70 * math.sin(x / 40)) for x in range(0, 420, 4)]
        d.line(pts, fill="black", width=3)
    elif kind == "incline":
        d.polygon([(60, 200), (420, 200), (420, 60)], outline="black", width=3)
        d.rectangle([(260, 100), (310, 140)], outline="black", width=3)
    else:
        d.line([(40, 110), (300, 40)], fill="black", width=4)
        d.line([(40, 110), (360, 110)], fill="black", width=4)
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def post(port, path, body):
    req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode() or "{}")


def build_full(vault, seed):
    from omrs.creation import create_question
    rng = random.Random(seed)
    uids = []
    for i, (subject, category, q, a, tags) in enumerate(QUESTIONS):
        images = [make_image(IMAGE_FOR[i])] if i in IMAGE_FOR else None
        result = create_question(vault, subject, category, 5, related_tags=tags,
                                 question_text=q, answer_text=a, question_images=images)
        uids.append(result["uid"])
    port = free_port()
    log = tempfile.TemporaryFile(mode="w+")  # 实例日志只在失败排查时有用，不落在 Vault 旁边
    proc = subprocess.Popen([sys.executable, os.path.join(ROOT, "omrs_engine.py"), "--vault", vault,
                             "serve", "-p", str(port)], stdin=subprocess.DEVNULL, stdout=log, stderr=log)
    try:
        for _ in range(100):
            try:
                urllib.request.urlopen(f"http://127.0.0.1:{port}/api/auth/session", timeout=2)
                break
            except OSError:
                time.sleep(0.2)
        for order, (name, color) in enumerate(LABELS):
            post(port, "/api/label/save", {"name": name, "color": color, "priority_bonus": 0.2, "order": order})
        for uid in rng.sample(uids, 12):
            post(port, "/api/question/labels", {"uid": uid, "labels": rng.sample([n for n, _ in LABELS], rng.randint(1, 2))})
        for round_no in range(3):
            batch = rng.sample(uids, 18 - round_no * 4)
            feedbacks = [{"uid": uid, "sub_score": rng.randint(2, 10), "is_correct": rng.random() < 0.6,
                          "source": "manual", "note": ""} for uid in batch]
            post(port, "/api/feedback", {"session_id": f"FIXTURE-{seed}-{round_no}", "feedbacks": feedbacks})
        post(port, "/api/question/suspend", {"uid": uids[-1], "reason": "演示：暂不复习"})
        post(port, "/api/board/create", {"name": "三角与数列", "uids": uids[:6]})
    finally:
        proc.terminate()
        proc.wait(timeout=10)
        log.close()
    return uids


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", required=True, help="Vault 目录（会被清空重建）")
    ap.add_argument("--profile", choices=["full", "empty"], default="full")
    ap.add_argument("--seed", type=int, default=7)
    args = ap.parse_args(argv)
    vault = os.path.abspath(args.out)
    if os.path.isdir(vault):
        shutil.rmtree(vault)
    os.makedirs(os.path.join(vault, "错题"))
    if args.profile == "full":
        uids = build_full(vault, args.seed)
        print(f"已生成 full Vault：{vault}（{len(uids)} 题）")
    else:
        print(f"已生成 empty Vault：{vault}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

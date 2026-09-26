"""设计 token 对比度门禁：从 assets/app/styles/tokens.css 解析浅色与深色语义 token，按 WCAG 2.x 计算对比度。

    python3 tests/check_contrast.py          # 不达标退出码 1
    python3 tests/check_contrast.py --table  # 打印全部组合

规则（PAIRS）：文字对 4.5:1；辅助文字压在 surface-2 上、焦点环这类图形对 3:1。
半透明背景先与它所在的表面（surface-1）合成，再算对比度。
"""
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOKENS = os.path.join(ROOT, "assets", "app", "styles", "tokens.css")

TEXT, GRAPHIC = 4.5, 3.0
# (前景, 背景, 阈值)。背景带透明度时合成在 surface-1 上。
PAIRS = [
    *[(fg, bg, TEXT) for fg in ("fg-1", "fg-2", "fg-3") for bg in ("surface-0", "surface-1")],
    ("fg-1", "surface-2", TEXT), ("fg-2", "surface-2", TEXT), ("fg-3", "surface-2", GRAPHIC),
    ("on-accent", "accent", TEXT), ("on-accent", "accent-hover", TEXT),
    ("on-accent", "danger", TEXT),      # v1.20.0：危险按钮悬停 / 按下（ui/button.css、legacy-bridge .btn.danger）
    ("fg-1", "accent-soft", TEXT),      # v1.20.0：表格选中行、标签 accent 色调
    *[(s, bg, TEXT) for s in ("danger", "success", "warning", "info") for bg in ("surface-0", "surface-1")],
    ("danger-fg", "danger-soft", TEXT), ("success-fg", "success-soft", TEXT),
    ("warning-fg", "warning-soft", TEXT), ("info-fg", "info-soft", TEXT),
    ("focus-ring", "surface-1", GRAPHIC), ("focus-ring", "surface-0", GRAPHIC),
    ("fg-1", "surface-sunken", TEXT), ("fg-2", "surface-sunken", TEXT),   # v1.24.2：题面块（qview 的 .q-md）上的正文与次文字
]

BLOCK_RE = re.compile(r"(:root|\[data-theme=\"dark\"\])\s*\{([^{}]*)\}")
DECL_RE = re.compile(r"--([\w-]+)\s*:\s*([^;]+?)\s*(?:;|$)")


def parse(css):
    """返回 {'light': {...}, 'dark': {...}}；深色 = 浅色被 [data-theme=dark] 覆盖后的结果。"""
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    css = re.sub(r"@media[^{]*\{(?:[^{}]*\{[^{}]*\})*[^{}]*\}", "", css)  # 忽略媒体查询里的覆盖
    light, dark_only = {}, {}
    for sel, body in BLOCK_RE.findall(css):
        target = light if sel == ":root" else dark_only
        for name, value in DECL_RE.findall(body):
            target[name] = value.strip()
    return {"light": dict(light), "dark": {**light, **dark_only}}


def resolve(tokens, name, depth=0):
    value = tokens[name]
    m = re.fullmatch(r"var\(--([\w-]+)\)", value)
    if m and depth < 10:
        return resolve(tokens, m.group(1), depth + 1)
    return value


def to_rgba(value):
    value = value.strip()
    m = re.fullmatch(r"#([0-9a-fA-F]{3}|[0-9a-fA-F]{6})", value)
    if m:
        h = m.group(1)
        if len(h) == 3:
            h = "".join(c * 2 for c in h)
        return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4)) + (1.0,)
    m = re.fullmatch(r"rgba?\(([^)]*)\)", value)
    if m:
        parts = [p.strip() for p in m.group(1).split(",")]
        rgb = tuple(float(p) for p in parts[:3])
        alpha = float(parts[3]) if len(parts) > 3 else 1.0
        return rgb + (alpha,)
    raise ValueError(f"无法解析颜色：{value}")


def over(top, base):
    a = top[3]
    return tuple(top[i] * a + base[i] * (1 - a) for i in range(3)) + (1.0,)


def luminance(rgb):
    def ch(c):
        c /= 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (ch(c) for c in rgb[:3])
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def ratio(a, b):
    la, lb = luminance(a), luminance(b)
    return (max(la, lb) + 0.05) / (min(la, lb) + 0.05)


def evaluate(css):
    rows = []
    for theme, tokens in parse(css).items():
        surface = to_rgba(resolve(tokens, "surface-1"))
        for fg, bg, need in PAIRS:
            back = to_rgba(resolve(tokens, bg))
            if back[3] < 1:
                back = over(back, surface)
            front = over(to_rgba(resolve(tokens, fg)), back)
            value = ratio(front, back)
            rows.append((theme, fg, bg, round(value, 2), need, value + 1e-9 >= need))
    return rows


def main(argv):
    rows = evaluate(open(TOKENS, encoding="utf-8").read())
    bad = [r for r in rows if not r[5]]
    if "--table" in argv or bad:
        for theme, fg, bg, value, need, ok in rows:
            if "--table" in argv or not ok:
                print(f"{'OK ' if ok else '不达标'} {theme:5} {fg:>11} / {bg:<12} {value:5.2f}（需 {need}）")
    print(f"检查 {len(rows)} 组对比度，{len(bad)} 组不达标")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

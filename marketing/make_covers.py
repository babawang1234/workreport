"""生成 3 张抖音竖版封面（1080x1440），纯本地绘制，文字清晰不乱码。"""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

OUT = Path(r"C:\Users\lixiaofan\Documents\Trae-CN\temp_20261116_01\marketing\covers")
OUT.mkdir(parents=True, exist_ok=True)

W, H = 1080, 1440
BOLD = r"C:\Windows\Fonts\msyhbd.ttc"
REG = r"C:\Windows\Fonts\msyh.ttc"


def font(size, bold=True):
    return ImageFont.truetype(BOLD if bold else REG, size)


def bg():
    """深色渐变 + 两团柔光"""
    base = Image.new("RGB", (W, H), (9, 12, 28))
    top = (18, 22, 52)
    bottom = (10, 12, 26)
    px = base.load()
    for y in range(H):
        t = y / H
        c = tuple(int(top[i] + (bottom[i] - top[i]) * t) for i in range(3))
        for x in range(W):
            px[x, y] = c
    glow = Image.new("RGB", (W, H), (0, 0, 0))
    gd = ImageDraw.Draw(glow)
    gd.ellipse([-260, -220, 620, 520], fill=(70, 56, 190))
    gd.ellipse([520, 900, 1280, 1560], fill=(20, 110, 130))
    glow = glow.filter(ImageFilter.GaussianBlur(180))
    base = Image.blend(base, Image.blend(base, glow, 0.55), 0.75)
    return base


def wrap(draw, text, f, max_w):
    lines, cur = [], ""
    for ch in text:
        if ch == "\n":
            lines.append(cur)
            cur = ""
            continue
        if draw.textlength(cur + ch, font=f) > max_w:
            lines.append(cur)
            cur = ch
        else:
            cur += ch
    if cur:
        lines.append(cur)
    return lines


def badge(draw, x, y, text, f, fill=(124, 108, 255), pad=(26, 14)):
    w = draw.textlength(text, font=f)
    box = [x, y, x + w + pad[0] * 2, y + f.size + pad[1] * 2]
    draw.rounded_rectangle(box, radius=(box[3] - box[1]) // 2, fill=fill)
    draw.text((x + pad[0], y + pad[1] - 2), text, font=f, fill=(255, 255, 255))
    return box


def cover1():
    img = bg()
    d = ImageDraw.Draw(img)
    badge(d, 80, 110, "智报 · AI 工作汇报", font(34))
    d.text((80, 300), "周报别再", font=font(126), fill=(255, 255, 255))
    d.text((80, 460), "熬夜写了", font=font(126), fill=(150, 140, 255))
    d.text((80, 700), "粘贴聊天记录、待办、随手记", font=font(46, False), fill=(196, 202, 226))
    d.text((80, 780), "20 秒出可直接提交的成稿", font=font(46, False), fill=(196, 202, 226))
    # 底部模块条
    y = 930
    for t in ["成果", "问题", "计划", "支持"]:
        f = font(40)
        w = d.textlength(t, font=f)
        d.rounded_rectangle([80, y, 80 + w + 60, y + 86], radius=22, fill=(34, 34, 60), outline=(124, 108, 255), width=2)
        d.text((80 + 30, y + 19), t, font=f, fill=(230, 232, 245))
        y += 100
    d.text((80, 1345), "zhibaozb.top", font=font(32, False), fill=(130, 138, 170))
    return img


def cover2():
    img = bg()
    d = ImageDraw.Draw(img)
    badge(d, 80, 110, "同一份工作 · 两种写法", font(34), fill=(38, 150, 170))
    d.text((80, 270), "领导只看", font=font(112), fill=(255, 255, 255))
    d.text((80, 410), "右边那种", font=font(112), fill=(150, 140, 255))
    # 左卡：流水账
    d.rounded_rectangle([80, 620, 500, 1180], radius=32, fill=(24, 26, 44), outline=(70, 74, 100), width=2)
    d.text((112, 660), "流水账", font=font(48), fill=(150, 156, 180))
    for i, t in enumerate(["周一开会", "周二改稿", "周三对接", "周四又改"]):
        d.text((112, 760 + i * 90), t, font=font(40, False), fill=(120, 126, 150))
    d.line([112, 1150, 400, 1150], fill=(200, 80, 90), width=6)
    # 右卡：四模块
    d.rounded_rectangle([560, 620, 1000, 1180], radius=32, fill=(30, 28, 62), outline=(130, 118, 255), width=3)
    d.text((592, 660), "四模块", font=font(48), fill=(180, 172, 255))
    for i, t in enumerate(["上线转化 +12%", "风险已同步", "下周三条计划", "需要 1 人力"]):
        ty = 760 + i * 90
        # 手绘对勾，避免字体缺字
        d.line([596, ty + 26, 610, ty + 40], fill=(124, 220, 180), width=6)
        d.line([610, ty + 40, 634, ty + 4], fill=(124, 220, 180), width=6)
        d.text((660, ty), t, font=font(38, False), fill=(226, 228, 245))
    d.text((80, 1260), "智报 · 粘碎片，20 秒出成稿", font=font(44), fill=(206, 210, 236))
    return img


def cover3():
    img = bg()
    d = ImageDraw.Draw(img)
    badge(d, 80, 110, "周报模板 · 直接套用", font(34), fill=(206, 120, 40))
    d.text((80, 290), "周报只写", font=font(124), fill=(255, 255, 255))
    d.text((80, 440), "这 4 块", font=font(124), fill=(150, 140, 255))
    items = [
        ("1", "本周成果", "做完的事 + 数据结果"),
        ("2", "问题与风险", "卡点、影响、已试方案"),
        ("3", "下周计划", "3–5 条，有交付物"),
        ("4", "需要的支持", "要谁配合，一次说清"),
    ]
    y = 640
    for num, title, desc in items:
        d.rounded_rectangle([80, y, 1000, y + 150], radius=28, fill=(26, 28, 48), outline=(70, 66, 120), width=2)
        d.ellipse([116, y + 44, 178, y + 106], fill=(124, 108, 255))
        nf = font(36)
        d.text((138, y + 58), num, font=nf, fill=(255, 255, 255))
        d.text((206, y + 34), title, font=font(48), fill=(255, 255, 255))
        d.text((206, y + 98), desc, font=font(34, False), fill=(168, 174, 200))
        y += 170
    d.text((80, 1350), "智报 · AI 周报 20 秒出稿", font=font(36, False), fill=(140, 146, 176))
    return img


for i, fn in enumerate([cover1, cover2, cover3], 1):
    path = OUT / f"cover{i}.png"
    fn().save(path, quality=95)
    print(path)

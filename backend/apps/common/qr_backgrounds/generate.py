"""Re-creates the bundled QR backgrounds (brand #1464BA / #11AB53).

    python apps/common/qr_backgrounds/generate.py      (Pillow only, deterministic)

The JPEGs next to this file are the shipped assets; run this only to change them.
"""
import math
import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

S = 1080
HERE = Path(__file__).resolve().parent
BLUE, GREEN = (20, 100, 186), (17, 171, 83)


def lerp(a, b, t):
    return tuple(round(x + (y - x) * t) for x, y in zip(a, b))


def gradient(c1, c2, angle=135):
    """Linear gradient across the square at `angle` degrees."""
    g = Image.linear_gradient("L").resize((S * 2, S * 2)).rotate(angle - 90, resample=Image.BICUBIC)
    g = g.crop((S // 2, S // 2, S // 2 + S, S // 2 + S))
    return Image.composite(Image.new("RGB", (S, S), c2), Image.new("RGB", (S, S), c1), g)


def glow(img, xy, r, color, alpha, blur):
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    x, y = xy
    d.ellipse((x - r, y - r, x + r, y + r), fill=color + (alpha,))
    layer = layer.filter(ImageFilter.GaussianBlur(blur))
    return Image.alpha_composite(img.convert("RGBA"), layer)


def lines_layer(draw_fn, blur=0):
    layer = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    draw_fn(ImageDraw.Draw(layer))
    return layer.filter(ImageFilter.GaussianBlur(blur)) if blur else layer


def caspian_light():
    img = gradient((246, 250, 255), (226, 238, 252), 120)
    img = glow(img, (180, 170), 300, BLUE, 70, 120)
    img = glow(img, (930, 940), 320, GREEN, 60, 130)
    def waves(d):
        for k in range(7):
            pts = [(x, 860 + k * 26 + 40 * math.sin(x / 140 + k * .5)) for x in range(-20, S + 21, 12)]
            d.line(pts, fill=BLUE + (36,), width=3)
    return Image.alpha_composite(img, lines_layer(waves))


def caspian_dark():
    img = gradient((8, 22, 44), (14, 46, 88), 135)
    img = glow(img, (160, 200), 320, BLUE, 150, 140)
    img = glow(img, (960, 900), 300, GREEN, 120, 140)
    def waves(d):
        for k in range(8):
            pts = [(x, 120 + k * 22 + 34 * math.sin(x / 160 + k * .6)) for x in range(-20, S + 21, 12)]
            d.line(pts, fill=(140, 190, 245, 40), width=2)
    return Image.alpha_composite(img, lines_layer(waves))


def ocean_waves():
    img = gradient(BLUE, (9, 58, 120), 160).convert("RGBA")
    def waves(d):
        for k in range(22):
            y0 = 40 + k * 48
            pts = [(x, y0 + 26 * math.sin(x / 110 + k * .9) + 12 * math.sin(x / 47 + k)) for x in range(-20, S + 21, 10)]
            d.line(pts, fill=(255, 255, 255, 22 + (k % 3) * 10), width=2)
    img = Image.alpha_composite(img, lines_layer(waves))
    return glow(img, (S // 2, S + 80), 420, GREEN, 90, 160)


def geometric_green():
    img = gradient(GREEN, (6, 96, 52), 45).convert("RGBA")
    rnd = random.Random(7)
    def tris(d):
        step = 90
        for row in range(-1, S // step + 2):
            for col in range(-1, S // step + 2):
                x, y = col * step + (step // 2 if row % 2 else 0), row * step * 0.87
                a = rnd.choice((0, 0, 10, 18, 28))
                if a:
                    d.polygon([(x, y), (x + step, y), (x + step / 2, y + step * .87)], fill=(255, 255, 255, a))
                d.line([(x, y), (x + step, y), (x + step / 2, y + step * .87), (x, y)], fill=(255, 255, 255, 26), width=1)
    img = Image.alpha_composite(img, lines_layer(tris))
    return glow(img, (S - 120, 140), 280, BLUE, 110, 150)


def network():
    img = gradient((6, 18, 36), (10, 34, 66), 150).convert("RGBA")
    rnd = random.Random(11)
    pts = [(rnd.randint(-40, S + 40), rnd.randint(-40, S + 40)) for _ in range(90)]
    def net(d):
        for i, a in enumerate(pts):
            for b in pts[i + 1:]:
                dist = math.dist(a, b)
                if dist < 170:
                    col = BLUE if (a[0] + b[1]) % 2 else GREEN
                    d.line([a, b], fill=col + (int(120 * (1 - dist / 170)),), width=2)
        for i, (x, y) in enumerate(pts):
            r = 4 + i % 4
            d.ellipse((x - r, y - r, x + r, y + r), fill=(GREEN if i % 3 == 0 else (110, 170, 240)) + (210,))
    img = Image.alpha_composite(img, lines_layer(net, blur=0.6))
    img = glow(img, (S // 2, S // 2), 360, BLUE, 60, 160)
    return img


def aurora():
    img = gradient((10, 40, 90), (8, 90, 70), 120).convert("RGBA")
    def bands(d):
        for k, col in enumerate((BLUE, GREEN, (90, 180, 255), GREEN)):
            pts = [(x, 260 + k * 150 + 110 * math.sin(x / 210 + k * 1.3)) for x in range(-40, S + 41, 12)]
            d.line(pts, fill=col + (150,), width=70)
    img = Image.alpha_composite(img, lines_layer(bands, blur=55))
    return glow(img, (S - 200, 200), 220, (255, 255, 255), 30, 120)


BUILT_IN = {
    "caspian-light": caspian_light, "caspian-dark": caspian_dark, "ocean-waves": ocean_waves,
    "geometric-green": geometric_green, "network": network, "aurora": aurora,
}

if __name__ == "__main__":
    for key, fn in BUILT_IN.items():
        fn().convert("RGB").save(HERE / f"{key}.jpg", quality=88, optimize=True, progressive=True)
        print(key, (HERE / f"{key}.jpg").stat().st_size)

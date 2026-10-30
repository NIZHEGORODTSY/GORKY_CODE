"""Рисует аватар бота: календарный лист со звуковой волной на градиенте.

Запуск: python -m scripts.make_avatar  ->  assets/avatar.jpg (640x640, JPG для setMyProfilePhoto)
"""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

SIZE = 640
SCALE = 3  # рисуем крупнее и уменьшаем — сглаживание краёв
OUT = Path(__file__).resolve().parent.parent / "assets" / "avatar.jpg"


def gradient(size: int, top: tuple, bottom: tuple) -> Image.Image:
    img = Image.new("RGB", (size, size))
    draw = ImageDraw.Draw(img)
    for y in range(size):
        t = y / (size - 1)
        color = tuple(round(a + (b - a) * t) for a, b in zip(top, bottom))
        draw.line([(0, y), (size, y)], fill=color)
    return img


def main() -> None:
    s = SIZE * SCALE
    img = gradient(s, (79, 70, 229), (147, 51, 234))  # индиго -> фиолетовый

    # Тень под листом
    shadow = Image.new("L", (s, s), 0)
    sd = ImageDraw.Draw(shadow)
    box = (int(s * 0.22), int(s * 0.24), int(s * 0.78), int(s * 0.80))
    sd.rounded_rectangle((box[0], box[1] + s // 40, box[2], box[3] + s // 40), radius=s // 12, fill=110)
    shadow = shadow.filter(ImageFilter.GaussianBlur(s // 50))
    img.paste((40, 20, 90), mask=shadow)

    d = ImageDraw.Draw(img)
    # Лист календаря
    d.rounded_rectangle(box, radius=s // 12, fill=(255, 255, 255))
    header_bottom = box[1] + int(s * 0.13)
    d.rounded_rectangle((box[0], box[1], box[2], header_bottom), radius=s // 12, fill=(255, 94, 98))
    d.rectangle((box[0], header_bottom - s // 12, box[2], header_bottom), fill=(255, 94, 98))
    # Кольца
    for x in (0.36, 0.64):
        cx = int(s * x)
        d.rounded_rectangle((cx - s // 60, box[1] - s // 30, cx + s // 60, box[1] + s // 25), radius=s // 60, fill=(55, 48, 163))

    # Звуковая волна
    heights = [0.10, 0.20, 0.32, 0.20, 0.28, 0.14, 0.08]
    bar_w = int(s * 0.045)
    gap = int(s * 0.025)
    total = len(heights) * bar_w + (len(heights) - 1) * gap
    x = (s - total) // 2
    cy = (header_bottom + box[3]) // 2
    for h in heights:
        half = int(s * h / 2)
        d.rounded_rectangle((x, cy - half, x + bar_w, cy + half), radius=bar_w // 2, fill=(79, 70, 229))
        x += bar_w + gap

    OUT.parent.mkdir(exist_ok=True)
    img.resize((SIZE, SIZE), Image.LANCZOS).save(OUT, "JPEG", quality=92)
    print(OUT)


if __name__ == "__main__":
    main()

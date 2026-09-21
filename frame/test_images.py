from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

REPO_ROOT = Path(__file__).resolve().parents[1]
TEST_IMAGE_DIR = REPO_ROOT / "assets" / "test"
MEDIA_VERSION = "gif-v1"
FRAME_COUNT = 12


@dataclass(frozen=True)
class TestScene:
    stem: str
    title: str
    orientation: str
    top: tuple[int, int, int]
    bottom: tuple[int, int, int]


SCENES: tuple[TestScene, ...] = (
    TestScene("01-harbor", "Harbor", "landscape", (8, 36, 72), (46, 150, 168)),
    TestScene("02-forest", "Forest", "landscape", (10, 42, 22), (78, 140, 48)),
    TestScene("03-desert", "Desert", "landscape", (92, 48, 18), (214, 168, 84)),
    TestScene("04-night", "Night", "landscape", (6, 8, 28), (38, 42, 92)),
    TestScene("05-meadow", "Meadow", "landscape", (36, 92, 40), (186, 210, 96)),
    TestScene("06-canyon", "Canyon", "landscape", (78, 28, 18), (176, 86, 42)),
    TestScene("07-window", "Window", "portrait", (40, 28, 18), (186, 132, 72)),
    TestScene("08-statue", "Statue", "portrait", (24, 28, 40), (118, 128, 148)),
)


def ensure_test_images(directory: Path = TEST_IMAGE_DIR) -> list[tuple[Path, Path, TestScene]]:
    directory.mkdir(parents=True, exist_ok=True)
    marker = directory / ".media-version"
    stale = True
    if marker.exists():
        stale = marker.read_text().strip() != MEDIA_VERSION
    if stale:
        for stale in directory.glob("*"):
            if stale.name != ".media-version":
                stale.unlink()
    media: list[tuple[Path, Path, TestScene]] = []
    for index, scene in enumerate(SCENES, start=1):
        gif = directory / f"{scene.stem}.gif"
        still = directory / f"{scene.stem}-still.jpg"
        if not gif.exists() or not still.exists():
            _render_scene(gif, still, scene, index)
        media.append((still, gif, scene))
    marker.write_text(MEDIA_VERSION + "\n")
    return media


def _render_scene(gif_path: Path, still_path: Path, scene: TestScene, number: int) -> None:
    if scene.orientation == "portrait":
        width, height = 540, 960
        still_size = (1080, 1920)
    else:
        width, height = 960, 540
        still_size = (1920, 1080)
    base = _gradient(width, height, scene.top, scene.bottom)
    frames: list[Image.Image] = []
    for tick in range(FRAME_COUNT):
        frame = base.copy()
        draw = ImageDraw.Draw(frame, "RGBA")
        _draw_motion(draw, scene, width, height, tick)
        _draw_labels(draw, scene, number, width, height)
        frames.append(frame.convert("P", palette=Image.ADAPTIVE, colors=128))
    frames[0].save(
        gif_path,
        save_all=True,
        append_images=frames[1:],
        duration=90,
        loop=0,
        disposal=2,
    )
    still = _gradient(*still_size, scene.top, scene.bottom)
    still_draw = ImageDraw.Draw(still, "RGBA")
    _draw_motion(still_draw, scene, still_size[0], still_size[1], 0)
    _draw_labels(still_draw, scene, number, still_size[0], still_size[1], still=True)
    still.convert("RGB").save(still_path, quality=90)


def _gradient(width: int, height: int, top: tuple[int, int, int], bottom: tuple[int, int, int]) -> Image.Image:
    image = Image.new("RGB", (width, height), top)
    pixels = image.load()
    for y in range(height):
        t = y / max(1, height - 1)
        color = tuple(int(top[i] * (1 - t) + bottom[i] * t) for i in range(3))
        for x in range(width):
            pixels[x, y] = color
    return image


def _draw_motion(
    draw: ImageDraw.ImageDraw,
    scene: TestScene,
    width: int,
    height: int,
    tick: int,
) -> None:
    phase = tick / max(1, FRAME_COUNT - 1)
    shift = int((phase - 0.5) * width * 0.22)
    bounce = int(abs(phase - 0.5) * height * 0.18)
    name = scene.title.lower()
    if name == "harbor":
        for i in range(7):
            x = 80 + i * int(width / 7) + shift
            y = int(height * 0.58) + (i % 3) * 18
            draw.ellipse((x, y, x + int(width * 0.1), y + int(height * 0.08)), fill=(255, 255, 255, 70))
    elif name == "forest":
        for i in range(10):
            x = 40 + i * int(width / 10) + (shift // 3)
            draw.rectangle((x, int(height * 0.22) + bounce // 4, x + 28, height), fill=(6, 24, 10, 110))
    elif name == "desert":
        cx = int(width * 0.72) + shift // 2
        cy = int(height * 0.22) + bounce
        r = int(width * 0.08)
        draw.ellipse((cx - r, cy - r, cx + r, cy + r), fill=(255, 210, 80, 140))
    elif name == "night":
        for i in range(28):
            x = (i * 97 + tick * 17) % width
            y = (i * 53) % int(height * 0.7)
            r = 2 + ((i + tick) % 5)
            draw.ellipse((x, y, x + r, y + r), fill=(255, 255, 255, 200))
    elif name == "meadow":
        cx = int(width * 0.78)
        cy = int(height * 0.18) + bounce
        r = int(width * 0.1)
        draw.ellipse((cx - r, cy - r, cx + r, cy + r), fill=(255, 220, 70, 150))
    elif name == "canyon":
        x = int(width * 0.2) + shift
        draw.polygon(
            [(x, height), (x + int(width * 0.22), int(height * 0.38)), (x + int(width * 0.48), height)],
            fill=(40, 12, 8, 90),
        )
    elif name == "window":
        pad = 70 + bounce // 2
        draw.rectangle((pad, pad + 80, width - pad, height - pad), outline=(255, 255, 255, 120), width=14)
    elif name == "statue":
        top = 180 + bounce
        draw.rounded_rectangle(
            (int(width * 0.3), top, int(width * 0.7), height - 140),
            radius=60,
            fill=(255, 255, 255, 40),
        )


def _draw_labels(
    draw: ImageDraw.ImageDraw,
    scene: TestScene,
    number: int,
    width: int,
    height: int,
    still: bool = False,
) -> None:
    font_lg = _font(int(height * 0.18) if still else int(height * 0.16))
    font_sm = _font(int(height * 0.055))
    draw.text((int(width * 0.06), int(height * 0.05)), f"{number:02d}", font=font_lg, fill=(255, 255, 255, 230))
    draw.text((int(width * 0.06), height - int(height * 0.16)), scene.title, font=font_sm, fill=(255, 255, 255, 230))
    hint = "still" if still else "gif"
    draw.text(
        (int(width * 0.06), height - int(height * 0.09)),
        f"{scene.orientation} · {hint}",
        font=_font(int(height * 0.035)),
        fill=(255, 255, 255, 160),
    )


def _font(size: int) -> ImageFont.ImageFont:
    for name in ("Helvetica.ttc", "Arial.ttf", "DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(name, size=max(12, size))
        except OSError:
            continue
    return ImageFont.load_default()

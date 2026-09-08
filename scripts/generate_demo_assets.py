#!/usr/bin/env python3
"""Build sanitized README demo assets from original, text-free backgrounds."""

from __future__ import annotations

import argparse
import math
import os
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIR = ROOT / "docs" / "assets"
SOCIAL_SIZE = (1280, 640)
DEMO_SIZE = (960, 540)
DEMO_FRAME_COUNT = 25
DEMO_FRAME_MS = 1000

NAVY = "#0B1739"
CYAN = "#67E8F9"
GREEN = "#22C55E"
WHITE = "#F8FAFC"
SLATE = "#A8BED8"
MUTED = "#7891AE"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate the fictional demo GIF and GitHub social preview."
    )
    parser.add_argument(
        "--social-source",
        required=True,
        type=Path,
        help="Text-free source artwork for the social preview.",
    )
    parser.add_argument(
        "--demo-source",
        required=True,
        type=Path,
        help="Text-free source artwork for the animated demo.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Output directory. Defaults to docs/assets in this repository.",
    )
    return parser.parse_args()


def load_source(path: Path, size: tuple[int, int]) -> Image.Image:
    if not path.is_file():
        raise FileNotFoundError(f"Missing source artwork: {path}")
    with Image.open(path) as image:
        if image.width < 800 or image.height < 400:
            raise ValueError(f"Source artwork is too small: {path}")
        return ImageOps.fit(
            image.convert("RGB"),
            size,
            method=Image.Resampling.LANCZOS,
            centering=(0.5, 0.5),
        )


def font_candidates(*, bold: bool, mono: bool) -> list[Path]:
    windows = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"
    if mono:
        names = ("CascadiaMono.ttf", "consola.ttf", "DejaVuSansMono.ttf")
    elif bold:
        names = ("seguisb.ttf", "arialbd.ttf", "DejaVuSans-Bold.ttf")
    else:
        names = ("segoeui.ttf", "arial.ttf", "DejaVuSans.ttf")
    roots = (
        windows,
        Path("/System/Library/Fonts/Supplemental"),
        Path("/usr/share/fonts/truetype/dejavu"),
    )
    return [root / name for root in roots for name in names]


def load_font(size: int, *, bold: bool = False, mono: bool = False) -> ImageFont.ImageFont:
    for candidate in font_candidates(bold=bold, mono=mono):
        if candidate.is_file():
            return ImageFont.truetype(str(candidate), size=size)
    return ImageFont.load_default()


def rounded_label(
    draw: ImageDraw.ImageDraw,
    box: tuple[int, int, int, int],
    text: str,
    *,
    fill: str,
    text_fill: str = WHITE,
    font_size: int = 20,
) -> None:
    draw.rounded_rectangle(box, radius=(box[3] - box[1]) // 2, fill=fill)
    font = load_font(font_size, bold=True)
    draw.text(
        ((box[0] + box[2]) / 2, (box[1] + box[3]) / 2),
        text,
        font=font,
        fill=text_fill,
        anchor="mm",
    )


def left_gradient(size: tuple[int, int], maximum_alpha: int) -> Image.Image:
    width, height = size
    overlay = Image.new("RGBA", size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    fade_end = int(width * 0.66)
    for x in range(fade_end):
        ratio = 1.0 - (x / fade_end)
        alpha = int(maximum_alpha * ratio * ratio)
        draw.line((x, 0, x, height), fill=(3, 10, 25, alpha))
    return overlay


def build_social_preview(source: Path, destination: Path) -> None:
    image = load_source(source, SOCIAL_SIZE).convert("RGBA")
    image.alpha_composite(left_gradient(SOCIAL_SIZE, maximum_alpha=238))
    draw = ImageDraw.Draw(image)

    rounded_label(
        draw,
        (72, 62, 314, 104),
        "YUAN SAYS AI",
        fill="#0E7490",
        font_size=19,
    )
    draw.text((72, 160), "AUDIO DOWNLOAD", font=load_font(62, bold=True), fill=WHITE)
    draw.text((72, 226), "SKILLS", font=load_font(62, bold=True), fill=CYAN)
    draw.text(
        (76, 318),
        "Explicit intent. Source codec. Verified output.",
        font=load_font(25),
        fill=SLATE,
    )

    labels = (
        ("EXPLICIT INTENT", "#164E63"),
        ("SOURCE CODEC", "#14532D"),
        ("FFPROBE VERIFIED", "#1E3A5F"),
    )
    x = 72
    for label, color in labels:
        label_width = int(load_font(16, bold=True).getlength(label)) + 34
        rounded_label(
            draw,
            (x, 388, x + label_width, 424),
            label,
            fill=color,
            font_size=16,
        )
        x += label_width + 14

    draw.line((72, 514, 570, 514), fill="#2A4E72", width=2)
    draw.text(
        (72, 544),
        "CODEX PLUGIN  /  v0.1.0",
        font=load_font(20, bold=True, mono=True),
        fill=GREEN,
    )
    draw.text(
        (72, 582),
        "One authorized video per request. No bypasses.",
        font=load_font(18),
        fill=MUTED,
    )

    destination.parent.mkdir(parents=True, exist_ok=True)
    image.convert("RGB").save(destination, format="PNG", optimize=True, compress_level=9)


SCENES = (
    {
        "start": 0,
        "stage": 0,
        "title": "EXPLICIT REQUEST",
        "lines": (
            ("> download audio from my own demo clip", WHITE),
            ("intent: explicit", GREEN),
            ("scope: one published video", SLATE),
        ),
    },
    {
        "start": 5,
        "stage": 1,
        "title": "NARROW ROUTING",
        "lines": (
            ("skill: download-youtube-audio", CYAN),
            ("request: authorized fictional fixture", SLATE),
            ("network: simulated", GREEN),
        ),
    },
    {
        "start": 10,
        "stage": 2,
        "title": "SOURCE-AWARE EXTRACTION",
        "lines": (
            ("select: best available audio", WHITE),
            ("source codec: opus", CYAN),
            ("transcoded: false", GREEN),
        ),
    },
    {
        "start": 16,
        "stage": 3,
        "title": "FFPROBE VERIFICATION",
        "lines": (
            ("audio_streams: 1", GREEN),
            ("video_streams: 0", GREEN),
            ("status: downloaded", WHITE),
        ),
    },
    {
        "start": 21,
        "stage": 3,
        "title": "SAFE RESULT",
        "lines": (
            ("file: demo-audio.opus", CYAN),
            ("source_codec_preserved: true", GREEN),
            ("done - no real media was used", WHITE),
        ),
    },
)


def current_scene(second: int) -> dict[str, object]:
    scene = SCENES[0]
    for candidate in SCENES:
        if second >= int(candidate["start"]):
            scene = candidate
    return scene


def build_demo_frame(base: Image.Image, second: int) -> Image.Image:
    image = base.copy().convert("RGBA")
    draw = ImageDraw.Draw(image)
    scene = current_scene(second)
    active_stage = int(scene["stage"])

    draw.rounded_rectangle((20, 42, 670, 445), radius=16, fill=(3, 10, 25, 188))
    draw.text((50, 20), "YUAN SAYS AI", font=load_font(18, bold=True), fill=CYAN)
    draw.text(
        (920, 20),
        "FICTIONAL  /  NO NETWORK",
        font=load_font(14, bold=True, mono=True),
        fill=GREEN,
        anchor="ra",
    )

    draw.text((54, 78), str(scene["title"]), font=load_font(24, bold=True), fill=WHITE)
    draw.line((54, 119, 630, 119), fill="#294C70", width=2)

    prompt_font = load_font(21, mono=True)
    y = 158
    for line, color in scene["lines"]:  # type: ignore[misc]
        draw.text((57, y), str(line), font=prompt_font, fill=str(color))
        y += 51

    cursor_visible = second % 2 == 0
    if cursor_visible:
        draw.rectangle((57, y + 6, 70, y + 29), fill=CYAN)

    stage_labels = ("INTENT", "ROUTE", "SOURCE", "VERIFY")
    stage_y = (105, 207, 310, 414)
    for index, (label, y_pos) in enumerate(zip(stage_labels, stage_y)):
        complete = index <= active_stage
        color = GREEN if complete else MUTED
        draw.ellipse((690, y_pos - 12, 714, y_pos + 12), fill=color)
        draw.text(
            (744, y_pos),
            label,
            font=load_font(16, bold=True),
            fill=WHITE if complete else MUTED,
            anchor="lm",
        )

    progress = (second + 1) / DEMO_FRAME_COUNT
    draw.rounded_rectangle((54, 406, 630, 416), radius=5, fill="#18334F")
    draw.rounded_rectangle(
        (54, 406, 54 + int(576 * progress), 416),
        radius=5,
        fill=GREEN,
    )

    for index in range(42):
        x = 55 + index * 14
        amplitude = 5 + int(10 * abs(math.sin((second * 0.8) + (index * 0.42))))
        draw.line((x, 462 - amplitude, x, 462 + amplitude), fill=CYAN, width=3)

    draw.text(
        (480, 512),
        "SIMULATED OUTPUT  /  NO REAL URL  /  NO CREDENTIALS  /  NO MEDIA",
        font=load_font(14, bold=True, mono=True),
        fill=SLATE,
        anchor="mm",
    )
    return image.convert("RGB")


def build_demo_gif(source: Path, destination: Path) -> None:
    base = load_source(source, DEMO_SIZE)
    frames = [build_demo_frame(base, second) for second in range(DEMO_FRAME_COUNT)]
    paletted = [
        frame.convert("P", palette=Image.Palette.ADAPTIVE, colors=128)
        for frame in frames
    ]
    destination.parent.mkdir(parents=True, exist_ok=True)
    paletted[0].save(
        destination,
        format="GIF",
        save_all=True,
        append_images=paletted[1:],
        duration=DEMO_FRAME_MS,
        loop=0,
        optimize=True,
        disposal=2,
    )


def verify_outputs(social_path: Path, demo_path: Path) -> None:
    with Image.open(social_path) as social:
        if social.size != SOCIAL_SIZE or social.format != "PNG":
            raise RuntimeError("Social preview dimensions or format are incorrect")
    with Image.open(demo_path) as demo:
        frame_count = getattr(demo, "n_frames", 1)
        total_ms = sum(
            int(demo.seek(index) or demo.info.get("duration", 0))
            for index in range(frame_count)
        )
        if demo.size != DEMO_SIZE or demo.format != "GIF":
            raise RuntimeError("Demo dimensions or format are incorrect")
        if frame_count != DEMO_FRAME_COUNT or not 20_000 <= total_ms <= 30_000:
            raise RuntimeError("Demo must contain 20-30 seconds of animation")


def main() -> int:
    args = parse_args()
    output_dir = args.output_dir.resolve()
    social_path = output_dir / "social-preview.png"
    demo_path = output_dir / "demo.gif"
    build_social_preview(args.social_source.resolve(), social_path)
    build_demo_gif(args.demo_source.resolve(), demo_path)
    verify_outputs(social_path, demo_path)
    print(f"Generated {social_path}")
    print(f"Generated {demo_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

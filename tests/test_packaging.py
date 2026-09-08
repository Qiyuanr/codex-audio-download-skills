from __future__ import annotations

import base64
import json
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "plugins" / "codex-audio-download-skills"
SKILLS = PLUGIN / "skills"
SITE_SKILLS = {
    "download-bilibili-audio": "Bilibili",
    "download-douyin-audio": "Douyin",
    "download-youtube-audio": "YouTube",
}
TEXT_SUFFIXES = {"", ".json", ".md", ".py", ".svg", ".yaml", ".yml"}
MEDIA_SUFFIXES = {
    ".mp3",
    ".m4a",
    ".aac",
    ".opus",
    ".ogg",
    ".webm",
    ".mp4",
    ".mkv",
    ".mov",
    ".flac",
    ".wav",
}


def gif_summary(data: bytes) -> tuple[int, int, int, int]:
    """Return logical width, height, frame count, and total duration in ms."""
    if data[:6] not in {b"GIF87a", b"GIF89a"}:
        raise ValueError("not a GIF")
    width, height = struct.unpack("<HH", data[6:10])
    offset = 13
    packed = data[10]
    if packed & 0x80:
        offset += 3 * (2 ** ((packed & 0x07) + 1))

    frames = 0
    duration_ms = 0
    while offset < len(data):
        marker = data[offset]
        offset += 1
        if marker == 0x3B:
            break
        if marker == 0x21:
            label = data[offset]
            offset += 1
            if label == 0xF9:
                block_size = data[offset]
                if block_size != 4:
                    raise ValueError("invalid graphic control extension")
                duration_ms += struct.unpack("<H", data[offset + 2 : offset + 4])[0] * 10
                offset += 1 + block_size
                if data[offset] != 0:
                    raise ValueError("unterminated graphic control extension")
                offset += 1
            else:
                while True:
                    block_size = data[offset]
                    offset += 1
                    if block_size == 0:
                        break
                    offset += block_size
            continue
        if marker == 0x2C:
            frames += 1
            image_packed = data[offset + 8]
            offset += 9
            if image_packed & 0x80:
                offset += 3 * (2 ** ((image_packed & 0x07) + 1))
            offset += 1  # LZW minimum code size
            while True:
                block_size = data[offset]
                offset += 1
                if block_size == 0:
                    break
                offset += block_size
            continue
        raise ValueError(f"unexpected GIF block marker: {marker:#x}")
    return width, height, frames, duration_ms


class SkillPackagingTests(unittest.TestCase):
    def test_expected_skill_layout_exists(self):
        expected = {"download-best-audio", *SITE_SKILLS}
        actual = {path.name for path in SKILLS.iterdir() if path.is_dir()}
        self.assertEqual(actual, expected)
        for name in expected:
            skill_dir = SKILLS / name
            self.assertTrue((skill_dir / "SKILL.md").is_file())
            self.assertTrue((skill_dir / "agents" / "openai.yaml").is_file())
        for name in SITE_SKILLS:
            self.assertTrue((SKILLS / name / "scripts" / "run.py").is_file())

    def test_skill_frontmatter_matches_directory(self):
        for skill_dir in SKILLS.iterdir():
            if not skill_dir.is_dir():
                continue
            text = (skill_dir / "SKILL.md").read_text(encoding="utf-8")
            match = re.match(r"^---\s*\n(.*?)\n---\s*\n", text, re.DOTALL)
            self.assertIsNotNone(match, skill_dir.name)
            frontmatter = match.group(1) if match else ""
            self.assertRegex(frontmatter, rf"(?m)^name:\s*{re.escape(skill_dir.name)}\s*$")
            self.assertRegex(frontmatter, r"(?m)^description:\s*\S.+$")

    def test_openai_metadata_has_matching_default_prompt(self):
        for skill_dir in SKILLS.iterdir():
            if not skill_dir.is_dir():
                continue
            text = (skill_dir / "agents" / "openai.yaml").read_text(encoding="utf-8")
            self.assertIn(f"${skill_dir.name}", text)
            expected_policy = "false" if skill_dir.name == "download-best-audio" else "true"
            self.assertRegex(
                text,
                rf"(?m)^\s*allow_implicit_invocation:\s*{expected_policy}\s*$",
            )

    def test_repository_plugin_metadata_matches_marketplace(self):
        manifest_path = PLUGIN / ".codex-plugin" / "plugin.json"
        marketplace_path = ROOT / ".agents" / "plugins" / "marketplace.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        marketplace = json.loads(marketplace_path.read_text(encoding="utf-8"))

        self.assertEqual(manifest["name"], "codex-audio-download-skills")
        self.assertEqual(manifest["version"], "0.1.0")
        self.assertEqual(manifest["skills"], "./skills/")
        self.assertEqual(manifest["author"]["name"], "Yuan Says AI")
        self.assertEqual(manifest["interface"]["category"], "Productivity")
        self.assertTrue(manifest["interface"]["capabilities"])
        for prompt in manifest["interface"]["defaultPrompt"]:
            self.assertLessEqual(len(prompt), 128)

        self.assertEqual(marketplace["name"], "yuan-says-ai-audio")
        self.assertEqual(len(marketplace["plugins"]), 1)
        entry = marketplace["plugins"][0]
        self.assertEqual(entry["name"], manifest["name"])
        self.assertEqual(entry["source"]["source"], "local")
        self.assertEqual(
            entry["source"]["path"],
            "./plugins/codex-audio-download-skills",
        )
        self.assertNotIn("url", entry["source"])
        self.assertNotIn("ref", entry["source"])
        self.assertEqual(entry["policy"]["installation"], "AVAILABLE")
        self.assertEqual(entry["policy"]["authentication"], "ON_INSTALL")

    def test_install_docs_use_current_agent_skill_locations(self):
        for name in ("README.md", "README.zh-CN.md"):
            text = (ROOT / name).read_text(encoding="utf-8")
            self.assertIn("<repo-root>/.agents/skills/", text)
            self.assertIn("$HOME/.agents/skills/", text)
            self.assertIn(".agents/plugins/marketplace.json", text)
            self.assertIn("codex plugin marketplace add", text)
            self.assertIn("--ref v0.1.0", text)
            self.assertIn("codex-audio-download-skills@yuan-says-ai-audio", text)
            self.assertIn("plugins/codex-audio-download-skills/skills/", text)
            self.assertNotIn("--ref main", text)

    def test_repository_community_files_exist(self):
        expected = (
            "SECURITY.md",
            ".github/ISSUE_TEMPLATE/bug_report.yml",
            ".github/ISSUE_TEMPLATE/feature_request.yml",
            ".github/ISSUE_TEMPLATE/config.yml",
            ".github/pull_request_template.md",
            "docs/release-notes-v0.1.0.md",
            "docs/assets/demo.gif",
            "docs/assets/social-preview.png",
            "scripts/generate_demo_assets.py",
        )
        for relative_path in expected:
            with self.subTest(path=relative_path):
                self.assertTrue((ROOT / relative_path).is_file())

    def test_demo_asset_is_explicitly_fictional_and_sanitized(self):
        demo_path = ROOT / "docs" / "assets" / "demo.gif"
        preview_path = ROOT / "docs" / "assets" / "social-preview.png"
        demo = demo_path.read_bytes()
        preview = preview_path.read_bytes()

        self.assertEqual(gif_summary(demo), (960, 540, 25, 25_000))
        self.assertEqual(preview[:8], b"\x89PNG\r\n\x1a\n")
        self.assertEqual(struct.unpack(">II", preview[16:24]), (1280, 640))

        forbidden_fragments = (
            b"c:\\users\\",
            b"/users/",
            b"youtube.com",
            b"youtu.be",
            b"bilibili.com",
            b"douyin.com",
            b"cookie",
            b"token=",
            b"signature=",
            b"x-amz-",
        )
        for artifact in (demo, preview):
            folded = artifact.lower()
            for fragment in forbidden_fragments:
                self.assertNotIn(fragment, folded)

        generator = (ROOT / "scripts" / "generate_demo_assets.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("FICTIONAL", generator)
        self.assertIn("NO REAL URL", generator)
        self.assertIn("DEMO_FRAME_COUNT = 25", generator)

    def test_repository_contains_no_known_private_material(self):
        forbidden_fragments = (
            "C:" + "\\Users\\",
            "Program Files" + "\\Python",
            "vd" + "_source=",
            "spm" + "_id_from=",
            "BV1" + "vo7azLEX2",
            "gh" + "o_",
        )
        for path in ROOT.rglob("*"):
            if not path.is_file() or ".git" in path.parts or path.suffix.lower() not in TEXT_SUFFIXES:
                continue
            text = path.read_text(encoding="utf-8")
            for fragment in forbidden_fragments:
                self.assertNotIn(fragment.casefold(), text.casefold(), str(path))

    def test_repository_contains_no_media_or_binary_artifacts(self):
        forbidden_names = {"yt-dlp.exe", "ffmpeg.exe", "ffprobe.exe", "deno.exe"}
        raster_artifacts = set()
        for path in ROOT.rglob("*"):
            if (
                not path.is_file()
                or ".git" in path.parts
                or ".asset-build" in path.parts
            ):
                continue
            self.assertNotIn(path.suffix.lower(), MEDIA_SUFFIXES, str(path))
            self.assertNotIn(path.name.casefold(), forbidden_names, str(path))
            if path.suffix.lower() in {".gif", ".png"}:
                raster_artifacts.add(path.relative_to(ROOT).as_posix())
        self.assertEqual(
            raster_artifacts,
            {"docs/assets/demo.gif", "docs/assets/social-preview.png"},
        )

    def test_wrappers_find_core_from_unicode_custom_skill_root(self):
        with tempfile.TemporaryDirectory() as root:
            skills_root = Path(root) / "自定义 Codex Home" / "skills"
            core_dir = skills_root / "download-best-audio" / "scripts"
            core_dir.mkdir(parents=True)
            fake_core = core_dir / "download_audio.py"
            fake_core.write_text(
                "import json, sys\nprint(json.dumps(sys.argv[1:]))\n",
                encoding="utf-8",
            )

            encoded = base64.b64encode(b"https://example.invalid/video").decode("ascii")
            for name, platform in SITE_SKILLS.items():
                wrapper_dir = skills_root / name / "scripts"
                wrapper_dir.mkdir(parents=True)
                wrapper = wrapper_dir / "run.py"
                shutil.copy2(SKILLS / name / "scripts" / "run.py", wrapper)
                proc = subprocess.run(
                    [sys.executable, str(wrapper), "--url-base64", encoded],
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    check=False,
                )
                self.assertEqual(proc.returncode, 0, proc.stderr)
                args = json.loads(proc.stdout)
                self.assertEqual(args[-2:], ["--expected-platform", platform])

    def test_wrappers_enforce_their_platform_with_real_core(self):
        mismatched_urls = {
            "download-bilibili-audio": "https://youtu.be/BaW_jenozKc",
            "download-douyin-audio": "https://youtu.be/BaW_jenozKc",
            "download-youtube-audio": "https://www.bilibili.com/video/BV1example",
        }
        for name, url in mismatched_urls.items():
            encoded = base64.b64encode(url.encode("utf-8")).decode("ascii")
            wrapper = SKILLS / name / "scripts" / "run.py"
            proc = subprocess.run(
                [sys.executable, str(wrapper), "--url-base64", encoded],
                capture_output=True,
                text=True,
                encoding="utf-8",
                check=False,
            )
            self.assertEqual(proc.returncode, 2, name)
            payload = json.loads(proc.stdout)
            self.assertEqual(payload["error_code"], "unsupported_platform")

    def test_wrapper_reports_missing_shared_skill_without_leaking_path(self):
        with tempfile.TemporaryDirectory() as root:
            skills_root = Path(root) / "private user name" / "skills"
            wrapper_dir = skills_root / "download-bilibili-audio" / "scripts"
            wrapper_dir.mkdir(parents=True)
            wrapper = wrapper_dir / "run.py"
            shutil.copy2(
                SKILLS / "download-bilibili-audio" / "scripts" / "run.py",
                wrapper,
            )
            proc = subprocess.run(
                [sys.executable, str(wrapper), "--url-base64", "aHR0cHM6Ly94"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                check=False,
            )
            self.assertEqual(proc.returncode, 2)
            payload = json.loads(proc.stdout)
            self.assertEqual(payload["error_code"], "shared_skill_missing")
            self.assertNotIn("private user name", proc.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)

from __future__ import annotations

import base64
import json
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILLS = ROOT / "skills"
SITE_SKILLS = {
    "download-bilibili-audio": "Bilibili",
    "download-douyin-audio": "Douyin",
    "download-youtube-audio": "YouTube",
}
TEXT_SUFFIXES = {"", ".md", ".py", ".yaml", ".yml"}
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
        for path in ROOT.rglob("*"):
            if not path.is_file() or ".git" in path.parts:
                continue
            self.assertNotIn(path.suffix.lower(), MEDIA_SUFFIXES, str(path))
            self.assertNotIn(path.name.casefold(), forbidden_names, str(path))

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

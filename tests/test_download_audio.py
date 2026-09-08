from __future__ import annotations

import base64
import importlib.util
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = (
    ROOT
    / "plugins"
    / "codex-audio-download-skills"
    / "skills"
    / "download-best-audio"
    / "scripts"
    / "download_audio.py"
)
SPEC = importlib.util.spec_from_file_location("download_best_audio", SCRIPT)
assert SPEC and SPEC.loader
module = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = module
SPEC.loader.exec_module(module)


def fake_tools() -> module.ToolPaths:
    return module.ToolPaths(
        yt_dlp=Path(r"C:\tools\yt-dlp.exe"),
        ffmpeg=Path(r"C:\tools\ffmpeg.exe"),
        ffprobe=Path(r"C:\tools\ffprobe.exe"),
        deno=Path(r"C:\tools\deno.exe"),
    )


def metadata(**overrides):
    value = {
        "id": "BV1example",
        "title": "测试标题",
        "uploader": "测试作者",
        "duration": 12.5,
        "extractor_key": "BiliBili",
        "webpage_url_domain": "www.bilibili.com",
        "format_id": "30280",
        "acodec": "mp4a.40.2",
        "vcodec": "none",
        "ext": "m4a",
        "abr": 192,
        "asr": 48000,
        "audio_channels": 2,
    }
    value.update(overrides)
    return value


class UrlValidationTests(unittest.TestCase):
    def test_supported_domains_and_share_links(self):
        cases = {
            "https://www.douyin.com/video/123": "Douyin",
            "https://v.douyin.com/abc/": "Douyin",
            "https://www.bilibili.com/video/BV1x": "Bilibili",
            "https://b23.tv/abc": "Bilibili",
            "https://www.youtube.com/watch?v=BaW_jenozKc": "YouTube",
            "https://music.youtube.com/watch?v=BaW_jenozKc": "YouTube",
            "https://youtu.be/BaW_jenozKc": "YouTube",
        }
        for url, expected in cases.items():
            with self.subTest(url=url):
                self.assertEqual(module.validate_url(url)[0], expected)

    def test_rejects_suffix_attack_userinfo_and_nonstandard_port(self):
        bad = (
            "https://evilbilibili.com/video/x",
            "https://youtube.com.evil.example/watch?v=x",
            "https://user:secret@youtube.com/watch?v=x",
            "https://youtube.com:8443/watch?v=x",
            "file:///C:/secret.txt",
            "http://www.bilibili.com/video/BV1example",
            "https://example.com/media",
        )
        for url in bad:
            with self.subTest(url=url), self.assertRaises(module.DownloadFailure):
                module.validate_url(url)

    def test_rejects_control_characters(self):
        with self.assertRaises(module.DownloadFailure) as caught:
            module.validate_url("https://youtube.com/watch?v=x\n--exec=bad")
        self.assertEqual(caught.exception.error_code, "invalid_url")


class InputAndNamingTests(unittest.TestCase):
    def test_cookie_profiles_are_allowlisted(self):
        for value in ("chrome", "chrome:Default", "chrome:Profile 12"):
            self.assertEqual(module.validate_cookie_profile(value), value)
        for value in ("firefox", "chrome:C:\\secret", "chrome:Profile x", "chrome;bad"):
            with self.subTest(value=value), self.assertRaises(module.DownloadFailure):
                module.validate_cookie_profile(value)

    def test_windows_filename_is_safe_and_keeps_identifier(self):
        info = metadata(title='CON: 标题 / <测试> * ? " 很长' * 20)
        name = module.make_final_name(info, "Bilibili", "m4a")
        self.assertLessEqual(len(name), 225)
        self.assertTrue(name.endswith(" [Bilibili-BV1example].m4a"))
        self.assertFalse(any(char in name for char in '<>:"/\\|?*'))

    def test_codec_families_are_normalized(self):
        self.assertEqual(module.normalize_codec("mp4a.40.2"), "aac")
        self.assertEqual(module.normalize_codec("aac"), "aac")
        self.assertEqual(module.normalize_codec("opus"), "opus")
        self.assertEqual(module.normalize_codec("pcm_s16le"), "pcm")

    def test_relative_output_dir_is_rejected(self):
        with self.assertRaises(module.DownloadFailure) as caught:
            module.ensure_output_root("relative/output")
        self.assertEqual(caught.exception.error_code, "invalid_output_dir")

    @unittest.skipUnless(os.name == "nt", "Windows root normalization test")
    def test_normalized_drive_root_is_rejected(self):
        with self.assertRaises(module.DownloadFailure) as caught:
            module.ensure_output_root(r"C:\Windows\..")
        self.assertEqual(caught.exception.error_code, "invalid_output_dir")

    @unittest.skipUnless(os.name == "nt", "Windows UTF-16 path budget test")
    def test_utf16_filename_budget_accounts_for_output_root(self):
        deep_root = Path("C:/") / ("深" * 210)
        with self.assertRaises(module.DownloadFailure) as caught:
            module.make_final_name(metadata(), "Bilibili", "m4a", deep_root)
        self.assertEqual(caught.exception.error_code, "invalid_output_dir")

    @unittest.skipIf(os.name == "nt", "POSIX filename byte budget test")
    def test_posix_filename_stays_within_filesystem_byte_budget(self):
        with tempfile.TemporaryDirectory() as root:
            output_root = Path(root)
            name = module.make_final_name(
                metadata(title="深" * 300), "Bilibili", "m4a", output_root
            )
            self.assertLessEqual(
                len(os.fsencode(name)), module.posix_filename_budget(output_root)
            )


class DependencyResolutionTests(unittest.TestCase):
    def test_safe_path_uses_absolute_entry_and_ignores_relative_entry(self):
        with tempfile.TemporaryDirectory() as root:
            root_path = Path(root)
            executable_name = module.executable_names("yt-dlp")[0]
            executable = root_path / executable_name
            executable.write_bytes(b"test")
            executable.chmod(0o755)
            with mock.patch.dict(
                module.os.environ,
                {"PATH": os.pathsep.join((".", str(root_path.resolve())))},
                clear=False,
            ):
                self.assertEqual(module.resolve_from_safe_path("yt-dlp"), executable.resolve())

    def test_resolve_tool_prefers_safe_path(self):
        expected = Path("/trusted/yt-dlp")
        with mock.patch.object(
            module, "resolve_from_safe_path", return_value=expected
        ), mock.patch.object(module, "resolve_from_winget") as winget:
            self.assertEqual(module.resolve_tool("yt-dlp"), expected)
        winget.assert_not_called()

    def test_deno_is_optional_except_for_youtube(self):
        resolved = {
            "yt-dlp": Path("/tools/yt-dlp"),
            "ffmpeg": Path("/tools/ffmpeg"),
            "ffprobe": Path("/tools/ffprobe"),
            "deno": None,
        }
        with mock.patch.object(module, "resolve_tool", side_effect=resolved.get):
            tools = module.resolve_tools("Bilibili")
        self.assertIsNone(tools.deno)

        with mock.patch.object(module, "resolve_tool", side_effect=resolved.get):
            with self.assertRaises(module.DownloadFailure) as caught:
                module.resolve_tools("YouTube")
        self.assertEqual(caught.exception.error_code, "dependency_missing")

    def test_yt_dlp_args_omit_missing_optional_deno(self):
        tools = module.ToolPaths(
            yt_dlp=Path("/tools/yt-dlp"),
            ffmpeg=Path("/tools/ffmpeg"),
            ffprobe=Path("/tools/ffprobe"),
            deno=None,
        )
        args = module.yt_dlp_common_args(tools, None)
        self.assertNotIn("--js-runtimes", args)

    def test_yt_dlp_args_disable_geo_header_and_proxy(self):
        args = module.yt_dlp_common_args(fake_tools(), None)
        self.assertEqual(args[args.index("--xff") + 1], "never")
        self.assertEqual(args[args.index("--proxy") + 1], "")


class MetadataTests(unittest.TestCase):
    def test_metadata_command_uses_argv_boundary_and_ignores_config(self):
        payload = metadata()
        completed = subprocess.CompletedProcess([], 0, json.dumps(payload), "")
        with mock.patch.object(module, "run_process", return_value=completed) as run:
            result = module.load_metadata(
                "https://www.bilibili.com/video/BV1example?" + "token" + "=secret",
                "Bilibili",
                fake_tools(),
                {},
                None,
            )
        args = run.call_args.args[0]
        self.assertEqual(result["id"], "BV1example")
        self.assertIn("--ignore-config", args)
        self.assertEqual(args[args.index("--xff") + 1], "never")
        self.assertEqual(args[args.index("--proxy") + 1], "")
        self.assertIn("--encoding", args)
        self.assertIn("--js-runtimes", args)
        self.assertEqual(args[-2], "--")
        self.assertTrue(args[-1].startswith("https://"))
        self.assertNotIn("--cookies-from-browser", args)

    def test_authorized_cookie_is_one_argv_value(self):
        payload = metadata()
        completed = subprocess.CompletedProcess([], 0, json.dumps(payload), "")
        with mock.patch.object(module, "run_process", return_value=completed) as run:
            module.load_metadata(
                "https://www.bilibili.com/video/BV1example",
                "Bilibili",
                fake_tools(),
                {},
                "chrome:Profile 2",
            )
        args = run.call_args.args[0]
        index = args.index("--cookies-from-browser")
        self.assertEqual(args[index + 1], "chrome:Profile 2")

    def test_wrong_redirect_extractor_is_rejected(self):
        completed = subprocess.CompletedProcess(
            [], 0, json.dumps(metadata(extractor_key="Generic")), ""
        )
        with mock.patch.object(module, "run_process", return_value=completed):
            with self.assertRaises(module.DownloadFailure) as caught:
                module.load_metadata(
                    "https://b23.tv/example", "Bilibili", fake_tools(), {}, None
                )
        self.assertEqual(caught.exception.error_code, "redirect_unverified")

    def test_playlist_and_live_are_rejected(self):
        variants = (
            (metadata(_type="playlist", entries=[]), "playlist_not_supported"),
            (metadata(is_live=True, live_status="is_live"), "live_not_supported"),
        )
        for payload, error_code in variants:
            completed = subprocess.CompletedProcess([], 0, json.dumps(payload), "")
            with self.subTest(error_code=error_code), mock.patch.object(
                module, "run_process", return_value=completed
            ):
                with self.assertRaises(module.DownloadFailure) as caught:
                    module.load_metadata(
                        "https://www.bilibili.com/video/BV1example",
                        "Bilibili",
                        fake_tools(),
                        {},
                        None,
                    )
                self.assertEqual(caught.exception.error_code, error_code)

    def test_douyin_requires_verified_author_and_duration(self):
        completed = subprocess.CompletedProcess(
            [],
            0,
            json.dumps(
                metadata(
                    id="123",
                    extractor_key="Douyin",
                    uploader=None,
                    duration=None,
                )
            ),
            "",
        )
        with mock.patch.object(module, "run_process", return_value=completed):
            with self.assertRaises(module.DownloadFailure) as caught:
                module.load_metadata(
                    "https://v.douyin.com/example", "Douyin", fake_tools(), {}, None
                )
        self.assertEqual(caught.exception.error_code, "redirect_unverified")

    def test_metadata_drm_uses_stable_error_code(self):
        completed = subprocess.CompletedProcess(
            [], 0, json.dumps(metadata(has_drm=True)), ""
        )
        with mock.patch.object(module, "run_process", return_value=completed):
            with self.assertRaises(module.DownloadFailure) as caught:
                module.load_metadata(
                    "https://www.bilibili.com/video/BV1example",
                    "Bilibili",
                    fake_tools(),
                    {},
                    None,
                )
        self.assertEqual(caught.exception.error_code, "drm_or_paid_restricted")


class ResultSafetyTests(unittest.TestCase):
    def test_failed_final_verification_leaves_no_final_named_file(self):
        valid_probe = {
            "codec": "aac",
            "profile": "LC",
            "container": "mov,mp4,m4a",
            "bitrate_kbps": 192,
            "sample_rate_hz": 48000,
            "channels": 2,
            "duration_seconds": 12.5,
            "size_bytes": 2048,
        }

        def fake_download(args, **_kwargs):
            self.assertEqual(args[args.index("--xff") + 1], "never")
            self.assertEqual(args[args.index("--proxy") + 1], "")
            template = Path(args[args.index("-o") + 1])
            candidate = template.parent / "source.m4a"
            candidate.write_bytes(b"audio")
            return subprocess.CompletedProcess(
                args, 0, "after_move:" + json.dumps(str(candidate)), ""
            )

        with tempfile.TemporaryDirectory() as root, mock.patch.object(
            module, "resolve_tools", return_value=fake_tools()
        ), mock.patch.object(module, "child_environment", return_value={}), mock.patch.object(
            module, "tool_versions", return_value={}
        ), mock.patch.object(
            module, "load_metadata", return_value=metadata()
        ), mock.patch.object(
            module, "run_process", side_effect=fake_download
        ), mock.patch.object(
            module,
            "probe_media",
            side_effect=[
                valid_probe,
                module.DownloadFailure("verification_failed", "final verification failed"),
            ],
        ):
            with self.assertRaises(module.DownloadFailure) as caught:
                module.download_audio(
                    "https://www.bilibili.com/video/BV1example",
                    output_dir=root,
                    cookie_profile=None,
                    force=False,
                    expected_platform="Bilibili",
                )

            self.assertEqual(caught.exception.error_code, "verification_failed")
            self.assertFalse(list(Path(root).glob("* [Bilibili-BV1example].m4a")))

    def test_non_force_commit_never_replaces_existing_target(self):
        with tempfile.TemporaryDirectory() as root:
            root_path = Path(root)
            source = root_path / "source.m4a"
            target = root_path / "target.m4a"
            source.write_bytes(b"new")
            target.write_bytes(b"old")
            with self.assertRaises(FileExistsError):
                module.move_without_overwrite(source, target)
            self.assertEqual(target.read_bytes(), b"old")
            self.assertEqual(source.read_bytes(), b"new")

    def test_non_force_commit_moves_new_file(self):
        with tempfile.TemporaryDirectory() as root:
            root_path = Path(root)
            source = root_path / "source.m4a"
            target = root_path / "target.m4a"
            source.write_bytes(b"audio")
            module.move_without_overwrite(source, target)
            self.assertFalse(source.exists())
            self.assertEqual(target.read_bytes(), b"audio")

    def test_failure_mapping_does_not_echo_secret_url(self):
        raw = "ERROR login required https://example/media?" + "token" + "=super-secret"
        failure = module.classify_failure(raw, cookies_used=False, stage="metadata")
        self.assertEqual(failure.error_code, "authentication_required")
        self.assertNotIn("super-secret", failure.message)

    def test_http_403_is_reported_as_ambiguous_access_denial(self):
        failure = module.classify_failure(
            "ERROR: unable to download video data: HTTP Error 403: Forbidden",
            cookies_used=False,
            stage="download",
        )
        self.assertEqual(failure.error_code, "access_denied")

    def test_url_text_cannot_spoof_drm_classification(self):
        failure = module.classify_failure(
            "ERROR https://youtube.com/watch?v=abc123&reason=drm HTTP Error 403",
            cookies_used=False,
            stage="download",
        )
        self.assertEqual(failure.error_code, "access_denied")

    def test_after_move_path_must_stay_in_staging(self):
        with tempfile.TemporaryDirectory() as root:
            root_path = Path(root)
            staging = root_path / "stage"
            staging.mkdir()
            outside = root_path / "outside.m4a"
            outside.write_bytes(b"data")
            line = "after_move:" + json.dumps(str(outside))
            with self.assertRaises(module.DownloadFailure) as caught:
                module.parse_after_move(line, staging.resolve())
        self.assertEqual(caught.exception.error_code, "path_validation_failed")

    def test_after_move_accepts_yt_dlp_json_string_output(self):
        with tempfile.TemporaryDirectory() as root:
            staging = Path(root).resolve()
            audio = staging / "source.opus"
            audio.write_bytes(b"data")
            parsed = module.parse_after_move(json.dumps(str(audio)), staging)
            self.assertEqual(parsed, audio.resolve())

    def test_result_marks_remux_without_transcode(self):
        probe = {
            "codec": "aac",
            "container": "mov,mp4,m4a",
            "bitrate_kbps": 192,
            "sample_rate_hz": 48000,
            "channels": 2,
            "duration_seconds": 12.5,
            "size_bytes": 2048,
        }
        payload = module.result_payload(
            status="downloaded",
            path=Path(r"C:\out\name.m4a"),
            info=metadata(ext="mp4"),
            platform="Bilibili",
            probe=probe,
            cookies_used=False,
            versions={},
            verification_basis="downloaded_source_vs_final_file",
        )
        self.assertTrue(payload["source_codec_preserved"])
        self.assertTrue(payload["remuxed"])
        self.assertFalse(payload["transcoded"])

    def test_audio_invariant_mismatch_is_rejected(self):
        probe = {
            "codec": "opus",
            "sample_rate_hz": 48000,
            "channels": 2,
            "duration_seconds": 12.5,
        }
        with self.assertRaises(module.DownloadFailure) as caught:
            module.ensure_audio_invariants(
                metadata(), probe, error_code="unexpected_transcode"
            )
        self.assertEqual(caught.exception.error_code, "unexpected_transcode")

    def test_existing_different_bitrate_tier_is_rejected(self):
        for bitrate in (128, 288):
            probe = {
                "codec": "aac",
                "profile": "LC",
                "bitrate_kbps": bitrate,
                "sample_rate_hz": 48000,
                "channels": 2,
                "duration_seconds": 12.5,
            }
            with self.subTest(bitrate=bitrate), self.assertRaises(
                module.DownloadFailure
            ) as caught:
                module.ensure_audio_invariants(
                    metadata(abr=192), probe, error_code="existing_outdated"
                )
            self.assertEqual(caught.exception.error_code, "existing_outdated")

    def test_base64_transport_round_trips_shell_characters(self):
        raw = "https://www.youtube.com/watch?v=BaW_jenozKc&x=$(`whoami`);'\""
        encoded = base64.b64encode(raw.encode("utf-8")).decode("ascii")
        value = module.choose_cli_text(
            None,
            encoded,
            label="链接",
            max_bytes=4096,
            required=True,
        )
        self.assertEqual(value, raw)

    def test_parser_error_does_not_echo_second_signed_url(self):
        secret = "https://youtu.be/BaW_jenozKc?" + "token" + "=super-secret"
        output = io.StringIO()
        with redirect_stdout(output):
            exit_code = module.main(
                ["https://youtu.be/BaW_jenozKc", secret]
            )
        payload = json.loads(output.getvalue())
        self.assertEqual(exit_code, 2)
        self.assertNotIn("super-secret", payload["message"])

    def test_site_specific_platform_lock(self):
        with self.assertRaises(module.DownloadFailure) as caught:
            module.download_audio(
                "https://youtu.be/BaW_jenozKc",
                output_dir=None,
                cookie_profile=None,
                force=False,
                expected_platform="Bilibili",
            )
        self.assertEqual(caught.exception.error_code, "unsupported_platform")

    def test_timeout_terminates_process_tree(self):
        fake_process = mock.Mock()
        fake_process.communicate.side_effect = subprocess.TimeoutExpired(
            cmd=["tool"], timeout=1
        )
        with mock.patch.object(module.subprocess, "Popen", return_value=fake_process), mock.patch.object(
            module, "terminate_and_reap"
        ) as terminate:
            with self.assertRaises(module.DownloadFailure) as caught:
                module.run_process(["tool"], env={}, timeout=1, stage="download")
        self.assertEqual(caught.exception.error_code, "download_timeout")
        terminate.assert_called_once_with(fake_process)

    def test_keyboard_interrupt_terminates_process_tree(self):
        fake_process = mock.Mock()
        fake_process.communicate.side_effect = KeyboardInterrupt
        with mock.patch.object(module.subprocess, "Popen", return_value=fake_process), mock.patch.object(
            module, "terminate_and_reap"
        ) as terminate:
            with self.assertRaises(KeyboardInterrupt):
                module.run_process(["tool"], env={}, timeout=1, stage="download")
        terminate.assert_called_once_with(fake_process)

    def test_main_returns_json_for_invalid_url(self):
        output = io.StringIO()
        with redirect_stdout(output):
            exit_code = module.main(["https://example.com/video"])
        payload = json.loads(output.getvalue())
        self.assertEqual(exit_code, 2)
        self.assertEqual(payload["status"], "failed")
        self.assertEqual(payload["error_code"], "unsupported_platform")

    def test_source_has_no_shell_execution(self):
        source = SCRIPT.read_text(encoding="utf-8")
        self.assertIn("shell=False", source)
        self.assertNotIn("shell" + "=True", source)
        self.assertNotIn("os" + ".system", source)
        self.assertNotIn("shutil.which", source)

    def test_dependency_diagnostics_have_stable_four_key_schema(self):
        available = {
            "yt-dlp": Path(r"C:\tools\yt-dlp.exe"),
            "ffmpeg": None,
            "ffprobe": Path(r"C:\tools\ffprobe.exe"),
            "deno": None,
        }
        with mock.patch.object(module, "resolve_tool", side_effect=available.get), mock.patch.object(
            module, "version_line", return_value="test-version"
        ):
            result = module.diagnostic_versions()
        self.assertEqual(set(result), {"yt_dlp", "ffmpeg", "ffprobe", "deno"})
        self.assertEqual(result["yt_dlp"], "test-version")
        self.assertEqual(result["ffmpeg"], "missing")


if __name__ == "__main__":
    unittest.main(verbosity=2)

#!/usr/bin/env python3
"""Download one source-quality audio track with yt-dlp and verify the result."""

from __future__ import annotations

import argparse
import base64
import binascii
import json
import os
import re
import secrets
import signal
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import parse_qs, urlsplit


DEFAULT_OUTPUT_DIR = Path.home() / "Downloads" / "Codex-Audio"
METADATA_TIMEOUT_SECONDS = 180
DOWNLOAD_TIMEOUT_SECONDS = 7200
SAFE_TOTAL_PATH_UTF16_UNITS = 240
POSIX_DEFAULT_NAME_MAX_BYTES = 255
POSIX_DEFAULT_PATH_MAX_BYTES = 4096

PLATFORM_DOMAINS = {
    "Douyin": ("douyin.com", "iesdouyin.com"),
    "Bilibili": ("bilibili.com", "b23.tv"),
    "YouTube": ("youtube.com", "youtu.be", "youtube-nocookie.com"),
}

EXPECTED_EXTRACTORS = {
    "Douyin": ("douyin",),
    "Bilibili": ("bilibili", "bili"),
    "YouTube": ("youtube",),
}

WINDOWS_RESERVED_RE = re.compile(
    r"^(?:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:[ .]|$)", re.IGNORECASE
)
CONTROL_RE = re.compile(r"[\x00-\x1f\x7f]")
INVALID_FILENAME_RE = re.compile(r'[<>:"/\\|?*]')
PROFILE_RE = re.compile(r"^chrome(?::(?:Default|Profile [0-9]+))?$", re.IGNORECASE)
WINGET_PACKAGE_PREFIXES = {
    "yt-dlp": "yt-dlp.yt-dlp_",
    "ffmpeg": "yt-dlp.FFmpeg_",
    "ffprobe": "yt-dlp.FFmpeg_",
    "deno": "DenoLand.Deno_",
}


@dataclass(frozen=True)
class ToolPaths:
    yt_dlp: Path
    ffmpeg: Path
    ffprobe: Path
    deno: Path | None


class DownloadFailure(Exception):
    def __init__(
        self,
        error_code: str,
        message: str,
        details: dict[str, Any] | None = None,
    ):
        super().__init__(message)
        self.error_code = error_code
        self.message = message
        self.details = details or {}


class JsonArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        del message
        raise DownloadFailure(
            "invalid_arguments",
            "参数无效：请只提供一个链接，并使用受支持的选项。",
        )


def emit(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))


def host_matches(host: str, domain: str) -> bool:
    return host == domain or host.endswith(f".{domain}")


def validate_url(raw_url: str) -> tuple[str, str]:
    if not raw_url or len(raw_url) > 4096 or CONTROL_RE.search(raw_url):
        raise DownloadFailure("invalid_url", "链接为空、过长或包含控制字符。")

    try:
        parsed = urlsplit(raw_url)
        port = parsed.port
    except ValueError as exc:
        raise DownloadFailure("invalid_url", "链接格式无效。") from exc

    if parsed.scheme.lower() != "https" or not parsed.hostname:
        raise DownloadFailure("invalid_url", "只接受一个完整的 HTTPS 视频链接。")
    if parsed.username is not None or parsed.password is not None:
        raise DownloadFailure("invalid_url", "链接不能包含用户名或密码。")
    if port is not None:
        if port != 443:
            raise DownloadFailure("invalid_url", "不接受使用非标准端口的视频链接。")

    host = parsed.hostname.rstrip(".").lower()
    path = parsed.path or "/"
    query = parse_qs(parsed.query, keep_blank_values=True)
    for platform, domains in PLATFORM_DOMAINS.items():
        if any(host_matches(host, domain) for domain in domains):
            if not is_supported_video_path(platform, host, path, query):
                raise DownloadFailure(
                    "invalid_url",
                    "该地址不是第一版支持的单个已发布视频链接。",
                )
            return platform, host

    raise DownloadFailure(
        "unsupported_platform",
        "第一版只支持抖音、B站和 YouTube 的正式链接或分享短链。",
    )


def is_supported_video_path(
    platform: str,
    host: str,
    path: str,
    query: dict[str, list[str]],
) -> bool:
    """Reject non-video and redirect endpoints before any network access."""
    normalized = path.rstrip("/") or "/"
    if platform == "Douyin":
        if host == "v.douyin.com":
            return bool(re.fullmatch(r"/[A-Za-z0-9_-]+", normalized))
        if host_matches(host, "iesdouyin.com"):
            return bool(re.fullmatch(r"/share/video/[0-9]+", normalized))
        return bool(re.fullmatch(r"/video/[0-9]+", normalized))
    if platform == "Bilibili":
        if host == "b23.tv":
            return bool(re.fullmatch(r"/[A-Za-z0-9_-]+", normalized))
        return bool(re.fullmatch(r"/video/(?:BV[A-Za-z0-9]+|av[0-9]+)", normalized, re.IGNORECASE))
    if platform == "YouTube":
        if host == "youtu.be":
            return bool(re.fullmatch(r"/[A-Za-z0-9_-]{6,}", normalized))
        if normalized == "/watch":
            video_ids = query.get("v", [])
            return len(video_ids) == 1 and bool(
                re.fullmatch(r"[A-Za-z0-9_-]{6,}", video_ids[0])
            )
        return bool(
            re.fullmatch(
                r"/(?:shorts|embed|live)/[A-Za-z0-9_-]{6,}",
                normalized,
                re.IGNORECASE,
            )
        )
    return False


def validate_cookie_profile(profile: str | None) -> str | None:
    if profile is None:
        return None
    if not PROFILE_RE.fullmatch(profile):
        raise DownloadFailure(
            "invalid_cookie_profile",
            "浏览器配置只允许 chrome、chrome:Default 或 chrome:Profile N。",
        )
    return profile


def is_within(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def executable_names(name: str) -> tuple[str, ...]:
    """Return directly executable filenames without invoking a command shell."""
    if os.name == "nt":
        return (f"{name}.exe",)
    return (name,)


def safe_path_directories() -> list[Path]:
    """Return resolved absolute PATH entries while excluding cwd and duplicates."""
    try:
        current = Path.cwd().resolve(strict=True)
    except OSError:
        current = None
    result: list[Path] = []
    seen: set[str] = set()
    for raw_directory in os.environ.get("PATH", "").split(os.pathsep):
        directory = Path(raw_directory) if raw_directory else None
        if directory is None or not directory.is_absolute():
            continue
        try:
            resolved_directory = directory.resolve(strict=True)
        except OSError:
            continue
        if current is not None and resolved_directory == current:
            continue
        key = os.path.normcase(str(resolved_directory))
        if key in seen:
            continue
        seen.add(key)
        result.append(resolved_directory)
    return result


def resolve_from_safe_path(name: str) -> Path | None:
    """Search safe PATH entries without invoking a command shell."""
    for resolved_directory in safe_path_directories():
        for executable_name in executable_names(name):
            candidate = resolved_directory / executable_name
            if candidate.is_file() and os.access(candidate, os.X_OK):
                return candidate.resolve(strict=True)
    return None


def resolve_from_winget(name: str) -> Path | None:
    """Find the newest matching portable WinGet package without trusting cwd."""
    local_app_data = os.environ.get("LOCALAPPDATA")
    prefix = WINGET_PACKAGE_PREFIXES.get(name)
    if not local_app_data or not prefix:
        return None
    packages = Path(local_app_data) / "Microsoft" / "WinGet" / "Packages"
    try:
        packages = packages.resolve(strict=True)
    except OSError:
        return None

    package_dirs: list[tuple[float, Path]] = []
    try:
        children = list(packages.iterdir())
    except OSError:
        return None
    for child in children:
        if not child.is_dir() or not child.name.casefold().startswith(prefix.casefold()):
            continue
        try:
            resolved_child = child.resolve(strict=True)
            modified = resolved_child.stat().st_mtime
        except OSError:
            continue
        if is_within(resolved_child, packages):
            package_dirs.append((modified, resolved_child))

    for _, package_dir in sorted(
        package_dirs,
        key=lambda item: item[0],
        reverse=True,
    ):
        try:
            candidates = sorted(package_dir.rglob(f"{name}.exe"))
        except OSError:
            continue
        for candidate in candidates:
            try:
                resolved_candidate = candidate.resolve(strict=True)
            except OSError:
                continue
            if (
                resolved_candidate.is_file()
                and is_within(resolved_candidate, package_dir)
                and is_within(resolved_candidate, packages)
            ):
                return resolved_candidate
    return None


def resolve_tool(name: str) -> Path | None:
    from_path = resolve_from_safe_path(name)
    if from_path is not None:
        return from_path
    if os.name == "nt":
        return resolve_from_winget(name)
    return None


def resolve_tools(platform: str) -> ToolPaths:
    resolved = {
        name: resolve_tool(name) for name in ("yt-dlp", "ffmpeg", "ffprobe", "deno")
    }
    required = ["yt-dlp", "ffmpeg", "ffprobe"]
    if platform == "YouTube":
        required.append("deno")
    missing = [name for name in required if resolved[name] is None]
    if missing:
        raise DownloadFailure(
            "dependency_missing",
            "缺少依赖："
            + "、".join(missing)
            + "。请按照项目 README 安装依赖，并重新打开终端或 Codex。",
        )
    return ToolPaths(
        yt_dlp=resolved["yt-dlp"],  # type: ignore[arg-type]
        ffmpeg=resolved["ffmpeg"],  # type: ignore[arg-type]
        ffprobe=resolved["ffprobe"],  # type: ignore[arg-type]
        deno=resolved["deno"],
    )


def child_environment(tools: ToolPaths) -> dict[str, str]:
    env = os.environ.copy()
    tool_dirs: list[str] = []
    for path in (tools.yt_dlp, tools.ffmpeg, tools.ffprobe, tools.deno):
        if path is None:
            continue
        parent = str(path.parent)
        if parent.casefold() not in {item.casefold() for item in tool_dirs}:
            tool_dirs.append(parent)
    if os.name == "nt":
        system_root = Path(os.environ.get("SystemRoot", r"C:\Windows"))
        system32 = system_root / "System32"
        if system32.is_dir():
            tool_dirs.append(str(system32.resolve()))
        env["NoDefaultCurrentDirectoryInExePath"] = "1"
        env["PATH"] = os.pathsep.join(tool_dirs)
    else:
        safe_path = [str(item) for item in safe_path_directories()]
        env["PATH"] = os.pathsep.join(tool_dirs + safe_path)
    env["NO_COLOR"] = "1"
    env["PYTHONUTF8"] = "1"
    return env


def terminate_process_tree(process: subprocess.Popen[str]) -> None:
    if process.poll() is not None:
        return
    if os.name == "nt":
        system_root = Path(os.environ.get("SystemRoot", r"C:\Windows"))
        taskkill = system_root / "System32" / "taskkill.exe"
        if taskkill.is_file():
            try:
                subprocess.run(
                    [str(taskkill), "/PID", str(process.pid), "/T", "/F"],
                    shell=False,
                    capture_output=True,
                    timeout=15,
                    creationflags=subprocess.CREATE_NO_WINDOW,
                    check=False,
                )
            except (OSError, subprocess.TimeoutExpired):
                pass
    else:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except (OSError, ProcessLookupError):
            pass
    if process.poll() is None:
        try:
            process.kill()
        except OSError:
            pass


def terminate_and_reap(process: subprocess.Popen[str]) -> None:
    terminate_process_tree(process)
    try:
        process.communicate(timeout=15)
    except subprocess.TimeoutExpired:
        try:
            process.kill()
        except OSError:
            pass
        process.communicate()


def run_process(
    args: list[str],
    *,
    env: dict[str, str],
    timeout: int,
    stage: str,
) -> subprocess.CompletedProcess[str]:
    creationflags = 0
    popen_options: dict[str, Any] = {}
    if os.name == "nt":
        creationflags = subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        popen_options["start_new_session"] = True
    try:
        process = subprocess.Popen(
            args,
            shell=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
            creationflags=creationflags,
            **popen_options,
        )
        try:
            stdout, stderr = process.communicate(timeout=timeout)
        except subprocess.TimeoutExpired as exc:
            terminate_and_reap(process)
            error_code = (
                "network_or_rate_limited"
                if stage == "metadata"
                else "download_timeout"
            )
            raise DownloadFailure(error_code, "操作超时，未生成正式文件。") from exc
        except KeyboardInterrupt:
            terminate_and_reap(process)
            raise
        return subprocess.CompletedProcess(
            args=args,
            returncode=process.returncode,
            stdout=stdout,
            stderr=stderr,
        )
    except OSError as exc:
        raise DownloadFailure("dependency_unavailable", "无法启动所需的下载或验证工具。") from exc


def version_line(path: Path, args: Iterable[str], env: dict[str, str]) -> str:
    proc = run_process(
        [str(path), *args], env=env, timeout=30, stage="version"
    )
    text = (proc.stdout or proc.stderr).strip().splitlines()
    return text[0][:160] if text else "unknown"


def tool_versions(tools: ToolPaths, env: dict[str, str]) -> dict[str, str]:
    return {
        "yt_dlp": version_line(tools.yt_dlp, ["--version"], env),
        "ffmpeg": version_line(tools.ffmpeg, ["-version"], env),
        "ffprobe": version_line(tools.ffprobe, ["-version"], env),
        "deno": (
            version_line(tools.deno, ["--version"], env)
            if tools.deno is not None
            else "missing"
        ),
    }


def diagnostic_versions() -> dict[str, str]:
    resolved = {
        name: resolve_tool(name) for name in ("yt-dlp", "ffmpeg", "ffprobe", "deno")
    }
    key_names = {"yt-dlp": "yt_dlp", "ffmpeg": "ffmpeg", "ffprobe": "ffprobe", "deno": "deno"}
    version_args = {
        "yt-dlp": ["--version"],
        "ffmpeg": ["-version"],
        "ffprobe": ["-version"],
        "deno": ["--version"],
    }
    env = os.environ.copy()
    directories = [str(path.parent) for path in resolved.values() if path is not None]
    if os.name == "nt":
        system32 = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32"
        if system32.is_dir():
            directories.append(str(system32.resolve()))
        env["NoDefaultCurrentDirectoryInExePath"] = "1"
    env["PATH"] = os.pathsep.join(dict.fromkeys(directories))
    env["NO_COLOR"] = "1"
    env["PYTHONUTF8"] = "1"

    result: dict[str, str] = {}
    for name, path in resolved.items():
        key = key_names[name]
        if path is None:
            result[key] = "missing"
            continue
        try:
            result[key] = version_line(path, version_args[name], env)
        except DownloadFailure:
            result[key] = "version_check_failed"
    return result


def classify_failure(text: str, *, cookies_used: bool, stage: str) -> DownloadFailure:
    diagnostic = re.sub(r"https?://[^\s'\"<>]+", "<url>", text, flags=re.IGNORECASE)
    lowered = diagnostic.casefold()

    if "no space left on device" in lowered or "磁盘空间不足" in lowered:
        return DownloadFailure("disk_full", "磁盘空间不足，未生成正式文件。")
    if "could not copy chrome cookie database" in lowered or "failed to decrypt" in lowered:
        return DownloadFailure(
            "cookie_read_failed", "无法读取本次授权的 Chrome 会话，请确认浏览器配置后重试。"
        )
    if any(
        marker in lowered
        for marker in ("drm protected", "detected drm", "widevine", "encrypted media")
    ):
        return DownloadFailure(
            "drm_or_paid_restricted", "该内容包含 DRM，Skill 不会尝试绕过。"
        )
    if any(
        marker in lowered
        for marker in (
            "purchase required",
            "available for purchase",
            "rent this video",
            "paid content",
            "premium subscription required",
        )
    ):
        return DownloadFailure(
            "drm_or_paid_restricted",
            "该内容受付费访问控制限制，Skill 不会尝试绕过。",
        )
    if any(
        marker in lowered
        for marker in (
            "not available in your country",
            "geo restricted",
            "geographic restriction",
            "region restriction",
            "仅限地区",
        )
    ):
        return DownloadFailure(
            "region_restricted", "该内容受地区限制，Skill 不会使用代理绕过。"
        )
    if any(
        marker in lowered
        for marker in (
            "login required",
            "sign in to confirm",
            "sign in to verify",
            "authentication required",
            "private video",
            "members-only",
            "age-restricted",
            "fresh cookies",
            "use --cookies-from-browser",
            "需要登录",
        )
    ):
        if cookies_used:
            return DownloadFailure(
                "account_or_entitlement_restricted",
                "使用已授权的 Chrome 会话后仍无法访问，可能受账号权限或订阅限制。",
            )
        return DownloadFailure(
            "authentication_required",
            "该链接需要登录会话。请先确认是否允许本次读取 Chrome Cookie。",
        )
    if "unsupported url" in lowered or "no suitable extractor" in lowered:
        return DownloadFailure(
            "extractor_failed", "当前 yt-dlp 无法解析该链接，可能是站点已改版。"
        )
    if "http error 403" in lowered or "http error 412" in lowered:
        return DownloadFailure(
            "access_denied",
            "站点拒绝了媒体请求；可能是解析器版本或访问权限问题，未自动读取 Cookie。",
        )
    if "requested format is not available" in lowered or "no video formats found" in lowered:
        return DownloadFailure("no_audio", "页面没有暴露可下载的音轨。")
    if any(
        marker in lowered
        for marker in ("http error 429", "too many requests", "rate limit", "timed out")
    ):
        return DownloadFailure(
            "network_or_rate_limited", "网络请求超时或被站点限流，请稍后重试。"
        )
    if any(
        marker in lowered
        for marker in ("postprocessing:", "post-processing:", "error in postprocessing")
    ):
        return DownloadFailure(
            "postprocessing_failed", "音频后处理失败，未生成正式文件。"
        )
    if stage == "download":
        return DownloadFailure("download_failed", "音频下载或后处理失败，未生成正式文件。")
    return DownloadFailure(
        "extractor_failed", "无法解析该页面，可能是链接失效或站点解析规则已变化。"
    )


def yt_dlp_common_args(tools: ToolPaths, cookie_profile: str | None) -> list[str]:
    args = [
        str(tools.yt_dlp),
        "--ignore-config",
        "--xff",
        "never",
        "--proxy",
        "",
        "--no-playlist",
        "--socket-timeout",
        "30",
        "--retries",
        "3",
        "--fragment-retries",
        "3",
        "--encoding",
        "utf-8",
        "--ffmpeg-location",
        str(tools.ffmpeg.parent),
    ]
    if tools.deno is not None:
        args.extend(["--js-runtimes", f"deno:{tools.deno}"])
    if cookie_profile:
        args.extend(["--cookies-from-browser", cookie_profile])
    return args


def load_metadata(
    url: str,
    platform: str,
    tools: ToolPaths,
    env: dict[str, str],
    cookie_profile: str | None,
) -> dict[str, Any]:
    args = yt_dlp_common_args(tools, cookie_profile)
    args.extend(
        [
            "--skip-download",
            "--no-warnings",
            "-f",
            "bestaudio/best",
            "--dump-single-json",
            "--",
            url,
        ]
    )
    proc = run_process(args, env=env, timeout=METADATA_TIMEOUT_SECONDS, stage="metadata")
    if proc.returncode != 0:
        raise classify_failure(
            f"{proc.stderr}\n{proc.stdout}",
            cookies_used=cookie_profile is not None,
            stage="metadata",
        )

    try:
        info = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise DownloadFailure(
            "extractor_failed", "下载器没有返回可验证的单视频信息。"
        ) from exc
    if not isinstance(info, dict):
        raise DownloadFailure("extractor_failed", "下载器返回了无效的视频信息。")

    if info.get("_type") in {"playlist", "multi_video"} or isinstance(info.get("entries"), list):
        raise DownloadFailure(
            "playlist_not_supported", "第一版只处理单个视频，不下载播放列表。"
        )
    if info.get("is_live") or info.get("live_status") == "is_live":
        raise DownloadFailure(
            "live_not_supported", "第一版不处理正在直播的内容。"
        )

    extractor = str(info.get("extractor_key") or info.get("extractor") or "")
    extractor_normalized = re.sub(r"[^a-z0-9]", "", extractor.casefold())
    if not any(token in extractor_normalized for token in EXPECTED_EXTRACTORS[platform]):
        raise DownloadFailure(
            "redirect_unverified", "分享链接没有解析成可确认的单个目标平台视频。"
        )
    resolved_host = resolved_metadata_host(info)
    if not resolved_host or not any(
        host_matches(resolved_host, domain) for domain in PLATFORM_DOMAINS[platform]
    ):
        raise DownloadFailure(
            "redirect_unverified",
            "分享链接没有解析到可确认的目标平台正式域名。",
        )
    info["_verified_source_host"] = resolved_host

    required = (info.get("id"), info.get("title"))
    if not all(str(value or "").strip() for value in required):
        raise DownloadFailure(
            "redirect_unverified", "无法确认唯一的视频 ID 和标题，已停止下载。"
        )
    if platform == "Douyin":
        uploader = info.get("uploader") or info.get("channel") or info.get("creator")
        duration = info.get("duration")
        if not str(uploader or "").strip() or not isinstance(duration, (int, float)):
            raise DownloadFailure(
                "redirect_unverified", "抖音分享链接未返回完整的作者和时长，已停止下载。"
            )

    selected = selected_audio_format(info)
    if info.get("has_drm") or selected.get("has_drm"):
        raise DownloadFailure(
            "drm_or_paid_restricted", "该内容包含 DRM，Skill 不会尝试绕过。"
        )
    source_codec = str(selected.get("acodec") or "").strip()
    if not source_codec or source_codec.casefold() == "none":
        raise DownloadFailure("no_audio", "页面没有暴露可下载的音轨。")
    return info


def selected_audio_format(info: dict[str, Any]) -> dict[str, Any]:
    requested = info.get("requested_downloads")
    if isinstance(requested, list):
        for item in requested:
            if isinstance(item, dict):
                codec = str(item.get("acodec") or "").casefold()
                if codec and codec != "none":
                    return item
    return info


def resolved_metadata_host(info: dict[str, Any]) -> str | None:
    domain = str(info.get("webpage_url_domain") or "").strip().rstrip(".").lower()
    if domain and not CONTROL_RE.search(domain):
        return domain
    webpage_url = str(info.get("webpage_url") or "").strip()
    if webpage_url:
        try:
            parsed = urlsplit(webpage_url)
        except ValueError:
            return None
        if parsed.scheme.lower() == "https" and parsed.hostname:
            return parsed.hostname.rstrip(".").lower()
    return None


def safe_text(value: Any, *, limit: int = 500) -> str | None:
    if value is None:
        return None
    text = CONTROL_RE.sub(" ", str(value))
    text = re.sub(r"\s+", " ", text).strip()
    return text[:limit] or None


def safe_number(value: Any) -> int | float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return value
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def normalize_codec(codec: Any) -> str | None:
    raw = str(codec or "").strip().casefold()
    if not raw or raw == "none":
        return None
    aliases = (
        (("mp4a", "aac"), "aac"),
        (("opus",), "opus"),
        (("vorbis",), "vorbis"),
        (("mp3",), "mp3"),
        (("flac",), "flac"),
        (("alac",), "alac"),
        (("eac3", "ec-3"), "eac3"),
        (("ac3", "ac-3"), "ac3"),
        (("dts",), "dts"),
        (("pcm",), "pcm"),
    )
    for prefixes, canonical in aliases:
        if any(raw.startswith(prefix) for prefix in prefixes):
            return canonical
    return raw.split(".", 1)[0]


def normalize_aac_profile(value: Any) -> str | None:
    raw = re.sub(r"[^a-z0-9]", "", str(value or "").casefold())
    aliases = {
        "lc": "lc",
        "aaclc": "lc",
        "heaac": "he-aac",
        "heaacv2": "he-aac-v2",
    }
    return aliases.get(raw)


def source_aac_profile(codec: Any) -> str | None:
    raw = str(codec or "").casefold()
    if raw.startswith("mp4a.40.2"):
        return "lc"
    if raw.startswith("mp4a.40.5"):
        return "he-aac"
    if raw.startswith("mp4a.40.29"):
        return "he-aac-v2"
    return None


def pcm_bit_depth(codec: Any, sample_format: Any = None) -> int | None:
    for value in (codec, sample_format):
        match = re.search(r"(?:pcm_[suf]?|^s|^u|^flt)([0-9]{1,2})", str(value or "").casefold())
        if match:
            return int(match.group(1))
    return None


def ensure_audio_invariants(
    info: dict[str, Any],
    probe: dict[str, Any],
    *,
    error_code: str,
) -> None:
    selected = selected_audio_format(info)
    source_codec = selected.get("acodec")
    final_codec = probe.get("codec")
    mismatch = normalize_codec(source_codec) != normalize_codec(final_codec)

    source_rate = safe_number(selected.get("asr"))
    final_rate = safe_number(probe.get("sample_rate_hz"))
    if source_rate and final_rate and int(source_rate) != int(final_rate):
        mismatch = True

    source_channels = safe_number(selected.get("audio_channels"))
    final_channels = safe_number(probe.get("channels"))
    if source_channels and final_channels and int(source_channels) != int(final_channels):
        mismatch = True

    source_duration_for_rate = safe_number(selected.get("duration")) or safe_number(
        info.get("duration")
    )
    source_size = safe_number(selected.get("filesize")) or safe_number(
        selected.get("filesize_approx")
    )
    source_bitrate = safe_number(selected.get("abr"))
    if (
        not source_bitrate
        and source_size
        and source_duration_for_rate
        and str(selected.get("vcodec") or "none").casefold() == "none"
    ):
        source_bitrate = float(source_size) * 8 / float(source_duration_for_rate) / 1000

    final_bitrate = safe_number(probe.get("bitrate_kbps"))
    if not final_bitrate:
        final_size = safe_number(probe.get("size_bytes"))
        final_duration_for_rate = safe_number(probe.get("duration_seconds"))
        if final_size and final_duration_for_rate:
            final_bitrate = float(final_size) * 8 / float(final_duration_for_rate) / 1000
    if source_bitrate and final_bitrate:
        bitrate_ratio = float(final_bitrate) / float(source_bitrate)
        if not 0.85 <= bitrate_ratio <= 1.20:
            mismatch = True
    elif error_code == "existing_outdated":
        raise DownloadFailure(
            "existing_unverified",
            "现有同 ID 文件缺少可比的码率信息，无法确认仍是当前最高音质；未覆盖。",
        )

    source_duration = safe_number(selected.get("duration")) or safe_number(info.get("duration"))
    final_duration = safe_number(probe.get("duration_seconds"))
    if source_duration and final_duration:
        tolerance = max(2.0, float(source_duration) * 0.02)
        if abs(float(source_duration) - float(final_duration)) > tolerance:
            mismatch = True

    if normalize_codec(source_codec) == "pcm":
        source_depth = pcm_bit_depth(source_codec)
        final_depth = safe_number(probe.get("bits_per_raw_sample")) or safe_number(
            probe.get("bits_per_sample")
        ) or pcm_bit_depth(final_codec, probe.get("sample_format"))
        if source_depth and final_depth and int(source_depth) != int(final_depth):
            mismatch = True

    expected_aac_profile = source_aac_profile(source_codec)
    final_aac_profile = normalize_aac_profile(probe.get("profile"))
    if expected_aac_profile and final_aac_profile and expected_aac_profile != final_aac_profile:
        mismatch = True

    if mismatch:
        if error_code == "existing_outdated":
            message = "现有同 ID 文件与当前最佳源音轨的关键参数不一致；未覆盖，请显式使用 --force。"
        else:
            message = "检测到音频编码、采样参数或时长发生意外变化，已拒绝交付。"
        raise DownloadFailure(error_code, message)


def sanitize_component(value: Any, *, fallback: str, max_chars: int) -> str:
    text = safe_text(value, limit=max_chars * 2) or fallback
    text = INVALID_FILENAME_RE.sub("_", text)
    text = re.sub(r"\s+", " ", text).strip(" .")
    if WINDOWS_RESERVED_RE.match(text):
        text = f"_{text}"
    if not text:
        text = fallback
    return text[:max_chars].rstrip(" .") or fallback


def media_marker(platform: str, media_id: Any) -> str:
    safe_platform = sanitize_component(platform, fallback="Media", max_chars=24)
    safe_id = sanitize_component(media_id, fallback="unknown", max_chars=64)
    return f" [{safe_platform}-{safe_id}]"


def find_existing(output_root: Path, marker: str) -> list[Path]:
    marker_folded = marker.casefold()
    matches: list[Path] = []
    for child in output_root.iterdir():
        if not child.is_file() or child.name.endswith((".part", ".ytdl")):
            continue
        if child.stem.casefold().endswith(marker_folded):
            resolved = child.resolve(strict=True)
            if resolved.parent != output_root:
                raise DownloadFailure(
                    "path_validation_failed", "发现指向输出目录外部的同名文件，已停止。"
                )
            matches.append(resolved)
    return matches


def probe_media(path: Path, tools: ToolPaths, env: dict[str, str]) -> dict[str, Any]:
    if not path.is_file() or path.stat().st_size <= 0:
        raise DownloadFailure("verification_failed", "下载结果为空或不存在。")
    proc = run_process(
        [
            str(tools.ffprobe),
            "-v",
            "error",
            "-show_entries",
            "format=format_name,duration,bit_rate:stream=index,codec_type,codec_name,profile,sample_fmt,bits_per_sample,bits_per_raw_sample,sample_rate,channels,bit_rate,duration",
            "-of",
            "json",
            "--",
            str(path),
        ],
        env=env,
        timeout=120,
        stage="probe",
    )
    if proc.returncode != 0:
        raise DownloadFailure("verification_failed", "FFprobe 无法验证下载结果。")
    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise DownloadFailure("verification_failed", "FFprobe 返回了无效信息。") from exc

    streams = payload.get("streams") if isinstance(payload, dict) else None
    if not isinstance(streams, list):
        raise DownloadFailure("verification_failed", "下载结果没有可验证的媒体流。")
    audio_streams = [item for item in streams if item.get("codec_type") == "audio"]
    video_streams = [item for item in streams if item.get("codec_type") == "video"]
    if not audio_streams:
        raise DownloadFailure("verification_failed", "下载结果不包含音轨。")
    if len(audio_streams) != 1:
        raise DownloadFailure("verification_failed", "下载结果包含多条音轨，无法确认唯一交付音轨。")
    if video_streams:
        raise DownloadFailure("verification_failed", "下载结果仍包含视频轨，未作为音频交付。")

    audio = audio_streams[0]
    container = payload.get("format") if isinstance(payload.get("format"), dict) else {}
    bitrate = safe_number(audio.get("bit_rate")) or safe_number(container.get("bit_rate"))
    return {
        "codec": safe_text(audio.get("codec_name"), limit=80),
        "profile": safe_text(audio.get("profile"), limit=80),
        "sample_format": safe_text(audio.get("sample_fmt"), limit=80),
        "bits_per_sample": safe_number(audio.get("bits_per_sample")),
        "bits_per_raw_sample": safe_number(audio.get("bits_per_raw_sample")),
        "container": safe_text(container.get("format_name"), limit=120),
        "bitrate_kbps": round(float(bitrate) / 1000, 2) if bitrate else None,
        "sample_rate_hz": safe_number(audio.get("sample_rate")),
        "channels": safe_number(audio.get("channels")),
        "duration_seconds": safe_number(audio.get("duration"))
        or safe_number(container.get("duration")),
        "size_bytes": path.stat().st_size,
    }


def parse_after_move(stdout: str, staging: Path) -> Path:
    prefix = "after_move:"
    candidates: list[Path] = []
    for line in stdout.splitlines():
        encoded = line[len(prefix) :] if line.startswith(prefix) else line
        try:
            value = json.loads(encoded)
        except json.JSONDecodeError:
            continue
        if isinstance(value, str):
            candidates.append(Path(value))

    if not candidates:
        candidates = [
            item
            for item in staging.iterdir()
            if item.is_file() and not item.name.endswith((".part", ".ytdl"))
        ]
    if len(candidates) != 1:
        raise DownloadFailure(
            "verification_failed", "下载器没有返回唯一的最终音频文件。"
        )

    candidate = candidates[0]
    if not candidate.is_absolute():
        candidate = staging / candidate
    resolved = candidate.resolve(strict=True)
    if resolved.parent != staging:
        raise DownloadFailure(
            "path_validation_failed", "下载结果超出了临时目录，已停止。"
        )
    return resolved


def utf16_units(value: str) -> int:
    return len(value.encode("utf-16-le")) // 2


def truncate_utf16(value: str, max_units: int) -> str:
    result: list[str] = []
    used = 0
    for character in value:
        units = utf16_units(character)
        if used + units > max_units:
            break
        result.append(character)
        used += units
    return "".join(result)


def truncate_filesystem_bytes(value: str, max_bytes: int) -> str:
    result: list[str] = []
    used = 0
    for character in value:
        encoded = os.fsencode(character)
        if used + len(encoded) > max_bytes:
            break
        result.append(character)
        used += len(encoded)
    return "".join(result)


def posix_filename_budget(output_root: Path | None) -> int:
    name_max = POSIX_DEFAULT_NAME_MAX_BYTES
    path_max = POSIX_DEFAULT_PATH_MAX_BYTES
    if output_root is not None:
        try:
            detected_name_max = int(os.pathconf(output_root, "PC_NAME_MAX"))
            if detected_name_max > 0:
                name_max = detected_name_max
        except (AttributeError, OSError, ValueError):
            pass
        try:
            detected_path_max = int(os.pathconf(output_root, "PC_PATH_MAX"))
            if detected_path_max > 0:
                path_max = detected_path_max
        except (AttributeError, OSError, ValueError):
            pass
        path_max -= len(os.fsencode(str(output_root))) + 1
    return min(name_max, path_max)


def make_final_name(
    info: dict[str, Any],
    platform: str,
    extension: str,
    output_root: Path | None = None,
) -> str:
    marker = media_marker(platform, info.get("id"))
    extension = re.sub(r"[^a-zA-Z0-9]", "", extension)[:12].lower() or "audio"
    title = sanitize_component(info.get("title"), fallback="audio", max_chars=512)
    if os.name == "nt":
        filename_budget = 220
        if output_root is not None:
            filename_budget = SAFE_TOTAL_PATH_UTF16_UNITS - utf16_units(str(output_root)) - 1
        fixed_units = utf16_units(marker) + utf16_units(extension) + 1
        title_budget = filename_budget - fixed_units
        if title_budget < utf16_units("audio"):
            raise DownloadFailure(
                "invalid_output_dir", "输出目录路径过深，无法生成安全的最终文件名。"
            )
        title = truncate_utf16(title, title_budget)
    else:
        filename_budget = posix_filename_budget(output_root)
        fixed_bytes = len(os.fsencode(f"{marker}.{extension}"))
        title_budget = filename_budget - fixed_bytes
        if title_budget < len(os.fsencode("audio")):
            raise DownloadFailure(
                "invalid_output_dir", "输出目录路径过深，无法生成安全的最终文件名。"
            )
        title = truncate_filesystem_bytes(title, title_budget)
    title = title.rstrip(" .") or "audio"
    return f"{title}{marker}.{extension}"


def move_without_overwrite(source: Path, target: Path) -> None:
    """Commit a same-filesystem file without replacing a racing target."""
    if os.name == "nt":
        os.rename(source, target)
        return
    os.link(source, target, follow_symlinks=False)
    try:
        source.unlink()
    except OSError:
        # The target is already a verified hard link. TemporaryDirectory will
        # make a best effort to remove the staging name during cleanup.
        pass


def result_payload(
    *,
    status: str,
    path: Path,
    info: dict[str, Any],
    platform: str,
    probe: dict[str, Any],
    cookies_used: bool,
    versions: dict[str, str],
    verification_basis: str,
) -> dict[str, Any]:
    selected = selected_audio_format(info)
    source_codec = safe_text(selected.get("acodec"), limit=80)
    source_ext = safe_text(selected.get("ext"), limit=40)
    final_codec = probe.get("codec")
    codec_preserved = normalize_codec(source_codec) == normalize_codec(final_codec)
    remuxed = bool(source_ext and path.suffix and source_ext.casefold() != path.suffix[1:].casefold())
    return {
        "status": status,
        "path": str(path),
        "title": safe_text(info.get("title")),
        "uploader": safe_text(
            info.get("uploader") or info.get("channel") or info.get("creator")
        ),
        "duration_seconds": safe_number(info.get("duration")) or probe.get("duration_seconds"),
        "platform": platform,
        "id": safe_text(info.get("id"), limit=160),
        "source_host": safe_text(
            info.get("_verified_source_host") or info.get("webpage_url_domain"),
            limit=160,
        ),
        "source_format_id": safe_text(selected.get("format_id"), limit=160),
        "source_codec": source_codec,
        "source_container": source_ext,
        "codec": final_codec,
        "container": probe.get("container") or path.suffix[1:],
        "bitrate_kbps": probe.get("bitrate_kbps")
        or safe_number(selected.get("abr")),
        "sample_rate_hz": probe.get("sample_rate_hz")
        or safe_number(selected.get("asr")),
        "channels": probe.get("channels")
        or safe_number(selected.get("audio_channels")),
        "size_bytes": probe.get("size_bytes"),
        "source_codec_preserved": codec_preserved,
        "remuxed": remuxed,
        "transcoded": not codec_preserved,
        "verification_basis": verification_basis,
        "used_browser_cookies": cookies_used,
        "tools": versions,
    }


def ensure_output_root(raw_path: str | None) -> Path:
    try:
        output = Path(raw_path).expanduser() if raw_path else DEFAULT_OUTPUT_DIR
    except (OSError, ValueError) as exc:
        raise DownloadFailure("invalid_output_dir", "输出目录格式无效。") from exc
    if raw_path and not output.is_absolute():
        raise DownloadFailure("invalid_output_dir", "自定义输出目录必须是绝对路径。")
    try:
        candidate = output.resolve(strict=False)
        if candidate == Path(candidate.anchor):
            raise DownloadFailure("invalid_output_dir", "不能把磁盘根目录作为输出目录。")
        candidate.mkdir(parents=True, exist_ok=True)
        root = candidate.resolve(strict=True)
    except DownloadFailure:
        raise
    except (OSError, ValueError) as exc:
        raise DownloadFailure("invalid_output_dir", "无法创建或访问输出目录。") from exc
    if not root.is_dir():
        raise DownloadFailure("invalid_output_dir", "输出路径不是目录。")
    if root == Path(root.anchor):
        raise DownloadFailure("invalid_output_dir", "不能把磁盘根目录作为输出目录。")
    return root


def download_audio(
    url: str,
    *,
    output_dir: str | None,
    cookie_profile: str | None,
    force: bool,
    expected_platform: str | None = None,
) -> dict[str, Any]:
    platform, input_host = validate_url(url)
    if expected_platform is not None and platform != expected_platform:
        labels = {"Bilibili": "B站", "Douyin": "抖音", "YouTube": "YouTube"}
        raise DownloadFailure(
            "unsupported_platform",
            f"该站点专用 Skill 只处理{labels.get(expected_platform, expected_platform)}链接。",
        )
    cookie_profile = validate_cookie_profile(cookie_profile)
    output_root = ensure_output_root(output_dir)
    tools = resolve_tools(platform)
    env = child_environment(tools)
    versions = tool_versions(tools, env)
    info = load_metadata(url, platform, tools, env, cookie_profile)
    marker = media_marker(platform, info.get("id"))
    existing = find_existing(output_root, marker)
    if len(existing) > 1:
        raise DownloadFailure(
            "existing_conflict", "同一平台视频 ID 对应多个现有文件，请先人工核对。"
        )
    if existing and not force:
        probe = probe_media(existing[0], tools, env)
        ensure_audio_invariants(info, probe, error_code="existing_outdated")
        payload = result_payload(
            status="already_exists",
            path=existing[0],
            info=info,
            platform=platform,
            probe=probe,
            cookies_used=cookie_profile is not None,
            versions=versions,
            verification_basis="current_source_vs_existing_file",
        )
        payload["message"] = "同一视频的音频文件已经存在，未覆盖。"
        return payload

    with tempfile.TemporaryDirectory(prefix=".download-best-audio-", dir=output_root) as temp:
        staging = Path(temp).resolve(strict=True)
        args = yt_dlp_common_args(tools, cookie_profile)
        args.extend(
            [
                "--no-overwrites",
                "--windows-filenames",
                "--no-progress",
                "--newline",
                "-f",
                "bestaudio/best",
                "-x",
                "--audio-format",
                "best",
                "--print",
                "after_move:%(filepath)j",
                "-o",
                str(staging / "source.%(ext)s"),
                "--",
                url,
            ]
        )
        proc = run_process(args, env=env, timeout=DOWNLOAD_TIMEOUT_SECONDS, stage="download")
        if proc.returncode != 0:
            raise classify_failure(
                f"{proc.stderr}\n{proc.stdout}",
                cookies_used=cookie_profile is not None,
                stage="download",
            )

        candidate = parse_after_move(proc.stdout, staging)
        probe = probe_media(candidate, tools, env)
        ensure_audio_invariants(info, probe, error_code="unexpected_transcode")

        extension = candidate.suffix[1:]
        final_name = make_final_name(info, platform, extension, output_root)
        final_path = (output_root / final_name)
        if final_path.parent.resolve(strict=True) != output_root:
            raise DownloadFailure("path_validation_failed", "最终文件路径超出输出目录。")

        replace_target = final_path
        if replace_target.exists() and not force:
            existing_probe = probe_media(replace_target, tools, env)
            ensure_audio_invariants(info, existing_probe, error_code="existing_outdated")
            payload = result_payload(
                status="already_exists",
                path=replace_target,
                info=info,
                platform=platform,
                probe=existing_probe,
                cookies_used=cookie_profile is not None,
                versions=versions,
                verification_basis="current_source_vs_existing_file",
            )
            payload["message"] = "目标文件已经存在，未覆盖。"
            return payload

        backup_path: Path | None = None
        previous_path = existing[0] if existing and force else None
        try:
            if previous_path is not None:
                backup_path = output_root / (
                    f".download-best-audio-backup-{secrets.token_hex(12)}"
                    f"{previous_path.suffix}"
                )
                os.rename(previous_path, backup_path)
            if force:
                os.replace(candidate, replace_target)
            else:
                move_without_overwrite(candidate, replace_target)
        except FileExistsError:
            race_probe = probe_media(replace_target, tools, env)
            ensure_audio_invariants(info, race_probe, error_code="existing_outdated")
            payload = result_payload(
                status="already_exists",
                path=replace_target,
                info=info,
                platform=platform,
                probe=race_probe,
                cookies_used=cookie_profile is not None,
                versions=versions,
                verification_basis="current_source_vs_existing_file",
            )
            payload["message"] = "并发下载已先生成同一目标文件，未覆盖。"
            return payload
        except OSError as exc:
            details: dict[str, Any] = {}
            if backup_path is not None and backup_path.exists() and previous_path is not None:
                try:
                    os.replace(backup_path, previous_path)
                except OSError:
                    details["recovery_path"] = str(backup_path)
            raise DownloadFailure(
                "commit_failed",
                "验证成功，但无法提交最终音频文件。",
                details,
            ) from exc

        try:
            final_probe = probe_media(replace_target, tools, env)
            ensure_audio_invariants(info, final_probe, error_code="unexpected_transcode")
        except DownloadFailure as failure:
            failed_new = staging / f"failed-new{replace_target.suffix}"
            try:
                if replace_target.exists():
                    os.replace(replace_target, failed_new)
                if backup_path is not None and backup_path.exists() and previous_path is not None:
                    os.replace(backup_path, previous_path)
            except OSError:
                if backup_path is not None and backup_path.exists():
                    failure.details["recovery_path"] = str(backup_path)
                elif replace_target.exists():
                    failure.details["recovery_path"] = str(replace_target)
            raise

        backup_cleanup_pending: str | None = None
        if backup_path is not None and backup_path.exists():
            try:
                backup_path.unlink()
            except OSError:
                backup_cleanup_pending = str(backup_path)
        payload = result_payload(
            status="downloaded",
            path=replace_target,
            info=info,
            platform=platform,
            probe=final_probe,
            cookies_used=cookie_profile is not None,
            versions=versions,
            verification_basis="downloaded_source_vs_final_file",
        )
        payload["source_host"] = payload.get("source_host") or input_host
        payload["message"] = "已保存当前可访问的最佳源音轨。"
        if backup_cleanup_pending:
            payload["previous_file_backup"] = backup_cleanup_pending
            payload["message"] += " 旧文件备份未能清理，已保留其恢复路径。"
        return payload


def decode_base64_text(encoded: str, *, label: str, max_bytes: int) -> str:
    if len(encoded) > max_bytes * 2 or not re.fullmatch(r"[A-Za-z0-9+/]*={0,2}", encoded):
        raise DownloadFailure("invalid_arguments", f"{label}的 Base64 参数无效。")
    try:
        raw = base64.b64decode(encoded, validate=True)
        value = raw.decode("utf-8")
    except (binascii.Error, UnicodeDecodeError) as exc:
        raise DownloadFailure("invalid_arguments", f"{label}的 Base64 参数无效。") from exc
    if len(raw) > max_bytes:
        raise DownloadFailure("invalid_arguments", f"{label}参数过长。")
    return value


def choose_cli_text(
    plain: str | None,
    encoded: str | None,
    *,
    label: str,
    max_bytes: int,
    required: bool = False,
) -> str | None:
    if plain is not None and encoded is not None:
        raise DownloadFailure("invalid_arguments", f"{label}只能使用一种传入方式。")
    value = plain
    if encoded is not None:
        value = decode_base64_text(encoded, label=label, max_bytes=max_bytes)
    if required and value is None:
        raise DownloadFailure("invalid_arguments", f"缺少{label}。")
    return value


def build_parser() -> JsonArgumentParser:
    parser = JsonArgumentParser(
        description="Download one source-quality audio track from Douyin, Bilibili, or YouTube."
    )
    parser.add_argument("url", nargs="?", help="One supported HTTPS video URL")
    parser.add_argument("--url-base64", help=argparse.SUPPRESS)
    parser.add_argument("--output-dir", help="Absolute output directory")
    parser.add_argument("--output-dir-base64", help=argparse.SUPPRESS)
    parser.add_argument(
        "--cookies-from-browser",
        dest="cookie_profile",
        help="Use an explicitly authorized Chrome profile for this run only",
    )
    parser.add_argument(
        "--cookies-from-browser-base64",
        dest="cookie_profile_base64",
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--expected-platform",
        choices=tuple(PLATFORM_DOMAINS),
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Replace the existing file for the same platform video ID",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    try:
        args = build_parser().parse_args(argv)
        url = choose_cli_text(
            args.url,
            args.url_base64,
            label="链接",
            max_bytes=4096,
            required=True,
        )
        output_dir = choose_cli_text(
            args.output_dir,
            args.output_dir_base64,
            label="输出目录",
            max_bytes=4096,
        )
        cookie_profile = choose_cli_text(
            args.cookie_profile,
            args.cookie_profile_base64,
            label="浏览器配置",
            max_bytes=256,
        )
        payload = download_audio(
            url or "",
            output_dir=output_dir,
            cookie_profile=cookie_profile,
            force=args.force,
            expected_platform=args.expected_platform,
        )
        emit(payload)
        return 0
    except DownloadFailure as exc:
        payload = {"status": "failed", "error_code": exc.error_code, "message": exc.message}
        payload.update(exc.details)
        if exc.error_code in {
            "dependency_missing",
            "dependency_unavailable",
            "extractor_failed",
            "access_denied",
            "download_failed",
            "postprocessing_failed",
        }:
            payload.setdefault("tools", diagnostic_versions())
        emit(payload)
        return 2
    except KeyboardInterrupt:
        emit({"status": "failed", "error_code": "cancelled", "message": "操作已取消。"})
        return 130
    except Exception:
        emit(
            {
                "status": "failed",
                "error_code": "internal_error",
                "message": "发生未预期错误，未生成正式文件。",
            }
        )
        return 3


if __name__ == "__main__":
    raise SystemExit(main())

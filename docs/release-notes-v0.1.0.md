# v0.1.0 — Initial release

Yuan Says AI's Codex Audio Download Skills package four focused Agent Skills for safely extracting and verifying the best audio stream currently available from one authorized Bilibili, Douyin, or YouTube video.

## Highlights

- Three narrowly triggered site Skills for Bilibili, Douyin, and YouTube.
- One shared deterministic runtime built on `yt-dlp`, FFmpeg, and FFprobe.
- Explicit-intent routing: bare links and requests to open or summarize a page do not download anything.
- Source-codec preservation with separate remux and transcode reporting.
- Temporary staging, output-path validation, no silent overwrite, and stable JSON error codes.
- Public access first; browser-cookie use requires permission for the current link and is never exported to a cookie file.
- Canonical repository plugin layout under `plugins/codex-audio-download-skills/`, plus current `.agents/skills` standalone installation guidance.
- English-first README, complete Simplified Chinese documentation, Issue Forms, security policy, and sanitized demo artwork.
- A 25-second fictional demo GIF and a ready-to-upload 1280×640 GitHub social preview, both branded Yuan Says AI.

## Supported runtime

- Python 3.10+
- `yt-dlp`
- FFmpeg and FFprobe
- Deno for YouTube; optional for Bilibili and Douyin

Automated tests cover Windows with Python 3.10 and 3.12, plus Ubuntu and macOS with Python 3.12. Real-site behavior still depends on platform, region, account context, and dependency versions.

## Installation

Repository marketplace:

```bash
codex plugin marketplace add Qiyuanr/codex-audio-download-skills --ref v0.1.0
codex plugin add codex-audio-download-skills@yuan-says-ai
```

The root marketplace loads the plugin from local source `./plugins/codex-audio-download-skills`. Standalone installation: copy all four directories under `plugins/codex-audio-download-skills/skills/` into either `<repo-root>/.agents/skills/` or `$HOME/.agents/skills/`, then start a new session.

## Responsible-use boundary

This project neither grants download permission nor bypasses DRM, paywalls, membership or account entitlements, or region restrictions. Process only content you own or are authorized to use, prefer official platform download/export features, and follow applicable law and platform terms.

## Validation

The release is gated on the four-platform GitHub Actions matrix, all four Skill validators, the Codex plugin validator, and the repository's privacy regression tests. The demo and social preview use fictional data only.

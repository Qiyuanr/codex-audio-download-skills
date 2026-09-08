# Security Policy

## Supported versions

| Version | Supported |
| --- | --- |
| `0.1.x` | Yes |
| `main` | Development |
| Older commits or third-party forks | No |

## Report a vulnerability privately

Do not disclose a suspected vulnerability, exploit details, credentials, signed media URLs, cookie data, or personal paths in a public issue.

1. Open this repository's **Security** tab and choose **Report a vulnerability**. The direct GitHub route is [Start a private report](https://github.com/Qiyuanr/codex-audio-download-skills/security/advisories/new).
2. If private vulnerability reporting is not available, open a minimal public issue that asks the maintainer to establish a private contact channel. Include no technical details that would expose the vulnerability or any sensitive data.
3. Provide the affected commit or version, operating system, Python version, sanitized reproduction steps, impact, and any proposed mitigation.

The maintainer will respond on a best-effort basis; this volunteer project does not promise a fixed response-time SLA. Please allow time for validation and a coordinated fix before public disclosure.

## In scope

- Shell or argument injection.
- Output-path escape, unsafe overwrite, or symlink-related file replacement.
- Exposure of cookies, browser-profile data, signed URLs, tokens, or private paths.
- Platform guard bypass that routes a URL to the wrong site wrapper.
- A validation flaw that causes video or an unexpected transcoded file to be reported as verified source audio.
- Supply-chain or packaging behavior introduced by this repository.

## Out of scope

- Availability changes or extractor breakage on third-party platforms.
- Reports that require bypassing DRM, paywalls, account entitlements, or region restrictions.
- Vulnerabilities in `yt-dlp`, FFmpeg, Deno, Python, Codex, or a video platform that are not caused by this repository.
- Social engineering, denial-of-service testing against public services, or testing with content you are not authorized to access.

## Data handling for reports

Use fictional or self-generated fixtures whenever possible. Redact usernames, absolute paths, media titles, video identifiers, query strings, cookies, tokens, and browser-profile names. Never attach downloaded media, cookie databases, or a complete raw debug log.

---

## 中文说明

首个正式标签发布前，仅维护最新 `main`。请不要在公开 Issue 中披露漏洞细节、Cookie、令牌、签名媒体链接或个人路径。优先通过仓库 **Security → Report a vulnerability** 私密报告；若该入口尚不可用，只提交一个不含技术细节的公开请求，让维护者建立私密沟通渠道。请使用虚构或自行生成的测试材料，并删除所有可识别信息。

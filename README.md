# Codex Audio Download Skills

[![Tests](https://github.com/Qiyuanr/codex-audio-download-skills/actions/workflows/tests.yml/badge.svg)](https://github.com/Qiyuanr/codex-audio-download-skills/actions/workflows/tests.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

面向 Codex 的 B站、抖音和 YouTube 单视频音频提取 Skills。

只有在用户明确说“下载音频”或“提取音频”并提供对应平台链接时才会触发。工具会尝试获取当前地区、账号权限和页面实际提供的最佳可用音轨，默认保留源编码，不把有损音频转成 FLAC 来制造“音质提升”的假象。

> **English summary**
>
> Three site-specific Codex Skills for extracting the best available source audio from a single Bilibili, Douyin, or YouTube video. They activate only on explicit download intent, preserve the source codec whenever possible, and validate the result with FFprobe. No playlist, livestream, DRM, paywall, account-entitlement, or region-restriction bypass. Use only for content you are authorized to download.

## 为什么做这个项目

很多下载脚本默认转换成 MP3、M4A 或 FLAC，但改变格式不会让已经压缩过的音频变得更清晰，还可能造成二次有损转码。

这个项目更关注：

- 获取页面当前实际提供的最佳可用音轨
- 尽量保留源音频编码，只在必要时改变封装
- 使用 FFprobe 验证最终文件确实有音轨且没有视频轨
- 避免裸链接误触发、路径越界、覆盖已有文件和 Cookie 泄露
- 将不同平台拆成独立 Skill，降低错误触发概率

## 包含的 Skills

| Skill | 识别范围 | 示例触发语 |
| --- | --- | --- |
| `download-bilibili-audio` | `bilibili.com`、`b23.tv` | `下载音频 https://www.bilibili.com/video/BV...` |
| `download-douyin-audio` | `douyin.com`、`iesdouyin.com` | `提取音频 https://v.douyin.com/...` |
| `download-youtube-audio` | `youtube.com`、`youtu.be`、`youtube-nocookie.com` | `download audio https://youtu.be/...` |
| `download-best-audio` | 三个平台的共享运行时 | 默认不参与隐式触发 |

只发送裸链接，或者要求“打开、总结、分析这个链接”，不会触发下载。

## 主要特性

- 单次只处理一个已经发布的视频
- 使用 `bestaudio/best` 选择最佳可用源
- 默认不做有损转码，并检测意外编码变化
- 下载和验证在临时目录完成，成功后才提交最终文件
- Windows 安全文件名，保留中文
- 同一平台视频 ID 已存在时直接返回，不覆盖
- 外部程序全部通过参数数组调用，不拼接 Shell 字符串
- 公开访问优先；浏览器 Cookie 仅在用户明确授权后用于当前链接
- 不导出 Cookie 文件，不记录凭据或带令牌的媒体地址
- JSON 结构化结果与稳定错误类型

## “最佳音质”是什么意思

这里的“最佳”指 yt-dlp 在当前时间、地区、页面状态和账号权限下能够识别并访问的最佳可用音轨。

它不代表平台母带、无损音源或任何账号都能获得的最高档位。平台可能只提供 AAC、Opus 等有损音频；把它转换成 FLAC 不会恢复已经损失的信息。网站接口和解析规则会变化，因此本项目不能保证每个平台长期稳定可用。

## 依赖

- Python 3.10+
- [yt-dlp](https://github.com/yt-dlp/yt-dlp)
- [FFmpeg / FFprobe](https://ffmpeg.org/)
- [Deno](https://deno.com/)（YouTube 需要；B站和抖音可选）

本仓库不附带第三方可执行文件。

Windows 10/11 可以使用 WinGet：

```powershell
winget install --id yt-dlp.yt-dlp -e
```

macOS 可使用 Homebrew：

```bash
brew install yt-dlp ffmpeg deno
```

安装后检查：

```text
yt-dlp --version
ffmpeg -version
ffprobe -version
deno --version
```

依赖和安装方式可能变化，请同时参考各项目的官方说明。

## 安装到 Codex

在 Codex 中依次运行以下安装请求：

```text
$skill-installer install https://github.com/Qiyuanr/codex-audio-download-skills/tree/main/skills/download-best-audio
$skill-installer install https://github.com/Qiyuanr/codex-audio-download-skills/tree/main/skills/download-bilibili-audio
$skill-installer install https://github.com/Qiyuanr/codex-audio-download-skills/tree/main/skills/download-douyin-audio
$skill-installer install https://github.com/Qiyuanr/codex-audio-download-skills/tree/main/skills/download-youtube-audio
```

也可以克隆仓库后，把 `skills/` 下的四个目录复制到 `$CODEX_HOME/skills`；未设置 `CODEX_HOME` 时通常是 `~/.codex/skills`。如果已有同名 Skill，请先检查差异，不要直接覆盖自己的修改。安装后重新打开 Codex 或开始一个新任务。

## 使用示例

```text
下载音频 https://www.bilibili.com/video/BV...
```

```text
提取音频 https://v.douyin.com/...
```

```text
download audio https://youtu.be/...
```

默认输出到当前用户的 `Downloads/Codex-Audio`。如果不通过 Codex 调用共享脚本，请交互式读取原始值并先编码为 Base64；不要把原始 URL 或路径直接粘贴进 Shell 命令。

```powershell
$urlBytes = [Text.Encoding]::UTF8.GetBytes((Read-Host "URL"))
$urlB64 = [Convert]::ToBase64String($urlBytes)
py -3 .\skills\download-best-audio\scripts\download_audio.py --url-base64 $urlB64
```

```bash
read -r -p 'URL: ' media_url
url_b64="$(printf '%s' "$media_url" | base64 | tr -d '\r\n')"
python3 ./skills/download-best-audio/scripts/download_audio.py --url-base64 "$url_b64"
```

指定输出目录：

```powershell
$outputBytes = [Text.Encoding]::UTF8.GetBytes((Read-Host "Absolute output path"))
$outputB64 = [Convert]::ToBase64String($outputBytes)
py -3 .\skills\download-best-audio\scripts\download_audio.py --url-base64 $urlB64 --output-dir-base64 $outputB64
```

浏览器登录状态只应在公开下载失败、确实需要登录，并且你确认有权访问和下载目标内容时使用：

```powershell
$profileBytes = [Text.Encoding]::UTF8.GetBytes((Read-Host "Chrome profile, for example chrome or chrome:Default"))
$profileB64 = [Convert]::ToBase64String($profileBytes)
py -3 .\skills\download-best-audio\scripts\download_audio.py --url-base64 $urlB64 --cookies-from-browser-base64 $profileB64
```

位置参数接口只适用于能直接构造参数数组、不经过 Shell 解析的程序调用方。不要提交浏览器 Cookie、Cookie 数据库、调试日志或带签名的媒体地址。Skill 内部使用 Base64 传递用户输入，是为了避免 Shell 注入，不是为了加密或隐藏链接。

## 当前范围

支持：

- 单个已发布视频
- B站、抖音和 YouTube 的正式链接与常见分享短链
- 最佳可用音轨下载、抽取、验证和安全落盘

不支持：

- 播放列表和批量链接
- 正在直播的内容
- DRM 内容
- 付费墙、会员权限或账号访问控制绕过
- 地区限制绕过
- 代理或第三方解析站绕过

## 隐私与安全

提交 Issue 前请删除：

- 本机用户名和绝对路径
- Cookie、令牌和浏览器资料
- 带签名的媒体 URL
- 私密或会员内容标题
- 未获授权的音频文件

建议只提交脱敏后的错误类型、依赖版本和最小复现步骤。本仓库的自动化测试使用模拟数据，不下载真实平台媒体。

## 使用边界与免责声明

本项目由维护者以非商业技术分享为目的发布，不构成下载任何内容的授权。非商业用途也不当然意味着相关下载行为符合版权法律或平台服务条款。

请仅处理你拥有版权、已取得权利人明确授权、平台明确允许下载，或适用法律明确允许处理的内容。优先使用平台提供的官方下载或导出功能。使用者应自行确认并遵守所在地法律、内容许可及平台条款：

- [YouTube Terms of Service](https://www.youtube.com/t/terms)
- [哔哩哔哩用户协议](https://www.bilibili.com/protocal/licence.html)
- [抖音用户服务协议](https://www.douyin.com/agreements/?id=6773906068725565448)

本项目不提供或鼓励绕过 DRM、付费访问控制、账号权限或地区限制。本项目与 OpenAI、哔哩哔哩、抖音、YouTube、yt-dlp 和 FFmpeg 没有隶属、授权或官方合作关系；各名称与商标归其权利人所有。

## 兼容性与测试

单元测试和打包检查在 Windows、macOS、Linux 上运行；真实站点行为仍取决于平台、地区和依赖版本。CI 不使用受版权保护的在线媒体作为固定测试素材。

```text
python -m unittest discover -s tests -v
```

## 贡献

欢迎提交经过脱敏的兼容性问题、测试和改进建议。请先阅读 [CONTRIBUTING.md](CONTRIBUTING.md)。

## License

本仓库原创代码采用 [MIT License](LICENSE)。MIT 允许下游在保留许可证的前提下复用，包括商业复用；维护者本人不通过本项目提供商业下载服务。第三方依赖适用各自许可证，详见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。

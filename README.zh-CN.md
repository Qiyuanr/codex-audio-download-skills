# Codex Audio Download Skills

[![Tests](https://github.com/Qiyuanr/codex-audio-download-skills/actions/workflows/tests.yml/badge.svg)](https://github.com/Qiyuanr/codex-audio-download-skills/actions/workflows/tests.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-3776AB.svg)](https://www.python.org/)

[English](README.md) · **简体中文**

四个可安装的 Codex Skills：从一个已获授权的 B 站、抖音或 YouTube 视频中提取页面当前可用的最佳音轨。三个站点 Skill 只有在用户明确要求“下载音频”或“提取音频”时才会触发；共享运行时使用 FFprobe 验证结果，并避免没有意义的二次有损转码。

这是 **Yuan Says AI** 的开源项目。

> 本项目不绕过 DRM、付费墙、账号权限或地区限制。请仅处理你拥有版权或已取得其他有效授权的内容。

<p align="center">
  <img src="docs/assets/demo.gif" alt="25 秒虚构脱敏演示：明确意图、安全路由、选择源音轨和验证结果" width="900">
</p>

<p align="center"><sub>这个 25 秒演示完全虚构，不发起网络请求，也不包含真实媒体、凭据、签名链接、标题或个人路径。</sub></p>

## 为什么做这个项目

把已经压缩过的音频转换成 MP3、M4A 或 FLAC，不会恢复丢失的细节，还可能增加一次有损编码。本项目更关注：

- 选择页面和 `yt-dlp` 当前实际提供的最佳音轨；
- 尽量保留源编码，只在必要时改变封装；
- 验证最终文件确实包含音轨且不包含视频轨；
- 防止裸链接误触发、输出路径越界、静默覆盖和凭据泄露；
- 保持各站点触发范围清晰，同时复用同一个经过审查的运行时。

这个仓库也是 [Agent Skill Release Kit](https://github.com/Qiyuanr/agent-skill-release-kit) 的首个公开示例。`.skill-release.yml` 只按精确路径和 SHA-256 放行程序生成的虚构 GIF；当前仓库在该工具 v0.1 规则下的审计结果为 `ready`。`ready` 只是规则集结果，不代表绝对安全。

## 包含的 Skills

| Skill | 作用 | 触发条件 |
| --- | --- | --- |
| `download-bilibili-audio` | B 站封装 | 明确下载音频意图，并提供 `bilibili.com` 或 `b23.tv` 链接 |
| `download-douyin-audio` | 抖音封装 | 明确下载音频意图，并提供 `douyin.com` 或 `iesdouyin.com` 链接 |
| `download-youtube-audio` | YouTube 封装 | 明确下载音频意图，并提供 `youtube.com`、`youtu.be` 或 `youtube-nocookie.com` 链接 |
| `download-best-audio` | 共享确定性运行时 | 仅供显式维护或直接调用；关闭隐式触发 |

只发送裸链接，或者要求打开、阅读、总结、讨论链接，**不会**触发下载。

## 快速开始

### 1. 安装运行依赖

- Python 3.10+
- [`yt-dlp`](https://github.com/yt-dlp/yt-dlp)
- [FFmpeg 和 FFprobe](https://ffmpeg.org/)
- [Deno](https://deno.com/)：YouTube 需要，B 站和抖音可选

仓库不附带第三方可执行文件。请按各依赖的官方说明完成安装，然后检查：

```text
python --version
yt-dlp --version
ffmpeg -version
ffprobe -version
deno --version
```

### 2. 安装全部四个 Skills

#### 方式 A：仓库插件 marketplace

仓库在 `plugins/codex-audio-download-skills/` 提供 canonical 插件目录，并在 `.agents/plugins/marketplace.json` 提供仓库 marketplace。安装固定的 `v0.1.0` 标签：

```bash
codex plugin marketplace add Qiyuanr/codex-audio-download-skills --ref v0.1.0
codex plugin add codex-audio-download-skills@yuan-says-ai-audio
```

安装后开始一个新的 Codex 会话。marketplace 通过仓库相对路径 `./plugins/codex-audio-download-skills` 加载插件。这是仓库 marketplace，并不表示项目已经进入 OpenAI 通用公共 Plugins Directory。以上命令会在 `v0.1.0` 标签发布后生效；安装前请自行审查源码。

#### 方式 B：独立 Skills

把 `plugins/codex-audio-download-skills/skills/` 下的**四个目录全部**复制到当前 Agent Skills 目录之一：

| 作用范围 | 目标目录 |
| --- | --- |
| 当前仓库 | `<repo-root>/.agents/skills/` |
| 当前用户的所有仓库 | `$HOME/.agents/skills/` |

四个目录必须保持同级，因为三个站点封装都会调用 `download-best-audio`。复制完成后开始新会话。之后可以用 `/skills` 查看已安装的 Skill，也可以用 `$download-youtube-audio` 等名称显式调用。

以上路径遵循当前的 [OpenAI Agent Skills 文档](https://learn.chatgpt.com/docs/build-skills)。旧版 README 曾使用 `$CODEX_HOME/skills`；新的独立安装请使用 `.agents/skills`。

### 3. 明确说出下载意图

```text
下载这个我有权处理的 YouTube 单视频音频：<粘贴链接>
```

```text
提取这个已获授权的 B 站单视频音频：<粘贴链接>
```

如果只粘贴链接，或者要求 Codex 总结链接，Skills 会保持不触发。

## “最佳音频”是什么意思

“最佳”是指 `yt-dlp` 在当时、当前地区和当前账号权限下，能从页面识别并访问到的最高排序音轨。它不代表平台母带、无损源，或所有账号都能获得的音质档位。

平台经常只提供 AAC 或 Opus。把这些音轨转成 FLAC 无法恢复已经丢失的信息。解析规则也会随平台变化，因此无法保证真实站点始终可用。

## 行为与安全控制

- 每次只处理一个已经发布的视频。
- 使用 `bestaudio/best`，拒绝仅播放列表链接和正在直播的内容。
- 在临时目录中下载并验证，成功后才提交最终文件。
- 尽量保留源编码，并把换封装与转码分别报告。
- 生成 Windows 安全文件名，同时尽量保留 Unicode。
- 除非直接调用方显式启用强制模式，否则不覆盖已有文件。
- 使用参数数组和 `shell=False` 启动外部程序。
- 先尝试公开访问；只有用户针对当前链接授权后才可使用浏览器 Cookie。
- 不导出 Cookie 文件，也不会有意记录凭据或带签名的媒体地址。
- 返回结构化 JSON 和稳定错误码。

## 兼容性

### Codex 与 ChatGPT 使用界面

| 安装方式 | 支持界面 | 说明 |
| --- | --- | --- |
| 独立 Agent Skills | ChatGPT 桌面端、Codex CLI、Codex IDE 扩展 | OpenAI 文档说明独立 Skills 可跨这些界面使用，请采用上面的 `.agents/skills` 路径。 |
| 仓库插件 marketplace | Codex CLI | 使用上面的命令添加 marketplace 和插件。 |
| 仓库插件 marketplace | ChatGPT 桌面端 Work 模式 | 桌面端会从 `.agents/plugins/marketplace.json` 发现仓库 marketplace；重启应用后，从 Plugins Directory 安装。 |
| 仓库插件 marketplace | 其他界面 | 本地和仓库 marketplace 的可用性因界面而异；不可用时请采用独立 Skills。 |

界面能力可能更新，请以 OpenAI 当前的 [Skills](https://learn.chatgpt.com/docs/build-skills) 和[插件打包](https://developers.openai.com/plugins/build/plugins)文档为准。

### 运行环境与 CI

| 环境 | CI 覆盖 | 运行说明 |
| --- | --- | --- |
| Windows | Python 3.10 和 3.12 | 默认写入当前用户的 Downloads 目录，并启用 Windows 安全路径检查。 |
| Ubuntu | Python 3.12 | 测试 POSIX 路径和文件名限制。 |
| macOS | Python 3.12 | 使用 POSIX 运行时，依赖需另行安装。 |

单元测试使用模拟数据和自行生成的数据，CI 不下载受版权保护的平台媒体。

## 当前范围

支持：

- 每次请求处理一个已发布视频；
- B 站、抖音和 YouTube 的常规视频链接与常见分享短链；
- 最佳可用音轨选择、提取、验证和安全落盘。

不支持：

- 播放列表、批量链接或正在直播的内容；
- DRM 内容；
- 绕过付费墙、会员、账号权限或地区限制；
- 使用代理或第三方解析站绕过限制。

## 直接调用运行时

通过 Skill 运行时，Codex 会处理输入传输。如果直接调用脚本，应交互式读取用户输入，在内存中编码为 UTF-8 Base64，然后只把编码后的值交给进程。

PowerShell：

```powershell
$mediaUrl = Read-Host "Authorized video URL"
$urlBase64 = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($mediaUrl))
py -3 .\plugins\codex-audio-download-skills\skills\download-best-audio\scripts\download_audio.py --url-base64 $urlBase64
```

Bash：

```bash
read -r -p 'Authorized video URL: ' media_url
url_base64="$(printf '%s' "$media_url" | base64 | tr -d '\r\n')"
python3 ./plugins/codex-audio-download-skills/skills/download-best-audio/scripts/download_audio.py --url-base64 "$url_base64"
```

Base64 只是参数传输措施，并不是加密。不要把原始 URL、输出路径或浏览器资料直接拼进 Shell 命令。位置参数接口只适用于能直接构造参数数组、不经过 Shell 解析的调用方。

## 隐私、安全与负责任使用

提交 Issue 前，请删除用户名、绝对路径、Cookie、Token、浏览器资料、签名媒体 URL、私密内容标题和下载的媒体文件。只提交脱敏后的错误码、依赖版本和最小复现步骤。私密漏洞报告方式和支持版本策略见 [SECURITY.md](SECURITY.md)。

本项目不构成下载任何内容的授权。非商业用途也不当然符合版权法律或平台条款。请优先使用平台官方的下载或导出能力，并为每一项内容确认许可、授权、适用法律及平台条款：

- [YouTube 服务条款](https://www.youtube.com/t/terms)
- [哔哩哔哩用户协议](https://www.bilibili.com/protocal/licence.html)
- [抖音用户服务协议](https://www.douyin.com/agreements/?id=6773906068725565448)

本项目与 OpenAI、哔哩哔哩、抖音、YouTube、`yt-dlp` 和 FFmpeg 没有隶属、授权或官方合作关系；名称与商标归各自权利人所有。

## 开发

```text
python -m compileall -q plugins/codex-audio-download-skills/skills scripts tests
python -m unittest discover -s tests -v
```

插件打包还可以使用 OpenAI 内置 `plugin-creator` 的校验器检查；四个 Skill 目录应分别通过 `skill-creator` 的 `quick_validate.py`。贡献与隐私检查表见 [CONTRIBUTING.md](CONTRIBUTING.md)。

可直接上传到 GitHub 的社交预览图位于 [docs/assets/social-preview.png](docs/assets/social-preview.png)。它与 GIF 的底图均以无文字方式生成，再由 [scripts/generate_demo_assets.py](scripts/generate_demo_assets.py) 加入精确的虚构文案和确定性尺寸。

## 发布版本

首个标签版本的说明见 [docs/release-notes-v0.1.0.md](docs/release-notes-v0.1.0.md)。

## License

仓库原创代码采用 [MIT License](LICENSE)。第三方依赖继续适用各自许可证，详见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。

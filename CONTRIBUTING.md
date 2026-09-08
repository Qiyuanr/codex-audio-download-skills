# Contributing

Thanks for improving this Yuan Says AI project's reliability, safety, tests, documentation, or platform compatibility.

## Before opening an issue

- Use the Bug report or Feature request Issue Form.
- Confirm that you are authorized to access and process the content used for reproduction.
- Prefer the stable `error_code`, dependency versions, and the smallest reproducible sequence.
- Replace every URL, video identifier, title, username, and absolute path with a fictional placeholder.
- Never upload downloaded audio or video, cookie databases, browser-profile data, tokens, signed media URLs, or complete raw debug logs.
- Report security-sensitive behavior privately by following [SECURITY.md](SECURITY.md).

## Pull requests

1. Keep each site Skill's trigger narrow. A bare link must never initiate a download.
2. Preserve the one-published-video scope and do not add DRM, paywall, account-entitlement, or region-restriction bypasses.
3. Pass external-command arguments as an array. Do not interpolate user-controlled strings into a shell command.
4. Use mocks, fictional data, or media you generated yourself. Do not commit third-party copyrighted media or include it in CI artifacts.
5. Update both `README.md` and `README.zh-CN.md` when behavior, installation, compatibility, or safety guidance changes.
6. Keep `plugins/codex-audio-download-skills/.codex-plugin/plugin.json`, `.agents/plugins/marketplace.json`, and release notes consistent when packaging changes.
7. Keep installation examples pinned to the intended release tag (`v0.1.0` for the first release), not a mutable branch.
8. Regenerate `docs/assets/demo.gif` and `docs/assets/social-preview.png` with `scripts/generate_demo_assets.py` only from original, text-free, fictional artwork. Do not commit the temporary source plates.

Run the repository checks before submitting:

```text
python -m compileall -q plugins/codex-audio-download-skills/skills scripts tests
python -m unittest discover -s tests -v
```

If your Codex installation includes the bundled validators, run `plugin-creator` against `plugins/codex-audio-download-skills/` and run `skill-creator`'s `quick_validate.py` once for each of the four folders under `plugins/codex-audio-download-skills/skills/`.

By contributing, you confirm that you have the right to provide the contribution under this repository's MIT License.

---

## 中文贡献说明

欢迎提交可靠性、安全、测试、文档和平台兼容性改进。

- 提交前请使用对应 Issue Form，并确认复现内容已经获得访问和处理授权。
- 优先提供稳定 `error_code`、依赖版本和最小复现步骤；所有 URL、视频 ID、标题、用户名和绝对路径都应替换为虚构占位符。
- 不要上传下载的音视频、Cookie 数据库、浏览器资料、Token、签名媒体 URL 或完整原始调试日志。
- 安全漏洞按 [SECURITY.md](SECURITY.md) 私密报告。
- 裸链接不能触发下载；不得增加 DRM、付费墙、账号权限或地区限制绕过。
- 外部命令必须使用参数数组，不得把用户输入拼入 Shell 命令。
- 测试只使用 Mock、虚构数据或自行生成的媒体。
- 用户可见行为变化时同步更新英文和中文 README；打包变化时同步检查插件清单、marketplace 和发布说明。
- canonical 插件根目录是 `plugins/codex-audio-download-skills/`，首版安装示例固定到 `v0.1.0`，不要改回可变分支。
- `demo.gif` 和 `social-preview.png` 只能由无文字、完全虚构的原创底图生成，不提交临时底图。
- 提交前运行上面的编译与单元测试命令。

提交贡献即表示你有权按本仓库的 MIT License 提供该贡献。

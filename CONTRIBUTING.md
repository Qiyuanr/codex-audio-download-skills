# Contributing

欢迎提交修复、测试和兼容性改进。

## Before opening an issue

- 确认目标内容允许你访问和处理。
- 优先提交 `error_code`、依赖版本和最小复现步骤。
- 删除用户名、绝对路径、Cookie、Token、浏览器资料、签名媒体 URL，以及私密或会员内容的标题。
- 不要上传下载的音频、视频或 Cookie 数据库。

## Pull requests

1. 保持三个站点 Skill 的触发范围明确；裸链接不能自动触发下载。
2. 不增加 DRM、付费墙、账号权限或地区限制绕过。
3. 外部命令必须使用参数数组，不能拼接 Shell 字符串。
4. 测试使用模拟数据或自行生成的短媒体，不把第三方受版权保护媒体加入仓库或 CI artifacts。
5. 运行：

   ```text
   python -m unittest discover -s tests -v
   ```

提交贡献即表示你有权按本仓库的 MIT License 提供该贡献。

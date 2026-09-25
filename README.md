# Oopz 文字上屏

Windows 游戏文字 HUD。它通过社区维护的 `oopz-sdk` 收发用户手动选择的 Oopz 文字频道消息。

下载：<https://acv.k-neco.com/tools/oopz-tactical-overlay/OopzTacticalOverlay.exe>

## 使用

1. 打开并登录 Oopz，加入对应服务器的语音频道。
2. 启动 `OopzTacticalOverlay.exe`。
3. 在设置页读取服务器，并手动选择 HUD 使用的文字频道。
4. 按输入快捷键（默认 `F8`），输入内容后按 `Enter` 发送；`Esc` 取消，结束后自动回到原游戏窗口。
5. 按显示快捷键（默认 `F9`）切换 HUD 显示。

单击系统托盘图标打开设置，右键菜单退出。重复启动会打开已有程序的设置页。
升级时先从托盘退出旧版，再运行新版；原有频道、快捷键、字号、透明度和位置设置会保留。

频道只在设置页手动切换，不再读取 Oopz 窗口或自动跟随。消息历史、实时消息和发送均由 SDK 完成。

## 设置

- 点击快捷键框后，直接按下新的组合键。
- 字号使用数字输入。
- 文本透明度和 HUD 背景透明度分别调节。
- 频道、快捷键和外观集中在一个设置页，修改即时生效，并可直接预览文字效果。
- 点击“调整位置与大小…”进入编辑模式；只有点击“完成”才保存，点击“取消”恢复原位置和大小。
- 激活输入时可用鼠标滚轮查看较早消息；退出输入后自动回到最新消息。
- 实时新消息会短暂高亮；断线后自动重连并补取近期消息。
- 单条消息发送失败不会断开当前频道。托盘会提示，草稿保留到下一次在同一账号和频道按输入快捷键时恢复；程序退出后不保留草稿。
- 不会自动重发失败的消息。若网络超时导致发送结果不确定，重发前先查看频道，以免重复。
- 平时 HUD 鼠标穿透；滚轮只在 HUD 输入处于前台时接管。点击其他窗口会退出输入。

## 通信边界

- 从本机 Oopz 登录态临时读取 SDK 所需凭据，不写入工具设置或日志。
- 通过 [`oopz-sdk`](https://github.com/tangqingfeng7/Oopzbot-SDK) 的 REST 与 WebSocket 收发消息。
- 工具只保存手动选择的服务器和频道 ID，不保存 Oopz 凭据。
- 不使用 Windows UI Automation、窗口文本抓取或模拟输入发送。
- Oopz 退出登录或 SDK 登录态失效后，HUD 会断开并停止收发。

`oopz-sdk` 是社区维护的非官方早期项目；自动更新只用于检查本工具的新版本。

## 兼容性

- 支持 Windows 10/11 64 位，游戏请使用窗口化或无边框窗口模式。
- 当 Windows 拒绝切换前台窗口（例如游戏以更高权限运行）时，会保留原窗口并提示，不强制切换或改变游戏窗口大小。
- 不注入 Oopz 或游戏进程，也不读取进程内存。
- 这是社区工具，不是 Oopz 官方插件；Oopz 界面或非官方 SDK 更新后可能需要适配。

更新清单：<https://acv.k-neco.com/tools/oopz-tactical-overlay/latest.json>

## 开发

```bash
uv sync --extra dev
uv run pytest -q
```

Windows 构建：

```bash
uv run python tools/build_windows.py
```

默认执行干净构建；本地重复构建可加 `--incremental` 复用 Nuitka 编译缓存。

在专用 Windows 测试桌面运行原生窗口回归（会创建测试窗口并模拟 F8/F9、Enter/Esc 和滚轮，不连接 Oopz）：

```bash
uv run python tools/native_windows_probe.py --output artifacts/native
```

生成的程序位于 `release/OopzTacticalOverlay.exe`。构建会验证打包后的 SDK 导入；`--smoke-test` 可进一步检查界面、托盘和设置读写。

重构约定见 [重构记录](docs/rebuild.md)，验证范围见 [0.9.0 验证记录](docs/validation-0.9.0.md)。

## 许可证

MIT © 2026 RinChan，见 [`LICENSE`](LICENSE)。

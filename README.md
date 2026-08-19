# Oopz 文字上屏

Windows 游戏文字 HUD。它通过社区维护的 `oopz-sdk` 收发用户手动选择的 Oopz 文字频道消息。

下载：<https://acv.k-neco.com/tools/oopz-tactical-overlay/OopzTacticalOverlay.exe>

## 使用

1. 打开并登录 Oopz，加入对应服务器的语音频道。
2. 启动 `OopzTacticalOverlay.exe`。
3. 在设置页读取服务器，并手动选择 HUD 使用的文字频道。
4. 按输入快捷键（默认 `F8`），输入内容后按 `Enter` 发送；`Esc` 取消。
5. 按显示快捷键（默认 `F9`）切换 HUD 显示。

频道只在设置页手动切换，不再读取 Oopz 窗口或自动跟随。消息历史、实时消息和发送均由 SDK 完成。

## 设置

- 点击快捷键框后，直接按下新的组合键。
- 字号使用数字输入。
- 文本透明度和 HUD 背景透明度分别调节。
- 点击“编辑 HUD 位置与大小”进入编辑模式；只有点击“完成”才保存，点击“取消”恢复原位置和大小。
- 激活输入时可用鼠标滚轮查看较早消息；退出输入后自动回到最新消息。

## 通信边界

- 从本机 Oopz 登录态临时读取 SDK 所需凭据，不写入工具设置或日志。
- 通过 [`oopz-sdk`](https://github.com/tangqingfeng7/Oopzbot-SDK) 的 REST 与 WebSocket 收发消息。
- 工具只保存手动选择的服务器和频道 ID，不保存 Oopz 凭据。
- 不使用 Windows UI Automation、窗口文本抓取或模拟输入发送。
- Oopz 退出登录或 SDK 登录态失效后，HUD 会断开并停止收发。

`oopz-sdk` 是社区维护的非官方早期项目；自动更新只用于检查本工具的新版本。

## 兼容性

- 仅支持 Windows 和无独占全屏限制的游戏显示模式。
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

## 许可证

MIT © 2026 RinChan，见 [`LICENSE`](LICENSE)。

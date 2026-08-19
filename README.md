# Oopz 文字上屏

Windows 游戏文字 HUD。它不登录 Oopz，也不单独连接 Oopz 的服务器；频道、消息和发送动作都由正在运行的 Oopz 客户端处理。

下载：<https://acv.k-neco.com/tools/oopz-tactical-overlay/OopzTacticalOverlay.exe>

## 使用

1. 打开 Oopz，并进入需要使用的文字频道。
2. 启动 `OopzTacticalOverlay.exe`。
3. 按输入快捷键（默认 `F8`），输入内容后按 `Enter` 发送；`Esc` 取消。
4. 按显示快捷键（默认 `F9`）切换 HUD 显示。

频道由 Oopz 唯一管理：在 Oopz 中切换到哪个文字频道，HUD 就自动清空旧内容并跟随到哪个频道。

Oopz 必须保持运行。为了读取 Oopz 已渲染的消息，Oopz 若被最小化，工具会把它保留在不可见的后台渲染状态；退出工具后会恢复原来的最小化状态。

## 设置

- 点击快捷键框后，直接按下新的组合键。
- 字号使用数字输入。
- 文本透明度和 HUD 背景透明度分别调节。
- 点击“编辑 HUD 位置与大小”进入编辑模式；只有点击“完成”才保存，点击“取消”恢复原位置和大小。
- 激活输入时可用鼠标滚轮查看较早消息；退出输入后自动回到最新消息。

## 通信边界

- 不保存 Oopz 登录凭据。
- 不使用 Oopz REST API 或远程 WebSocket。
- 仅通过 Windows UI Automation 和输入事件操作本机 Oopz 客户端。
- Oopz 关闭后，HUD 会断开并停止收发。

自动更新只用于检查本工具的新版本，与 Oopz 消息通信无关。

## 兼容性

- 仅支持 Windows 和无独占全屏限制的游戏显示模式。
- 不注入 Oopz 或游戏进程，也不读取进程内存。
- 这是社区工具，不是 Oopz 官方插件；Oopz 界面更新后可能需要适配。

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

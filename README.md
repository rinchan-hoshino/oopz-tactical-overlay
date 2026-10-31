# 纸条 TypeSlip

纸条是 Windows 10/11 的 Oopz 游戏聊天浮层：在窗口化或无边框游戏里看一个文字频道，按键打字，发送后回到游戏。使用本机 Oopz 登录态和社区维护的 [oopz-sdk](https://github.com/tangqingfeng7/Oopzbot-SDK)，不保存登录凭据，不注入游戏。

[下载纸条 1.0.0](https://acv.k-neco.com/tools/oopz-tactical-overlay/OopzTacticalOverlay.exe) · 已有用户可从原启动入口自动升级，设置保持不变。

1. 打开并登录 Oopz，加入服务器的语音频道，然后启动纸条。
2. 按 `F8` 在 HUD 里选一个文字频道；输入时按 `Tab` 或输入 `#` 换频道。
3. 输入消息后按 `Enter` 发送，或按 `Esc` 取消，自动回到游戏；托盘右键打开设置。

| 操作 | 快捷键 / 手势 |
| --- | --- |
| 输入消息 | `F8`（可改） |
| 显示 / 隐藏 HUD | `F9`（可改），或托盘左键 |
| 发送 / 取消 | `Enter` / `Esc` |
| 选择频道 | 输入状态下 `Tab` 或 `#`，方向键 + `Enter` |
| 翻看历史 / 改字号 | 输入状态下滚轮 / `Ctrl` + 滚轮 |
| 移动 / 缩放 | 输入状态下拖消息区 / 右下角，松手保存，拖动中 `Esc` 撤销 |

平时鼠标穿透、不抢焦点，旧消息十秒后渐淡；断线自动重连补消息。发送失败不自动重发，草稿只在当前进程中按账号和频道保留。提示音默认关闭，只响别人新发的消息。重复启动打开设置；设置随系统明暗，HUD 始终深底浅字。Windows 拒绝切换焦点时会提示，不强制抢占游戏窗口。

开发：`python -m pip install -e '.[dev]'`，`QT_QPA_PLATFORM=offscreen pytest`。截图：`PYTHONPATH=src python tests/tools/render_ui.py`。Windows 构建：`python tools/build/build_windows.py`。更新兼容、迁移取舍与发行门槛见 [发行说明](docs/releasing.md)。

MIT © 2026 RinChan，见 [LICENSE](LICENSE)。

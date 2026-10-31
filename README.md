# 纸条 TypeSlip

纸条是 Windows 10/11 的 Oopz 游戏聊天浮层：在窗口化或无边框游戏里看一个文字频道，按键打字，发送后回到游戏。使用本机 Oopz 登录态和社区维护的 [oopz-sdk](https://github.com/tangqingfeng7/Oopzbot-SDK)，不保存登录凭据，不注入游戏。

[下载已发布版本](https://acv.k-neco.com/tools/oopz-tactical-overlay/OopzTacticalOverlay.exe) · 已有用户可从原启动入口自动升级，设置保持不变。

1. 打开并登录 Oopz，加入服务器的语音频道，然后启动纸条。
2. 按 `F8` 在 HUD 里选一个文字频道；输入时按 `Tab` 或输入 `#` 换频道。
3. 输入消息后按 `Enter`（或 `Shift+Enter`）发送；空输入按回车、再次按输入热键或按 `Esc` 退出输入，自动回到游戏；托盘右键打开设置。

| 操作 | 快捷键 / 手势 |
| --- | --- |
| 进入 / 退出输入 | `F8`（可改） |
| 显示 / 隐藏 HUD | `F9`（可改），或托盘左键 |
| 发送 / 取消 | `Enter` / `Esc` |
| 选择频道 | 输入状态下 `Tab` 或 `#`，方向键 + `Enter` |
| 翻看历史 / 改字号 | 输入状态下滚轮或拖右侧细滚动条 / `Ctrl` + 滚轮 |
| 移动 / 缩放 | 输入状态下拖消息区 / 右下角，松手保存，拖动中 `Esc` 撤销 |

翻历史时新消息不会拉走阅读位置；“回到最新消息”和滚动条均悬浮显示，出现或消失不挤动消息。输入法选字时回车不会误发。平时鼠标穿透、不抢焦点，消息保持可读；断线自动重连补消息。发送失败不自动重发，草稿只在当前进程中按账号和频道保留。新安装默认使用 64 毫秒的轻触提示音，只响别人新发的消息；已有提示音设置保留。重复启动打开设置；设置随系统明暗，可实时预览并调整字号、文字不透明度和暗角不透明度；发言人以稳定强调色和冒号区分，白色半粗正文配深色描边与投影；左下渐隐暗角默认 15%，可关闭或加深。关闭“连接后持续显示消息”后，新消息显示 8 秒、2 秒淡出，输入时可查看历史；F9 仍控制整体显隐。设置中的“调整位置与大小”可用示例消息定位，`Esc` 返回设置。Windows 拒绝切换焦点时会提示，不强制抢占游戏窗口。

开发：`python -m pip install -e '.[dev]'`，`QT_QPA_PLATFORM=offscreen pytest`。截图：`PYTHONPATH=src python tests/tools/render_ui.py`。Windows 构建：`python tools/build/build_windows.py`。更新兼容、迁移取舍与发行门槛见 [发行说明](docs/releasing.md)。

MIT © 2026 RinChan，见 [LICENSE](LICENSE)。

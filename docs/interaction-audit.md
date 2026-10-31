# 1.0.2 交互审计附录

基线：0.12.0 发布源码 `55f7cd08c0ba744535fed96a28bb95e7bc493498`（`pyproject.toml` / `__version__`），对照 1.0.1 `0e72f4be9`，修复分支 `fix/1.0.2`。
旧版依据：`main.py`、`widgets.py`、`message_widgets.py`、`intent.py`、`settings_dialog.py`、`win32_input.py` 及对应交互测试；可用 `git show 55f7cd0:src/oopz_overlay/<文件>` 复查。新版有意变更以 README、`docs/releasing.md` 的 1.0/1.0.1 记录为依据。

| 行为 | 0.12.0 实际行为 | 1.0.1 对比及 1.0.2 结论 / 验证 |
| --- | --- | --- |
| F8 从被动进入输入 | 已连线才允许；未连接提示 | 保留 1.0 离线可输入、无频道进入列表；`test_first_run_has_hud_and_no_settings` |
| 输入中再按 F8 | `main.py:_activate_overlay` 直接 return，实际上不切换 | 按本次明确需求新增切换退出，列表/调整状态也可退出；`test_activation_hotkey_toggles_and_returns_to_original_window`；原生及 exe 按键 |
| 有文字 Enter / 小键盘 Enter | strip 后发送并关闭 | 保留单行发送、归还焦点；保留 1.0 输入原文；`test_keyboard_picker_send_cancel`、`test_composition_keys_do_not_send_or_leave_input` |
| Shift+Enter | 原生 QLineEdit.returnPressed，同样发送，无多行模式 | 保留单行发送；`test_enter_and_shift_enter_send_single_line`（两种修饰键） |
| 空白 Enter | 关闭且不发送 | 修复被吞掉的空回车；空串/全空格测试；原生及 exe 空回车 |
| Esc | 清除文字、关闭并归还焦点 | 恢复退出；保留 1.0 同账号同频道内存草稿；`test_keyboard_picker_send_cancel`、原生及 exe Esc |
| 中文组合输入 Enter | preedit 非空时禁止发送 | 修复丢失的 preedit 跟踪；组合中 Return/Enter/Tab/Esc 测试；真实 Windows 中文 IME 选字回车后仍在输入，第二次回车才发 |
| 组合中的 Esc / Tab / # | 交给原生输入法/编辑器；组合 Enter 有保护 | 组合期间所有按键交还原生编辑器，防止进入频道列表或退出；同上组合测试 |
| 普通编辑、选择、复制粘贴、方向键 | 原生单行 QLineEdit | 继续原生编辑器；不替换系统编辑与输入法处理 |
| Tab / # 选频道 | 无 HUD 频道选择，设置中选择 | 保留 1.0 HUD 列表；`test_keyboard_picker_send_cancel`、`test_hash_opens_picker_without_sending` |
| 列表方向键/Enter/鼠标单击 | 设置原生组合框 | 保留原生 QListWidget 选择，选后回输入；列表滚轮选择、Ctrl+滚轮改字号是 1.0 增加 |
| F9 被动显隐 | 持久记录手动隐藏 | 保留；设置和连接变化不覆盖手动隐藏；`test_temporary_messages_allow_input_and_respect_manual_visibility`、原生及 exe F9 |
| F9 输入/调整时 | 忽略 | 保留 1.0 显隐同时退出、归还焦点及草稿；`test_f9_exits_input_restores_focus_and_preserves_draft` |
| 托盘左键 | 打开设置 | 保留 README 明示的 1.0 左键显隐 |
| 托盘右键菜单 | 只有退出 | 保留 1.0 设置+退出；exe 用实际菜单打开设置及正常退出 |
| 托盘双击/中键 | 不处理 | 继续不处理；单击语义由 Trigger 保留 |
| 重复启动 | 单实例，激活设置 | 保留；`test_legacy_local_socket_opens_existing_settings` |
| 进入输入获取焦点 | 记录原前台、置顶并 focus；失败提示 | 保留，不用 AttachThreadInput/Alt-Tab 强抢；`test_denied_focus_does_not_force_alt_tab_or_change_window_placement`；原生 F8 |
| 发送/空回车/Esc/F8 归还游戏焦点 | 前三项归还进入前窗口 | 保留前三项，新增 F8；原生及 exe 使用自建游戏替身窗口核对 HWND；初版托盘探针的隔离事故见报告 |
| 切到其他程序 | 结束输入，不强抢回游戏；旧版清草稿 | 保留结束输入、不抢焦点，保留 1.0 草稿；`test_blur_does_not_restore_focus_to_game`、原生 blur |
| 原窗口消失、最小化或前台已变化 | 不强行恢复 | 保留；`test_wheel_and_focus_return_do_not_steal_from_another_foreground`、`test_restore_window_returns_to_previous_foreground_without_making_it_topmost` |
| 被动鼠标穿透/不激活 | WS_EX_TRANSPARENT / NOACTIVATE | 保留；HUD 原生属性及原生/包内被动状态；不把预览子控件设成原生穿透窗口（已有测试） |
| 全局滚轮 | 仅输入活跃且 HUD 是前台时捕获，鼠标可在框外 | 保留前台作用域；`test_global_wheel_hook_only_consumes_vertical_wheel_while_enabled`、前台变化测试；原生框外滚轮 |
| 平滑滚动/连续滚动 | 90–180 ms OutCubic，连续滚轮累加目标 | 恢复 130 ms OutCubic 和累加目标；`test_smooth_wheel_accumulates_rapid_notches` 直接推进动画时钟验证中间帧和连续目标，旧滚轮测试等待动画后验证 |
| 触控板/高分辨率滚轮 | 比例计算，最小 1 px，忽略 0 | 修复先整除导致小增量丢失；`test_small_wheel_deltas_scroll_and_zero_does_not_change_font` |
| 拖动滚动条 | 历史区原生竖向滚动条 | 恢复右侧 8 px 浮层条，固定预留文字边距、显示时不改宽度；`test_drag_scrollbar_browses_history_without_resizing_messages` |
| 历史区 Home/End/PageUp/PageDown/上下键 | 原生 QListWidget/滚动条键盘导航 | 恢复消息区获得焦点时导航；保持输入框自身方向键编辑；`test_history_keyboard_navigation_when_messages_have_focus` |
| 最新位置收到新消息 | 跟到底部 | 保留 offset=0；`test_latest_follows_new_messages_and_button_returns_keyboard_focus` |
| 看历史收到消息/淘汰最老消息 | 保留滚动位置 | 修复按底部距离导致阅读位置改变；用首个可见消息 ID+屏幕 Y 锚定；满80条/未满测试，动画中到消息时停在最后阅读锚点（`test_new_message_stops_inflight_scroll_at_the_reading_anchor`），原生截图像素对比 |
| 回到最新消息 | 布局内导航行；点击后焦点回输入 | 改为消息区右下浮层；按钮及滚动条显隐都不参与布局；固定 offset 时逐像素一致；点击后恢复输入焦点 |
| 历史时间显示 | 导航行显示所看时间 | 保留 1.0 历史行内时间，不恢复旧导航行样式 |
| 退出输入 | 停止滚动、回最新、取消交互 | 保留；新增停止动画、清理并回滚未释放的拖动，避免下次输入跳位；`test_leaving_during_drag_does_not_resume_stale_drag` |
| 移动/缩放 | 独立编辑条，完成/取消，暂存到完成 | 保留 README 明示的 1.0 消息区/右下角拖动、释放保存，拖动中 Esc 撤销；`test_drag_release_saves_and_escape_rolls_back` |
| 设置中调整位置 | 旧版暂存编辑并提交/取消 | 保留 1.0 样例消息调整、Esc 返回设置；`test_adjust_position_uses_samples_and_returns_to_settings`、exe |
| Ctrl+滚轮字号 | 旧版仅设置里改字号 | 保留 1.0 新增功能及9–20边界；零增量不再误减字号；滚轮测试 |
| 自定义热键/冲突/录制 | 冲突回滚、录制时释放、Esc/失焦结束 | 保留冲突/暂停/Esc/失焦/关闭，补回冲突与暂停测试；1.0录制期间同步不打断录制、首个合法按键事件即完成（含重复），旧版同步取消且忽略重复；保留简化录制器，不改变全局注册协议 |
| 断线/发送失败 | 输入受连接限制；失败草稿队列 | 保留 1.0 离线输入、失败不自动重发、同账号同频道草稿；`test_send_returns_passive_and_failure_restores_scoped_draft` |
| 持续显示/淡出 | 不常驻时隐藏，被动连线才常驻 | 保留 1.0.1 新消息8秒+2秒淡出、输入显示历史，F9独立；已有淡出/可见性测试 |
| 设置实时预览/声音 | 多状态预览、原生声音选择试听 | 保留 1.0.1 同一渲染器白黑杂色预览、独立透明度、短提示音和缺失声音保留；不恢复旧 UI；已有设置/声音/预览测试 |
| 正常退出 | 关闭网络/全局钩子/热键、托盘消失 | 保留；exe 从托盘退出后 F8/F9 可重新注册，startup.log 无未处理异常 |

## 实现取舍

- 托盘在0.12和1.0均为单个静态图标，没有未连接/未读状态变体；本轮替换所有既有入口，未增加状态语义。
- “回到最新消息”与细滚动条都作为 Messages 子控件绝对定位；不改变消息区几何。滚动条保留固定文字边距，避免出现时换行。图标小于等于24px采用单横线，其余采用双横线；同一份SVG导出源用于程序、托盘、设置及exe。
- 阅读锚点以可见消息ID和纵坐标保存，新增/补齐/80条上限淘汰时重算底部偏移；当前正在看的消息本身被80条上限淘汰时，无法继续保留已不存在的内容，按剩余历史范围夹取。
- 旧版 F8 并未切换；遵从本次产品指令新增。Shift+Enter 没有多行语义，不另造新交互。托盘左键、离线输入、草稿保留、频道列表、直接拖动保存等已有明确1.0文档，继续保留。
- 所有行为修复均有自动测试；Qt offscreen 验证事件/几何/文字像素，原生验收脚本验证真实热键/IME/前台/全局滚轮，打包程序另验三条退化。源码原生注入的是测试聊天，exe滚动使用已有位置调整示例；没有加入生产测试入口或伪称 Oopz/真实游戏联机验收。

## 验证范围

最终源码全量测试：Mac offscreen 140 passed / 1 skipped（仅 Windows DPAPI）；rinutm 原生桌面 141 passed，无测试警告。原生探针与打包探针的具体结果、截图及交付 exe SHA-256 见本机 `~/.rin/work/typeslip/fix-102-report.md` 和 `~/.rin/work/typeslip/fix-102/` 证据。源码原生测试覆盖的网络收发为夹具；真实 Oopz 登录收发、真实游戏和干净 Windows 系统未验收。

## 验收探针隔离记录

初版托盘探针将 `exists()` 当作可见性，且点击前未记录实际命中的窗口。初次点击是否落到底层程序无法确认；没有操作QMT接口或进程，也没有擅自检查或补偿其状态。后续命中记录显示 全量测试产生的“纸条发送失败”通知（ShellExperienceHost）覆盖了溢出图标，而普通截图默认漏掉分层窗口，因此原截图不能用于断言命中了QMT。探针现要求溢出窗口可见，只通过UIA关闭匹配纸条名称的通知，再将鼠标移到任务栏空白处消除提示层，再核对鼠标位置实际命中Shell托盘窗口才点击；截图包含分层窗口。

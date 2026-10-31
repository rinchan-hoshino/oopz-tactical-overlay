# 发行与自动更新验收

完成本地构建不代表用户能够自动更新。每次发行必须完成线上发布和旧版升级验证，再报告交付完成。

## 发布内容

- 保持检查入口：`https://acv.k-neco.com/tools/oopz-tactical-overlay/latest.json`。
- 新版程序先发布到版本目录，例如 `0.9.1/OopzTacticalOverlay.exe`，清单的 `url` 指向该文件。版本目录中的程序发布后不再修改。
- 清单中的版本、文件大小和 SHA-256 必须对应已验证的 Windows 发行包；`publishedAt` 使用实际发布时间。
- 保持原下载入口 `OopzTacticalOverlay.exe` 可用，并同步为新版。
- 更换线上文件前，在公开目录之外备份旧程序和旧清单。临时文件写完并校验后，再原子替换入口文件。

静态站点沿用现有 `archive` 服务；发布程序不需要重启服务或改动其他应用。

## 必须完成的验证

1. 从公共 HTTPS 地址重新读取清单，确认版本、下载地址、大小和 SHA-256；不能用本地清单代替。
2. 在隔离的 Windows 用户状态目录启动上一发行版，让其使用真实公共更新入口。
3. 验证旧版自动下载完成，待更新记录和下载文件校验正确，运行中的程序尚未被替换。
4. 正常退出并重新启动，确认更新助手替换原文件、启动新版本并清除待更新记录。
5. 核对原设置保留、新版界面正常、退出后快捷键释放。
6. 记录测试环境、前后版本、发行包 SHA-256 和实际结果；清理本轮测试任务及进程。

还应验证实际安装入口，尤其是程序与更新缓存位于不同磁盘的情况。0.10.1 起，助手先在程序所在盘复制并重新校验更新文件，再原子替换；不能直接对跨盘路径调用 `os.replace`。旧助手遇到此问题时，需要一次使用已校验的新助手完成迁移，不能把同盘虚拟机验证当成该场景已通过。

## 用户看到的流程

程序在启动时检查更新，下载完成后提示重启更新。已经打开的程序不会定时检查新发行版，也不会在使用中强制重启。

因此，发布时已打开的旧版需要先重启一次触发检查，等出现更新已下载的提示后，再退出并启动完成替换。

## 1.0.0 重做：本轮范围与兼容记录

首轮只修改本地源码和测试，未提交、未发布、未访问线上、未连接 Windows。后续本地验证已完成并提交在 `redesign-1.0`；1.0.0 的 Windows 与公网升级验收见下文，实际跨盘安装入口仍待验证。

- `src/oopz_overlay/core` 不依赖 Qt；SDK、登录态、Win32 和更新在 `adapters`，UI 在 `ui`，`app.py` 负责组装。
- schema 8 原字段经原 DPAPI 解密后读取；状态目录仍为 `%LOCALAPPDATA%/RinChan/OopzTacticalOverlay/state.bin`。schema 9 保留原底色、文字透明度为基准，一个浓淡值（默认 50）同时调整两者，初次迁移不改变两项透明度。设计未规定映射公式，此处以无损为先；若改变映射，须复核迁移样例。
- 旧 `always_visible` 不再作为持久设置生效，这是设计明确删除的开关；频道、热键、显示器、中心相对坐标、宽高、字号与提示音保留。默认位置、字号范围 9–20、最多 80 条近期历史沿用旧版。
- 频道列表仍采用旧版当前语音服务器（无语音时回退到已保存服务器），不自动跟随 Oopz 窗口；此处设计没有改动服务器选择规则。离线时仍能打开 HUD，发送失败保留草稿；取消保留当前输入至同账号同频道再次输入，退出不落盘。
- 两个透明度基准仅用于兼容存储，不在 UI 暴露；设置读取失败时保留原文件、不用默认值覆盖。
- 原更新清单 URL、HTTPS 前缀约束、SHA-256、安装入口文件名和单实例服务名不变。`--apply-update` 的六个参数顺序、同盘暂存复制复验再替换、失败重启旧程序、`--cleanup-updater` 删除助手并继续启动均保留。
- `tests/fixtures/0.12.0` 由 `tests/tools/generate_legacy_fixtures.py` 执行提交 `55f7cd08c0ba744535fed96a28bb95e7bc493498`（版本 0.12.0）的实际序列化、更新协议和构建清单代码生成。exe 是明确标记的合成字节；state 是传给 DPAPI 的 JSON 原文，不能替代 Windows 同用户密文测试。
- 截图与检查入口在 `tests/tools`；生产程序没有 `--render-preview`、`--render-settings` 或 `--smoke-test` 分支。Windows 构建入口为 `tools/build/build_windows.py`。
- 旧 artifacts、release、assets、validation 文档、旧原生探针与重写前源码/测试已移到 `/Users/rin/.rin/archive/typeslip-artifacts-20261030/`，没有删除归档内容。
- 仓库额外保留 `pyproject.toml`、`uv.lock` 和 `.gitignore`：它们是依赖锁定、安装和构建所必需的元数据；这是对设计「只留」目录列表的最小例外。

本轮运行记录与截图目录为 `/Users/rin/.rin/work/typeslip/`；首轮 offscreen 截图不替代 Windows 的焦点、IME、全局热键、真实 DPAPI 和实际升级验证。

### 本地联网验证（2026-10-30）

仓库 `.venv` 已安装项目与 dev 依赖（PySide6-Essentials 6.12.0、oopz-sdk 0.15.0）。全量 `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest`：78 passed、1 skipped；唯一跳过为 Windows DPAPI 实机测试。`pip check` 与 `git diff --check` 通过，本次未改测试断言或生产代码。

`tests/tools/render_ui.py` 生成并人工检查七张截图：HUD 平时、输入、频道列表、首次启动、未登录，设置亮/暗。offscreen 没有系统主题通知，设置截图使用 Fusion 和显式 QPalette 模拟明暗；这验证配色和布局，不代表 Windows 原生外观验收。截图与依赖快照、测试日志均留在仓库外的 `/Users/rin/.rin/work/typeslip/`。未 push、未合并 main、未发布、未操作 Windows。

### Windows 与公网发行验证（2026-10-31）

- 第二轮在 rinutm（Windows 11 ARM64 / x64 Python 3.11.9）构建并通过原生桌面全量测试：79 passed，DPAPI、中文 IME、焦点恢复和全局热键通过；记录见 `/Users/rin/.rin/work/typeslip/round2-report.md`。本次复跑 Mac offscreen：78 passed、1 skipped（Windows DPAPI）。
- “更新检查失败”来自第二轮探针主动设置的 `127.0.0.1:9` 代理；去掉代理后还复现了虚拟机缺少 ISRG Root X1 的证书错误。Windows 正常 HTTPS 请求触发系统根证书自动补齐后，原发行包检查正常；未关闭证书校验、未修改更新代码或重打包，版本比较和公网清单解析通过。
- 公网从 0.12.0（SHA-256 `d542b8f3ff50ed9bc7bcce602445ef45d237179292975d68cdfccc03fe9a99f7`）升级到 1.0.0（39,011,840 字节，SHA-256 `c560acdb6eb1a34795ea6e0538067ac731299a1a9ade0d2ee31b0a646873a37e`）。版本目录、原入口、TypeSlip.exe、Zhitiao.exe、校验清单与使用说明同步更新，最新清单使用实际发布时间。
- rinutm 使用实际线上 0.12.0 exe、隔离 LOCALAPPDATA 和旧版 DPAPI 加密的 schema 8 样例：公网自动下载、待更新记录与文件校验、运行中保持旧文件、托盘退出、重新启动、旧助手替换并启动 1.0.0、清除待更新记录和助手均通过。schema 9 保存后逐字段核对设置保留；正常退出后 Ctrl+F8 / Alt+F9 均可重新注册。
- 首次验收探针只识别 TypeSlip，未识别旧版中文托盘名“纸条”，因此按流程恢复了全部入口文件和旧清单，并从公网核对回滚。修正探针后旧版正常退出，重新发布同一已校验包并完成后续升级验收；未重启服务。
- 备份：服务器 `/app/state/archive/releases/oopz-tactical-overlay/backup-0.12.0-before-1.0.0-20261031/`；本机报告 `/Users/rin/.rin/work/typeslip/release-report.md`，证据 `release/`，截图 `shots-release/`。公网 HTTPS 清单和发行包已重新下载核对。
- 实际跨盘安装入口未验证：虚拟机只有 C: 可写；真实 Oopz 登录收发和干净 Windows 系统仍未验证，不计为通过。


## 1.0.1 改进与发行

- 保留 1.0 的紧凑单页与系统外观，加入同一 HUD 渲染器的实时预览（白/黑/杂色），设置打开时隐藏实际 HUD、关闭后恢复、独立文字/暗角不透明度、位置尺寸调整和提示音试听。不恢复旧版大标题、频道管理与多状态演示，频道选择继续在 HUD 内完成。
- schema 10 将 schema 9 的 strength 换算为实际透明度一次；schema 8 原透明度与持续显示偏好保留。旧设置未记录提示音时保持关闭，新安装默认轻触；缺失的已选声音保留并标明不可用。
- 原声音列表按文件名排序再截前五项，导致只出现 Alarm；现在优先提供 Windows 自带的四种短音（64–148 毫秒），完整系统声音列表仍可选。不附带音频、不新增依赖。
- HUD 采用 FPS 聊天样式：稳定发言人强调色加冒号、白色半粗正文、1.5 px 外扩深色描边和柔和投影，取消逐行底条与矩形高亮。背景改为消息区左下渐隐暗角，所有边缘羽化；新安装 15%，已有透明度值与位置保留，新安装靠左下。
- “连接后持续显示消息”开启时常驻；关闭后新消息显示 8 秒、2 秒淡出，输入和调整时显示历史。F9 显隐单独保留，不因连接或设置切换自动恢复。设置预览复用同一渲染器并保持可见，不修改实际历史。
- 依照 [WCAG 2.2 对比度说明](https://www.w3.org/WAI/WCAG22/Understanding/contrast-minimum.html)，有描边文字按字形与紧邻的深色光晕计算对比度；此数值不代表浅色字形直接对白色游戏画面的对比度。降低文字透明度或消息淡出期间不保证 4.5:1。
- 发布前的本地验收结果、发行包 SHA-256、窗口区域截图和测试日志记录在 `~/.rin/work/typeslip/fix-101-report.md`。当时仅本地提交 fix/1.0.1，未发布、上传或推送；公网升级结果见下文，真实游戏/Oopz 联机仍未验收。
- 最终源码验收：Mac offscreen 113 passed / 1 skipped（Windows DPAPI），rinutm 原生 114 passed；19 个构建输入文件哈希与本地一致。实际 exe 的预览、试听、保存、迁移、鼠标穿透、托盘退出及快捷键释放通过；名字/描边最低 9.73:1、正文/描边 19.71:1。

### 1.0.1 公网升级验收（2026-10-31）

- 发行包沿用已验收文件，未改生产代码或重打包。线上由 1.0.0（39,011,840 字节，SHA-256 `c560acdb6eb1a34795ea6e0538067ac731299a1a9ade0d2ee31b0a646873a37e`）更新为 1.0.1（39,041,536 字节，SHA-256 `a50e23f35fd890f7e2e57969679586f2f31447d1824f90edba4fdfe4df3d7596`），最终 `publishedAt=2026-10-31T05:49:04.566966+00:00`。
- 版本目录不可变；三个下载入口、校验清单和使用说明同步，入口原子替换，latest.json 最后替换。Mac 从公共 HTTPS 重下四个 exe 核对大小及哈希；Windows 升级后重读公网清单一致，未重启 archive 服务。
- 仅通过 ssh rinutm 操作 Windows，未操作 QMT 进程或窗口。使用公网原始 1.0.0 exe 和隔离 LOCALAPPDATA：自动下载、待更新记录与文件校验、运行中保持旧安装文件、正常托盘退出、重启后旧助手替换、新版启动、待更新记录及下载缓存和助手清理均通过。助手退出码 0，安装文件版本资源为 1.0.1.0。
- 1.0.0 实际设置存储及 UI 保存生成 schema 9 样例；strength=70、底色38、文字72 的有效透明度58/88迁移为 schema 10 的独立值，Windows Notify.wav、频道、热键、显示器名、位置、尺寸和字号逐字段保留。新版预览与设置截图核对，输入热键可用，正常退出后 Ctrl+F8 / Alt+F9 均可重新注册。
- 两次验收失败均恢复了全部入口和旧清单，并从 HTTPS 确认 1.0.0：第一次为验证脚本未编码中文使用说明 URL；第二次为下载完成通知遮挡托盘，探针点不到退出菜单。修正 URL 编码并仅关闭 TypeSlip 通知后，从干净旧版状态重跑全链路通过；未修改发行包。
- 备份位于服务器 `/app/state/archive/releases/oopz-tactical-overlay/backup-1.0.0-before-1.0.1-20261031/`；本机升级起点、日志、JSON 与截图在 `~/.rin/work/typeslip/release-101/`，报告为 `~/.rin/work/typeslip/release-101-report.md`。本轮 Mac 复跑 113 passed / 1 skipped（Windows DPAPI），Windows 测试任务、进程及应用锁已清理。
- rinutm 仍仅 C: 可写，实际跨盘安装入口未验证；真实 Oopz 登录收发及干净 Windows 环境未验证，不计为通过。

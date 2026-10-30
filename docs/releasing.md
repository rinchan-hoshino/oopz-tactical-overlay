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

因此，发布时已打开的旧版需要先重启一次触发检查，等出现“已下载，重启后更新”后，再退出并启动完成替换。

## 1.0.0 重做：本轮范围与兼容记录

首轮只修改本地源码和测试，未提交、未发布、未访问线上、未连接 Windows。后续本地验证已完成并提交在 `redesign-1.0`；1.0.0 仍未完成发行验收，发布前必须以 0.12.0 做真实公网升级和跨盘安装入口验证。

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

本轮运行记录与截图目录为 `/Users/rin/.rin/work/typeslip/`；Windows 的焦点、IME、全局热键、真实 DPAPI 和实际升级结果留待下一轮，不以 offscreen 截图替代。

### 本地联网验证（2026-10-30）

仓库 `.venv` 已安装项目与 dev 依赖（PySide6-Essentials 6.12.0、oopz-sdk 0.15.0）。全量 `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest`：78 passed、1 skipped；唯一跳过为 Windows DPAPI 实机测试。`pip check` 与 `git diff --check` 通过，本次未改测试断言或生产代码。

`tests/tools/render_ui.py` 生成并人工检查七张截图：HUD 平时、输入、频道列表、首次启动、未登录，设置亮/暗。offscreen 没有系统主题通知，设置截图使用 Fusion 和显式 QPalette 模拟明暗；这验证配色和布局，不代表 Windows 原生外观验收。截图与依赖快照、测试日志均留在仓库外的 `/Users/rin/.rin/work/typeslip/`。未 push、未合并 main、未发布、未操作 Windows。

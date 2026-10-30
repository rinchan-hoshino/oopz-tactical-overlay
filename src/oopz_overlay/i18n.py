"""Small presentation dictionaries; SDK and core do not need Qt."""
import locale
import os
ZH = {'app': '纸条 TypeSlip',
 'settings': '设置…',
 'quit': '退出',
 'input_hotkey': '输入',
 'visibility_hotkey': '显示 / 隐藏',
 'strength': '浓淡',
 'font_size': '字号',
 'sound': '提示音',
 'off': '关',
 'record': '按下新组合',
 'login': '先打开并登录 Oopz',
 'choose': '按 {hotkey} 选个频道',
 'connecting': '正在连接…',
 'connected': '已连接',
 'reconnecting': '正在重连…',
 'empty_channels': '先在 Oopz 加入一个语音频道',
 'send_failed': '发送失败，草稿已保留',
 'latest': '回到最新',
 'type': '输入消息',
 'checking': '正在检查更新',
 'current': '已是最新版本',
 'ready': '已下载，重启后更新',
 'downloading': '正在下载更新',
 'update_failed': '更新检查失败，下次启动重试',
 'save_failed': '设置保存失败，请检查磁盘权限',
 'focus_failed': '无法切换输入，请检查游戏权限',
 'sample1': '二楼窗口一个',
 'sample2': '收到，我绕右侧',
 'sample3': '等一下，楼梯有脚步',
 'settings_failed': '无法读取原设置，修复 state.bin 后重启',
 'hotkey_failed': '快捷键不可用，请重新设置',
 'history_failed': '历史暂不可用，仍可接收新消息'}
EN = {'app': 'TypeSlip',
 'settings': 'Settings…',
 'quit': 'Quit',
 'input_hotkey': 'Compose',
 'visibility_hotkey': 'Show / hide',
 'strength': 'Intensity',
 'font_size': 'Font size',
 'sound': 'Sound',
 'off': 'Off',
 'record': 'Press a shortcut',
 'login': 'Open Oopz and sign in',
 'choose': 'Press {hotkey} to choose a channel',
 'connecting': 'Connecting…',
 'connected': 'Connected',
 'reconnecting': 'Reconnecting…',
 'empty_channels': 'Join a voice channel in Oopz first',
 'send_failed': 'Send failed; draft kept',
 'latest': 'Back to latest',
 'type': 'Message',
 'checking': 'Checking for updates',
 'current': 'Up to date',
 'ready': 'Downloaded; restart to update',
 'downloading': 'Downloading update',
 'update_failed': 'Update check failed; retry on next launch',
 'save_failed': 'Cannot save settings; check disk permissions',
 'focus_failed': 'Cannot focus input; check game permissions',
 'sample1': 'One at the upstairs window',
 'sample2': 'Copy, going around the right',
 'sample3': 'Wait, footsteps on the stairs',
 'settings_failed': 'Cannot read settings; repair state.bin and restart',
 'hotkey_failed': 'Shortcut unavailable; choose another',
 'history_failed': 'History unavailable; live messages still work'}
PLACEHOLDERS = {'[图片]': '[Image]',
 '[视频]': '[Video]',
 '[语音]': '[Audio]',
 '[文件]': '[File]',
 '[表情]': '[Sticker]',
 '[非文字消息]': '[Non-text message]',
 '我': 'Me',
 '未知': 'Unknown',
 '连接中断，正在重连…': 'Reconnecting…',
 '历史消息暂时无法读取，实时消息仍会继续接收。': 'History unavailable; live messages still work.'}

def language() -> str:
    value = os.environ.get('LC_ALL') or os.environ.get('LC_MESSAGES') or os.environ.get('LANG')
    if not value or value in {'C', 'POSIX'}:
        value = locale.getlocale()[0] or 'zh'
    return 'en' if value.lower().startswith('en') else 'zh'

def tr(key: str, locale: str | None=None, **values) -> str:
    lang = locale or language()
    text = (EN if lang == 'en' else ZH).get(key)
    if text is None:
        text = PLACEHOLDERS.get(key, key) if lang == 'en' else key
    return text.format(**values) if values else text

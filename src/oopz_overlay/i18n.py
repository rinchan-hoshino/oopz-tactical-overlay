"""Small presentation dictionaries; SDK and core do not need Qt."""
import locale
import os
ZH = {'app': '纸条 TypeSlip',
 'settings': '设置…',
 'quit': '退出',
 'input_hotkey': '输入消息',
 'visibility_hotkey': '显示 / 隐藏消息',
 'font_size': '字号',
 'sound': '消息提示音',
 'off': '关闭',
 'record': '请按下快捷键',
 'login': '请先打开并登录 Oopz',
 'choose': '按 {hotkey} 选择文字频道',
 'connecting': '正在连接…',
 'connected': '已连接',
 'reconnecting': '正在重连…',
 'empty_channels': '请先在 Oopz 加入语音频道',
 'send_failed': '发送失败，草稿已保留',
 'latest': '回到最新消息',
 'type': '输入消息',
 'checking': '正在检查更新',
 'current': '已是最新版本',
 'ready': '更新已下载，重启后安装',
 'downloading': '正在下载更新',
 'update_failed': '更新检查失败，下次启动重试',
 'save_failed': '设置保存失败，请检查磁盘权限',
 'focus_failed': '无法切换输入，请检查游戏权限',
 'sample1': '二楼窗口一个',
 'sample2': '收到，我绕右侧',
 'sample3': '等一下，楼梯有脚步',
 'settings_failed': '无法读取设置，原设置文件已保留',
 'hotkey_failed': '快捷键不可用，请重新设置',
 'history_failed': '暂时无法加载历史消息，仍可接收新消息'}
EN = {'app': 'TypeSlip',
 'settings': 'Settings…',
 'quit': 'Quit',
 'input_hotkey': 'Compose',
 'visibility_hotkey': 'Show / hide',
 'font_size': 'Font size',
 'sound': 'Message sound',
 'off': 'Off',
 'record': 'Press a shortcut',
 'login': 'Open Oopz and sign in',
 'choose': 'Press {hotkey} to choose a text channel',
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
 'settings_failed': 'Cannot read settings; original file kept',
 'hotkey_failed': 'Shortcut unavailable; choose another',
 'history_failed': 'History unavailable; live messages still work'}

ZH.update({
    'settings_title': '纸条设置', 'preview': '效果预览',
    'white_scene': '白色背景', 'black_scene': '黑色背景', 'mixed_scene': '杂色背景',
    'preview_background': '预览背景',
    'adjust': '调整位置与大小', 'adjust_hint': '拖动消息区移动，右下角缩放；Esc 返回设置',
    'text_opacity': '文字不透明度', 'backdrop_opacity': '背景不透明度',
    'always_visible': '连接后持续显示消息', 'sound_preview': '试听',
    'sound_unavailable': '声音不可用', 'sound_failed': '无法播放提示音，请选择其他声音',
    'sound_tap': '轻触（推荐）', 'sound_tick': '短音', 'sound_drop': '水滴', 'sound_soft': '柔和',
})
EN.update({
    'settings_title': 'TypeSlip settings', 'preview': 'Live preview',
    'white_scene': 'White background', 'black_scene': 'Black background', 'mixed_scene': 'Mixed background',
    'preview_background': 'Preview background',
    'adjust': 'Adjust position and size', 'adjust_hint': 'Drag messages to move, bottom right to resize; Esc returns to settings',
    'text_opacity': 'Text opacity', 'backdrop_opacity': 'Background opacity',
    'always_visible': 'Keep messages visible when connected', 'sound_preview': 'Listen',
    'sound_unavailable': 'Sound unavailable', 'sound_failed': 'Cannot play this sound; choose another',
    'sound_tap': 'Tap (recommended)', 'sound_tick': 'Tick', 'sound_drop': 'Drop', 'sound_soft': 'Soft',
})

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

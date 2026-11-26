from pathlib import Path

PLUGIN_NAME = 'BiliBiliNotify'
DISPLAY_NAME = 'B站订阅推送'
WEBUI_EVENT = 'BiliBiliNotify_WebUI_Config'
DATA_ROOT = Path('plugin/data') / PLUGIN_NAME
IMAGE_ROOT = Path('data/images') / PLUGIN_NAME / 'covers'
GLOBAL_FILE = 'global.json'
BOT_FILE = 'config.json'
ROOMS_FILE = 'rooms.json'
KINDS = ('live', 'dynamic', 'video')
LABELS = dict(zip(KINDS, ('直播', '动态', '视频')))
COMMAND_NAME = 'bpush'
allowed_prefix_list = ('.', '。', '/', '／')
HTTP_TIMEOUT = 10
IMAGE_TIMEOUT = 15

# 总账号凭据与指纹独立于各 Bot 的轮询、群和主播开关。
GLOBAL_DEFAULT = {
    'version': 1,
    'cookie': {'sessdata': '', 'bili_jct': '', 'buvid3': '', 'buvid4': '', 'b_nut': 0},
    'user_agent': '',
    'proxy': '',
    'whitelist': [],
    'buvid_cache': {'cookie': '', 'fetched_at': 0.0},
    'log_to_file': False,
    'meta': {'updated_at': 0, 'updated_by': ''},
}
BOT_DEFAULT = {
    'version': 1,
    'enable': True,
    'prefix_list': list(allowed_prefix_list),
    # max_sockets：直播间长连接上限（WebSocket 只用于把开播感知从轮询提到秒级，
    # 超出的主播仍靠轮询；0 表示关闭长连接、只用轮询）。
    # live_relaxed_seconds：长连接已连上的主播，直播轮询放宽到该间隔（0 = 不放宽）。
    'poll': {'live_seconds': 10, 'dynamic_seconds': 60, 'video_seconds': 60,
             'max_concurrent': 3, 'max_sockets': 8, 'live_relaxed_seconds': 60},
    'at_all': {'daily_limit': 10, 'guild_at_once': True},
    'at_subscribers': {'live': True, 'dynamic': False, 'video': False},
    # dynamic_source：follow = 关注流当触发器（需 SESSDATA 且关注目标 UP），poll = 逐 UP 轮询
    'dynamic_source': 'follow',
    # auto_follow：添加主播时顺手关注它（会修改登录账号的关注列表）。
    # 默认开，但只有登录态（SESSDATA + bili_jct）才真正调用；未登录时静默跳过。
    'auto_follow': True,
    'push_default': dict.fromkeys(KINDS, True),
    'send_interval_seconds': 3,
    'disabled_group_list': [],
    'configured_master_list': [],
    'meta': {'updated_at': 0},
}
ROOMS_DEFAULT = {'version': 1, 'rooms': {}, 'groups': {}}

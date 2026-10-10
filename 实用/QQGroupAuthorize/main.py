"""沿用官方原生模板的生命周期，仅接收 QQ 群消息。"""

import threading
import time
from collections import OrderedDict

import OlivOS

from . import config, renderer, resources, transport

PLUGIN_NAME = '获取主动授权'
_seen = OrderedDict()
_seen_lock = threading.Lock()
_join_seen = OrderedDict()
HELP = (
    '获取主动授权 / QQGroupAuthorize\n'
    '需要手机 QQ 9.2.90 及以上。\n'
    'Requires mobile QQ 9.2.90 or later.\n'
    '仅限手机 QQ，电脑端目前不可用；低于该版本，请群主先更新 QQ。\n'
    'Mobile QQ only; desktop QQ is currently unsupported. Ask the group owner to update older versions.\n'
    '\n发设置图 / Send setup image\n'
    '.授权 全消息\n.auth allmsg\n'
    '\n显示帮助 / Show help\n'
    '.授权 帮助\n.auth help\n'
    '\n开启入群自动发图 / Enable automatic image on bot joining\n'
    '.授权 入群 开\n.auth join on\n'
    '\n关闭入群自动发图（默认关闭） / Disable automatic image (default: off)\n'
    '.授权 入群 关\n.auth join off\n'
    '\n查看当前 bot 开关 / Check current bot setting\n'
    '.授权 入群 状态\n.auth join status\n'
    '\n空格可省略 / Spaces are optional.\n'
    '前缀支持 . / 。；英文大小写不敏感。\n'
    'Prefixes: . / 。; English commands are case-insensitive.\n'
    '仅 QQ 群消息生效，不支持私聊或频道。\n'
    'QQ groups only; private chats and guild channels are unsupported.\n'
    'QQ 版本说明仅为操作提示，插件不检测客户端版本。\n'
    'The QQ version note is guidance only; the plugin does not check client versions.\n'
    '\n开关权限：当前 bot 的 Core 骰主，或插件全局配置骰主。\n'
    'Permission: current bot Core masters or global plugin masters.\n'
    '群主/管理员不自动获得此权限。\n'
    'Group owners/admins do not automatically receive this permission.\n'
    '\n配置 / Config: plugin/data/QQGroupAuthorize/config.json\n'
    'browser_path 为共用浏览器路径；bots[bot hash].name 是自动保存的当前 bot 兜底名称。\n'
    'browser_path is shared; bots[bot hash].name stores each bot fallback name.\n'
    'masters 是全局用户 ID 字符串列表；QQ 官方群聊填成员 OpenID，通常不是 QQ 号。\n'
    'masters: global list of user ID strings; use QQ group member OpenIDs, usually not QQ numbers.\n'
    '开关按 bot hash 保存，影响当前 bot 的所有群，仅在机器人自身入群时触发。\n'
    'Saved per bot hash; applies to all groups of the current bot and triggers only when the bot itself joins.'
)


class Event:
    @staticmethod
    def init(plugin_event, Proc):
        # renderer 已在 import 时将 HTML 读入内存；这里不依赖 OPK 解包目录。
        pass

    @staticmethod
    def init_after(plugin_event, Proc):
        try:
            resources.prepare_resources()
            config.initialize(Proc.Proc_data.get('bot_info_dict', {}).values())
        except Exception as exc:
            log(Proc, f'初始化数据目录失败（{type(exc).__name__}），命令仍可使用文本降级。')

    @staticmethod
    def group_message(plugin_event, Proc):
        try:
            handle_group(plugin_event, Proc)
        except Exception as exc:
            # 不记录事件载荷、凭据或异常中的请求 URL。
            log(Proc, f'处理群消息失败（{type(exc).__name__}）。')

    @staticmethod
    def save(plugin_event, Proc):
        with _seen_lock:
            _seen.clear()
            _join_seen.clear()

    @staticmethod
    def group_member_increase(plugin_event, Proc):
        try:
            handle_join(plugin_event, Proc)
        except Exception as exc:
            log(Proc, f'入群自动发图失败（{type(exc).__name__}）。')


def log(proc, message):
    if proc is not None:
        try:
            proc.log(3, f'[{PLUGIN_NAME}] {message}', [])
        except Exception:
            pass


def match_keyword(text, keywords):
    """沿用轻量模板：长关键词优先，按前缀取余文，各层仅去掉两端空白。"""
    source = text.strip().lower()
    for keyword in sorted(keywords, key=len, reverse=True):
        if source.startswith(keyword):
            return keyword, source[len(keyword) :].strip()
    return '', source


def parse_command(event):
    """先解析消息段，再逐层贪婪匹配根命令/子命令，支持免空格写法。"""
    message = event.data.message
    if isinstance(message, str):
        message = OlivOS.messageAPI.Message_templet('olivos_string', message)
    parts = getattr(message, 'data', None)
    if not getattr(message, 'active', False) or not isinstance(parts, list):
        return None
    own_ids = {str(event.bot_info.id), str(event.base_info.get('self_id', ''))}
    sdk = getattr(OlivOS, 'qqGuildv2SDK', None)
    sub_ids = getattr(sdk, 'sdkSubSelfInfo', {})
    if event.bot_info.hash in sub_ids:
        own_ids.add(str(sub_ids[event.bot_info.hash]))
    extend = getattr(event.data, 'extend', {}) or {}
    for field in ('sub_self_id', 'sub_self_open_id'):
        if extend.get(field):
            own_ids.add(str(extend[field]))
    text = ''
    for part in parts:
        if isinstance(part, OlivOS.messageAPI.PARA.text):
            text += part.data.get('text', '')
        elif not text.strip() and isinstance(part, OlivOS.messageAPI.PARA.at):
            if str(part.data.get('id')) not in own_ids:
                return None
        elif not text.strip() and isinstance(part, OlivOS.messageAPI.PARA.reply):
            continue
        else:
            return None
    text = text.strip().lower()
    if not text or text[0] not in './。':
        return None
    root, remaining = match_keyword(text[1:], ('授权', 'auth'))
    if not root:
        return None
    if not remaining:
        return 'help', ''
    subcommands = (
        {'全消息': 'image', '帮助': 'help', '入群': 'join'}
        if root == '授权'
        else {'allmsg': 'image', 'help': 'help', 'join': 'join'}
    )
    matched, argument = match_keyword(remaining, subcommands)
    if not matched:
        return None
    action = subcommands[matched]
    if action in ('image', 'help') and argument:
        return None
    return action, argument


def is_command(event):
    return parse_command(event) == ('image', '')


def is_qq_group(event):
    extend = getattr(event.data, 'extend', {}) or {}
    return (
        event.platform.get('sdk') == 'qqGuildv2_link'
        and event.platform.get('platform') == 'qqGuild'
        and extend.get('flag_from_qq') is True
        and not extend.get('flag_from_direct', False)
        and getattr(event.data, 'host_id', None) in (None, '')
    )


def handle_group(event, proc):
    # qqGuildV2 同时承载频道；群回调仍须检查来源，不能只检查 SDK 名称。
    extend = getattr(event.data, 'extend', {}) or {}
    if not is_qq_group(event) or event.plugin_info.get('func_type') != 'group_message':
        return
    command = parse_command(event)
    if command is None:
        return
    action, argument = command
    group_id = str(getattr(event.data, 'group_id', '') or '')
    message_id = str(getattr(event.data, 'message_id', '') or extend.get('reply_msg_id', '') or '')
    if not group_id or not message_id:
        log(proc, '群消息缺少 group_id 或原消息 ID，无法被动回复。')
        return
    key = (str(event.bot_info.hash), group_id, message_id)
    with _seen_lock:
        if key in _seen:
            return
        _seen[key] = True
        while len(_seen) > 512:
            _seen.popitem(last=False)
    event.set_block()
    bridge = transport.GroupReply(event, group_id, message_id)
    if action == 'help':
        bridge.text(HELP + f'\n当前用户 ID / User ID：{event.data.user_id}')
        return
    if action == 'join':
        control_auto_join(event, bridge, argument)
        return
    send_guide(event, proc, bridge)


def control_auto_join(event, bridge, argument):
    actions = {'开': True, 'on': True, '关': False, 'off': False, '状态': None, 'status': None}
    matched, remaining = match_keyword(argument, actions)
    if argument and (not matched or remaining):
        bridge.text('用法：.授权入群开/关/状态，或 .authjoinon/off/status。帮助：.授权帮助 / .authhelp。空格可省略。')
        return
    try:
        if not config.is_master(event):
            bridge.text('仅骰主可操作此开关。请配置插件全局 masters，或使用当前 bot 的 Core 骰主身份。')
            return
        action = actions[matched] if matched else None
        if action is not None:
            config.set_auto_join(event.bot_info.hash, action)
        enabled = config.auto_join_enabled(event.bot_info.hash)
    except config.ConfigError as exc:
        bridge.text(str(exc))
        return
    verb = '已' if action is not None else '当前'
    bridge.text(f'{verb}{"开启" if enabled else "关闭"}当前 bot 的入群自动发图，对该 bot 的所有群生效。')


def handle_join(event, proc):
    extend = getattr(event.data, 'extend', {}) or {}
    if (
        not is_qq_group(event)
        or event.plugin_info.get('func_type') != 'group_member_increase'
        or extend.get('qq_event_type') != 'GROUP_ADD_ROBOT'
        or str(event.data.user_id) != str(event.bot_info.id)
        or not config.auto_join_enabled(event.bot_info.hash)
    ):
        return
    group_id = str(event.data.group_id or '')
    event_id = str(extend.get('event_id') or '')
    if not group_id or not event_id:
        log(proc, '自身入群事件缺少群 ID 或事件回复凭据，未主动发送。')
        return
    # Core 同样对自身入群去重；额外保留事件 ID 五分钟，兼容重复投递不同时间到达。
    now = time.monotonic()
    key = (str(event.bot_info.hash), group_id, event_id)
    group_key = (str(event.bot_info.hash), group_id, 'recent_join')
    with _seen_lock:
        for old in [item for item, expiry in _join_seen.items() if expiry <= now]:
            _join_seen.pop(old, None)
        if key in _join_seen or group_key in _join_seen:
            return
        _join_seen[key] = now + 300
        _join_seen[group_key] = now + 3
        while len(_join_seen) > 1024:
            _join_seen.popitem(last=False)
    # 不 set_block，让 Core 原有的欢迎和入群记录继续执行。
    send_guide(event, proc, transport.GroupReply(event, group_id, event_id=event_id))


def send_guide(event, proc, bridge):
    fallback = '授权图暂时无法显示。\n' + transport.MANUAL_GUIDE
    try:
        profile = resources.bot_profile(event, proc)
        result = renderer.guide_image(profile)
        if result.warning:
            log(proc, result.warning)
        if result.data:
            first_ok = bridge.image(result.data)
            if not first_ok:
                log(proc, '授权图上传或发送失败，改为被动文字指引。')
                first_ok = bridge.text(fallback)
        else:
            first_ok = bridge.text(fallback)
    except Exception as exc:
        log(proc, f'图片生成失败（{type(exc).__name__}），改为文字指引。')
        first_ok = bridge.text(fallback)
    if not first_ok:
        log(proc, '图片与文字降级均未发送成功。')

    # 自动授权入口按用户要求暂时注释，只发送手动设置图。
    # 恢复前需要有效的 groupCode、botUin、botUid 构造 QQ 跳转链接；不能拿群 OpenID/AppID 代替。
    # try:
    #     second_ok = bridge.authorization()
    # except Exception as exc:
    #     log(proc, f'Markdown 发送失败（{type(exc).__name__}）。')
    #     second_ok = False
    # if not second_ok:
    #     bridge.text('授权按钮暂时不可用，请群主手动设置。\n' + transport.MANUAL_GUIDE)

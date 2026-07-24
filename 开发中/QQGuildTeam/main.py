"""
QQGuildTeam - 团队分组与 Markdown @ 插件

匹配 OlivaDiceCore 代码风格，前置依赖 OlivaDiceCore。
仅在 qqGuildV2 平台维护命名分组，支持用户自行加入/离开，骰主/群管可创建/删除分组。
.team at 命令用 Markdown 格式 @ 所有分组成员，其他平台完全不响应。

命令：
  .team at [分组名]       用 Markdown @ 所有分组成员（默认当前用户的活跃组）
  .team add <分组名>      将当前用户加入指定分组
  .team leave [分组名]    将当前用户移出指定分组
  .team create <分组名>   创建新分组（需骰主或群管）
  .team del <分组名>      删除分组（需骰主或群管）
  .team list [分组名]     列出分组成员
  .team active <分组名>   设置当前用户的活跃分组
  .team on                开启本群插件
  .team off               关闭本群插件
  .team help              显示帮助
  .team                   查看状态

数据按 bot_hash/group_id 分文件存储，群链 bot 自动回退查找链接账号的配置。
"""

import json
import os
import threading
import time
import traceback

import OlivaDiceCore
import OlivOS

# 数据存储基础路径（按 bot_hash 分目录）
base_data_path = 'plugin/data/QQGuildTeam'

# 文件读写锁
file_lock = threading.RLock()

# 命令前缀
CMD_DOT = '.team'

# 帮助文本
HELP_STR = (
    '团队分组与 Markdown @ 插件\n'
    '━━━━━━━━━━━━━━\n'
    '.team at [分组名]       用 Markdown @ 所有分组成员\n'
    '.team add <分组名>      将当前用户加入指定分组\n'
    '.team leave [分组名]    将当前用户移出指定分组\n'
    '.team create <分组名>   创建新分组（需骰主或群管）\n'
    '.team del <分组名>      删除分组（需骰主或群管）\n'
    '.team list [分组名]     列出分组成员\n'
    '.team active <分组名>   设置当前用户的活跃分组\n'
    '.team on                开启本群插件\n'
    '.team off               关闭本群插件\n'
    '.team help              显示帮助\n'
    '.team                   查看状态\n'
    '━━━━━━━━━━━━━━\n'
    '未指定分组名时默认使用你当前的活跃分组。\n'
    '仅 qqGuildV2 平台生效，其他平台不会响应。'
)

# ── isMatchWordStart（匹配 OlivaDiceCore 风格）──


def isMatchWordStart(data, key, ignoreCase=True, fullMatch=False, isCommand=False):
    tmp_output = False
    flag_skip = False
    tmp_data = data.strip()
    tmp_keys = [key] if isinstance(key, str) else key
    if isCommand:
        if 'replyContextFliter' in OlivaDiceCore.crossHook.dictHookList:
            for k in tmp_keys:
                if k in OlivaDiceCore.crossHook.dictHookList['replyContextFliter']:
                    tmp_output = False
                    flag_skip = True
                    break
    if not flag_skip:
        if ignoreCase:
            tmp_data = tmp_data.lower()
            tmp_keys = [k.lower() for k in tmp_keys]
        tmp_keys_sorted = sorted(tmp_keys, key=lambda x: len(x), reverse=True)
        for tmp_key in tmp_keys_sorted:
            if not fullMatch and len(tmp_data) >= len(tmp_key):
                if tmp_data[: len(tmp_key)] == tmp_key and (
                    len(tmp_data) == len(tmp_key) or tmp_data[len(tmp_key)].isspace()
                ):
                    tmp_output = True
                    break
            elif fullMatch and tmp_data == tmp_key:
                tmp_output = True
                break
    return tmp_output


def getMatchWordStartRight(data, key, ignoreCase=True):
    tmp_output_str = ''
    tmp_data = data
    tmp_keys = [key] if isinstance(key, str) else key
    if ignoreCase:
        tmp_data = tmp_data.lower()
        tmp_keys = [k.lower() for k in tmp_keys]
    tmp_keys_sorted = sorted(tmp_keys, key=lambda x: len(x), reverse=True)
    for tmp_key in tmp_keys_sorted:
        if len(tmp_data) > len(tmp_key):
            if tmp_data[: len(tmp_key)] == tmp_key:
                tmp_output_str = data[len(tmp_key) :]
                break
    return tmp_output_str


def skipSpaceStart(data):
    return data.lstrip()


# ── 数据读写（参考 QQGuildWelcome 实现）──


def get_config_path(bot_hash):
    return os.path.join(base_data_path, bot_hash, 'config.json')


def load_bot_config(bot_hash):
    path = get_config_path(bot_hash)
    with file_lock:
        try:
            with open(path, encoding='utf-8') as f:
                config = json.load(f)
            if not isinstance(config, dict) or not isinstance(config.get('groups', {}), dict):
                raise ValueError('配置文件结构无效')
            return config
        except FileNotFoundError:
            return {'groups': {}}
        except Exception:
            traceback.print_exc()
            return {'groups': {}}


def save_bot_config(bot_hash, config):
    path = get_config_path(bot_hash)
    temp_path = path + '.tmp'
    with file_lock:
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(temp_path, 'w', encoding='utf-8') as f:
                json.dump(config, f, ensure_ascii=False, indent=2)
            os.replace(temp_path, path)
            return True
        except Exception:
            traceback.print_exc()
            try:
                if os.path.exists(temp_path):
                    os.remove(temp_path)
            except Exception:
                pass
            return False


def get_linked_bot_hashes(bot_hash):
    """获取群链中所有 bot 的 hash 列表（含自身）"""
    try:
        relations = OlivaDiceCore.console.getAllAccountRelations()
        if bot_hash in relations:
            res = [bot_hash]
            res.extend(relations[bot_hash])
            return res
        for master, slaves in relations.items():
            if bot_hash in slaves:
                res = [master]
                res.extend(slaves)
                return res
    except Exception:
        pass
    return [bot_hash]


def get_group_config(bot_hash, group_id):
    """获取单个群的配置，始终优先读取群链主账号"""
    for linked_hash in get_linked_bot_hashes(bot_hash):
        cfg = load_bot_config(linked_hash).get('groups', {}).get(str(group_id), {})
        if cfg:
            return cfg
    return {}


def set_group_config(bot_hash, group_id, group_cfg):
    """写入单个群的配置，群链账号统一写入主账号"""
    linked_hashes = get_linked_bot_hashes(bot_hash)
    storage_bot_hash = linked_hashes[0] if linked_hashes else bot_hash
    config = load_bot_config(storage_bot_hash)
    if 'groups' not in config:
        config['groups'] = {}
    config['groups'][str(group_id)] = group_cfg
    return save_bot_config(storage_bot_hash, config)


# ── 权限检查（参考 QQGuildWelcome 实现）──


def is_dice_master(plugin_event):
    try:
        user_hash = OlivaDiceCore.userConfig.getUserHash(
            str(plugin_event.data.user_id), 'user', plugin_event.platform['platform']
        )
        return OlivaDiceCore.ordinaryInviteManager.isInMasterList(plugin_event.bot_info.hash, user_hash)
    except Exception:
        return False


def is_group_admin(plugin_event):
    try:
        sender = getattr(plugin_event.data, 'sender', {})
        if type(sender) is dict:
            return sender.get('role', '') in ['owner', 'admin', 'sub_admin']
    except Exception:
        pass
    return False


def has_permission(plugin_event):
    """骰主或群管理"""
    return is_dice_master(plugin_event) or is_group_admin(plugin_event)


# ── 工具函数 ──


def is_qq_guild(plugin_event):
    """判断是否为 qqGuildV2 平台"""
    return plugin_event.platform.get('sdk', '') == 'qqGuildv2_link'


def get_user_id(plugin_event):
    return str(plugin_event.data.user_id)


def get_user_hash(plugin_event):
    try:
        return OlivaDiceCore.userConfig.getUserHash(
            str(plugin_event.data.user_id), 'user', plugin_event.platform['platform']
        )
    except Exception:
        return str(plugin_event.data.user_id)


def build_markdown_at(plugin_event, member_list):
    """构建 qqGuildV2 Markdown @ 字符串"""
    if not member_list:
        return ''
    try:
        mt = OlivOS.qqGuildv2SDK.markdown_tag
    except Exception:
        mt = None

    at_parts = []
    for m in member_list:
        user_id = m.get('user_id', '')
        if not user_id:
            continue
        if mt is not None and is_qq_guild(plugin_event):
            at_parts.append(mt.at_user(user_id))
    return ' '.join(at_parts)


def replyMsg(plugin_event, message):
    """匹配 OlivaDiceCore 风格的回复消息"""
    plugin_event.reply(message)


# ── 分组管理逻辑 ──


def ensure_group_data(group_cfg):
    """确保 group_cfg 包含必要的字段"""
    if not isinstance(group_cfg, dict):
        group_cfg = {}
    if not isinstance(group_cfg.get('groups'), dict):
        group_cfg['groups'] = {}
    for group_name, group_data in list(group_cfg['groups'].items()):
        if not isinstance(group_data, dict):
            group_data = {}
            group_cfg['groups'][group_name] = group_data
        if not isinstance(group_data.get('members'), list):
            group_data['members'] = []
        else:
            group_data['members'] = [member for member in group_data['members'] if isinstance(member, dict)]
    if not isinstance(group_cfg.get('user_active_group'), dict):
        group_cfg['user_active_group'] = {}
    if 'enabled' not in group_cfg:
        group_cfg['enabled'] = True
    return group_cfg


def get_active_group(group_cfg, user_hash):
    """获取用户的活跃分组名"""
    return group_cfg.get('user_active_group', {}).get(user_hash, '')


def set_active_group(group_cfg, user_hash, group_name):
    """设置用户的活跃分组"""
    if 'user_active_group' not in group_cfg:
        group_cfg['user_active_group'] = {}
    group_cfg['user_active_group'][user_hash] = group_name


def resolve_group_name(group_cfg, user_hash, specified_name):
    """解析分组名：指定则用指定，未指定则用当前用户的活跃组"""
    if specified_name:
        return specified_name
    return get_active_group(group_cfg, user_hash)


def cmd_team_at(plugin_event, group_cfg, user_hash, group_name):
    """处理 .team at 命令：用 Markdown @ 所有分组成员"""
    group_name = resolve_group_name(group_cfg, user_hash, group_name)
    if not group_name:
        replyMsg(plugin_event, '请先指定分组名或设置活跃分组：.team active <分组名>')
        return
    group_data = group_cfg.get('groups', {}).get(group_name)
    if group_data is None:
        replyMsg(plugin_event, f'分组「{group_name}」不存在')
        return
    members = group_data.get('members', [])
    if not members:
        replyMsg(plugin_event, f'分组「{group_name}」中还没有成员')
        return

    # 构建 @ 字符串
    at_text = build_markdown_at(plugin_event, members)
    if not at_text:
        replyMsg(plugin_event, f'分组「{group_name}」中暂无有效成员')
        return

    # 使用当前消息 ID 发送被动 Markdown 回复，避免消耗主动消息额度
    try:
        if not plugin_event.indeAPI.hasAPI('create_markdown_message'):
            replyMsg(plugin_event, '当前 OlivOS 版本不支持 Markdown 消息接口')
            return

        extend_data = getattr(plugin_event.data, 'extend', {})
        if type(extend_data) is not dict:
            extend_data = {}
        chat_type = 'qq_group' if extend_data.get('flag_from_qq', False) else 'guild_channel'
        md_content = f'# 分组 {group_name}\n\n{at_text}\n\n> OlivaDice Team'
        api_result = plugin_event.indeAPI.create_markdown_message(
            chat_type=chat_type,
            chat_id=str(plugin_event.data.group_id),
            markdown={'content': md_content},
            msg_id=extend_data.get('reply_msg_id'),
        )
        if not isinstance(api_result, dict) or not api_result.get('active', False):
            replyMsg(plugin_event, 'Markdown @ 发送失败，请检查机器人 Markdown 权限与 OlivOS 日志')
    except Exception:
        traceback.print_exc()
        replyMsg(plugin_event, 'Markdown @ 发送异常，请检查 OlivOS 日志')


def cmd_team_add(plugin_event, group_cfg, user_hash, group_name):
    """处理 .team add 命令：将当前用户加入指定分组"""
    if not group_name:
        replyMsg(plugin_event, '用法：.team add <分组名>\n或先设置活跃分组后使用 .team add me')
        return
    if group_name.lower() == 'me' or group_name == '我':
        group_name = get_active_group(group_cfg, user_hash)
        if not group_name:
            replyMsg(plugin_event, '你还没有活跃分组，请先使用：.team active <分组名>')
            return
    groups = group_cfg.get('groups', {})
    if group_name not in groups:
        replyMsg(plugin_event, f'分组「{group_name}」不存在，请先让骰主或群管创建：.team create {group_name}')
        return
    members = groups[group_name]['members']
    # 检查是否已经在分组中
    already_member = False
    for m in members:
        if m.get('user_hash') == user_hash:
            already_member = True
            break
    if already_member:
        replyMsg(plugin_event, f'你已经在分组「{group_name}」中了')
        return

    member_info = {
        'user_hash': user_hash,
        'user_id': get_user_id(plugin_event),
        'name': str(getattr(plugin_event.data, 'sender', {}).get('nickname', '')),
    }
    if not member_info['name']:
        member_info['name'] = user_hash[:8]
    members.append(member_info)

    # 自动将该分组设为当前用户的活跃分组
    set_active_group(group_cfg, user_hash, group_name)
    return f'已将你加入分组「{group_name}」，并设为你的活跃分组'


def cmd_team_leave(plugin_event, group_cfg, user_hash, group_name):
    """处理 .team leave 命令：将当前用户移出指定分组"""
    group_name = resolve_group_name(group_cfg, user_hash, group_name)
    if not group_name:
        replyMsg(plugin_event, '请先指定分组名或设置活跃分组：.team active <分组名>')
        return
    groups = group_cfg.get('groups', {})
    if group_name not in groups:
        replyMsg(plugin_event, f'分组「{group_name}」不存在')
        return
    members = groups[group_name]['members']
    new_members = []
    found = False
    for m in members:
        if m.get('user_hash') == user_hash:
            found = True
        else:
            new_members.append(m)
    if not found:
        replyMsg(plugin_event, f'你不在分组「{group_name}」中')
        return
    groups[group_name]['members'] = new_members
    if get_active_group(group_cfg, user_hash) == group_name:
        group_cfg.get('user_active_group', {}).pop(user_hash, None)
    return f'已将你移出分组「{group_name}」'


def cmd_team_create(plugin_event, group_cfg, user_hash, group_name):
    """处理 .team create 命令：创建新分组（需骰主或群管）"""
    if not group_name:
        replyMsg(plugin_event, '用法：.team create <分组名>')
        return
    if not has_permission(plugin_event):
        replyMsg(plugin_event, '权限不足：需要骰主或群管理')
        return
    groups = group_cfg.get('groups', {})
    if group_name in groups:
        replyMsg(plugin_event, f'分组「{group_name}」已存在')
        return
    groups[group_name] = {
        'creator': user_hash,
        'created_at': int(time.time()),
        'members': [],
    }
    return f'已创建分组「{group_name}」'


def cmd_team_del(plugin_event, group_cfg, user_hash, group_name):
    """处理 .team del 命令：删除分组（需骰主或群管）"""
    if not group_name:
        replyMsg(plugin_event, '用法：.team del <分组名>')
        return
    if not has_permission(plugin_event):
        replyMsg(plugin_event, '权限不足：需要骰主或群管理')
        return
    groups = group_cfg.get('groups', {})
    if group_name not in groups:
        replyMsg(plugin_event, f'分组「{group_name}」不存在')
        return
    del groups[group_name]
    # 清理所有用户的该分组活跃记录
    uag = group_cfg.get('user_active_group', {})
    keys_to_remove = []
    for uk, ug in uag.items():
        if ug == group_name:
            keys_to_remove.append(uk)
    for k in keys_to_remove:
        del uag[k]
    return f'已删除分组「{group_name}」'


def cmd_team_list(plugin_event, group_cfg, user_hash, group_name):
    """处理 .team list 命令：列出分组成员"""
    group_name = resolve_group_name(group_cfg, user_hash, group_name)
    if not group_name:
        replyMsg(plugin_event, '请先指定分组名或设置活跃分组：.team active <分组名>')
        return
    groups = group_cfg.get('groups', {})
    if group_name not in groups:
        replyMsg(plugin_event, f'分组「{group_name}」不存在')
        return
    members = groups[group_name].get('members', [])
    if not members:
        replyMsg(plugin_event, f'分组「{group_name}」中还没有成员')
        return
    lines = [f'【{group_name}】成员列表（共 {len(members)} 人）：']
    for idx, m in enumerate(members, start=1):
        name = m.get('name', m.get('user_id', ''))
        lines.append(f'{idx}. {name}')
    replyMsg(plugin_event, '\n'.join(lines))


def cmd_team_active(plugin_event, group_cfg, user_hash, group_name):
    """处理 .team active 命令：设置当前用户的活跃分组"""
    if not group_name:
        replyMsg(plugin_event, '用法：.team active <分组名>')
        return
    groups = group_cfg.get('groups', {})
    if group_name not in groups:
        replyMsg(plugin_event, f'分组「{group_name}」不存在')
        return
    set_active_group(group_cfg, user_hash, group_name)
    return f'已将你的活跃分组设为「{group_name}」'


def persist_command_result(plugin_event, bot_hash, group_id, group_cfg, success_message):
    """仅在配置成功落盘后回复操作成功"""
    if success_message is None:
        return
    if set_group_config(bot_hash, group_id, group_cfg):
        replyMsg(plugin_event, success_message)
    else:
        replyMsg(plugin_event, '配置保存失败，本次操作未生效，请检查 OlivOS 日志')


def cmd_team_status(plugin_event, group_cfg, user_hash):
    """处理 .team（无参数）：查看当前状态"""
    enabled = group_cfg.get('enabled', True)
    active = get_active_group(group_cfg, user_hash)
    groups = group_cfg.get('groups', {})
    group_names = list(groups.keys())
    status_str = '开启' if enabled else '关闭'
    lines = [
        'QQGuildTeam 状态',
        '━━━━━━━━━━━━━━',
        f'本群状态：{status_str}',
        '你的活跃分组：%s' % (active if active else '未设置'),
        f'已有分组（{len(group_names)} 个）：{"、".join(group_names) if group_names else "无"}',
        '━━━━━━━━━━━━━━',
        '.team help 查看帮助',
    ]
    replyMsg(plugin_event, '\n'.join(lines))


# ── 命令分发 ──


def dispatch_team_command(plugin_event, group_cfg, user_hash, sub_cmd, sub_arg):
    """根据子命令分发到对应的处理函数"""
    if sub_cmd == 'help' or sub_cmd == '' or sub_cmd is None:
        replyMsg(plugin_event, HELP_STR)
        return

    if sub_cmd == 'on':
        if not has_permission(plugin_event):
            replyMsg(plugin_event, '权限不足：需要骰主或群管理')
            return
        group_cfg['enabled'] = True
        return '已开启本群 QQGuildTeam'

    if sub_cmd == 'off':
        if not has_permission(plugin_event):
            replyMsg(plugin_event, '权限不足：需要骰主或群管理')
            return
        group_cfg['enabled'] = False
        return '已关闭本群 QQGuildTeam'

    if sub_cmd == 'at':
        cmd_team_at(plugin_event, group_cfg, user_hash, sub_arg)
        return

    if sub_cmd == 'add':
        return cmd_team_add(plugin_event, group_cfg, user_hash, sub_arg)

    if sub_cmd == 'leave':
        return cmd_team_leave(plugin_event, group_cfg, user_hash, sub_arg)

    if sub_cmd == 'create':
        return cmd_team_create(plugin_event, group_cfg, user_hash, sub_arg)

    if sub_cmd == 'del':
        return cmd_team_del(plugin_event, group_cfg, user_hash, sub_arg)

    if sub_cmd == 'list':
        cmd_team_list(plugin_event, group_cfg, user_hash, sub_arg)
        return

    if sub_cmd == 'active':
        return cmd_team_active(plugin_event, group_cfg, user_hash, sub_arg)

    replyMsg(plugin_event, HELP_STR)


# ── 入口事件 ──


class Event:
    def init(plugin_event, Proc):
        """初始化：为每个 bot 创建数据目录"""
        try:
            if 'bot_info_dict' in Proc.Proc_data:
                for bot_hash, bot_info in Proc.Proc_data['bot_info_dict'].items():
                    platform = getattr(bot_info, 'platform', {})
                    if type(platform) is not dict or platform.get('sdk', '') != 'qqGuildv2_link':
                        continue
                    dir_path = os.path.join(base_data_path, bot_hash)
                    if not os.path.exists(dir_path):
                        os.makedirs(dir_path)
        except Exception:
            traceback.print_exc()

    def group_message(plugin_event, Proc):
        """仅处理 qqGuildV2 平台的 .team 命令"""
        if not is_qq_guild(plugin_event):
            return

        try:
            raw_msg = plugin_event.data.message.strip()

            # 匹配 .team 开头
            if not isMatchWordStart(raw_msg, CMD_DOT, isCommand=True):
                return

            # 精确匹配命令前缀，确保是 ".team" 或 ".team " 开头
            tmp_rest = getMatchWordStartRight(raw_msg, CMD_DOT)
            tmp_rest = skipSpaceStart(tmp_rest)

            # 拦截事件，阻止继续传给 OlivaDiceCore
            plugin_event.set_block()

            bot_hash = plugin_event.bot_info.hash
            group_id = str(plugin_event.data.group_id)
            group_cfg = get_group_config(bot_hash, group_id)
            group_cfg = ensure_group_data(group_cfg)

            user_hash = get_user_hash(plugin_event)

            # 如果插件关闭，只允许 on/off 命令
            if not group_cfg.get('enabled', True):
                if isMatchWordStart(tmp_rest, 'on'):
                    if has_permission(plugin_event):
                        group_cfg['enabled'] = True
                        if set_group_config(bot_hash, group_id, group_cfg):
                            Proc.log(2, f'[QQGuildTeam] 群 {group_id} 开启插件')
                            replyMsg(plugin_event, '已开启本群 QQGuildTeam')
                        else:
                            replyMsg(plugin_event, '配置保存失败，本次操作未生效，请检查 OlivOS 日志')
                    else:
                        replyMsg(plugin_event, '权限不足：需要骰主或群管理')
                elif isMatchWordStart(tmp_rest, 'off'):
                    replyMsg(plugin_event, '插件已关闭')
                elif isMatchWordStart(tmp_rest, 'status') or tmp_rest == '':
                    cmd_team_status(plugin_event, group_cfg, user_hash)
                elif isMatchWordStart(tmp_rest, 'help'):
                    replyMsg(plugin_event, HELP_STR)
                else:
                    replyMsg(plugin_event, 'QQGuildTeam 当前已关闭，发送 .team on 重新开启')
                return

            # 解析子命令
            command_map = {
                'help': 'help',
                '帮助': 'help',
                'on': 'on',
                '开启': 'on',
                '启用': 'on',
                'off': 'off',
                '关闭': 'off',
                '禁用': 'off',
                'at': 'at',
                '艾特': 'at',
                '@': 'at',
                'add': 'add',
                '加入': 'add',
                '+': 'add',
                'leave': 'leave',
                '退出': 'leave',
                '离开': 'leave',
                '-': 'leave',
                'create': 'create',
                '创建': 'create',
                '新建': 'create',
                'del': 'del',
                'delete': 'del',
                '删除': 'del',
                '移除': 'del',
                'list': 'list',
                '列表': 'list',
                '查看': 'list',
                'active': 'active',
                '活跃': 'active',
                '当前': 'active',
            }

            sub_cmd = None
            sub_arg = None

            # 先用命令映射匹配
            for cmd_key, cmd_val in command_map.items():
                if isMatchWordStart(tmp_rest, cmd_key):
                    sub_cmd = cmd_val
                    sub_arg_tmp = getMatchWordStartRight(tmp_rest, cmd_key)
                    sub_arg = skipSpaceStart(sub_arg_tmp)
                    break

            if sub_cmd is not None:
                success_message = dispatch_team_command(plugin_event, group_cfg, user_hash, sub_cmd, sub_arg)
                persist_command_result(plugin_event, bot_hash, group_id, group_cfg, success_message)
                return

            # 没有匹配到已知命令 → 检查是否是 .team <分组名> add 格式
            # 如果 tmp_rest 中有空格，第一部分可能是分组名
            tmp_parts = tmp_rest.split(None, 1)
            if len(tmp_parts) >= 2:
                possible_group = tmp_parts[0]
                possible_action = tmp_parts[1]
                # 检查 possible_action 的开头是否是 add/at/leave 等
                if isMatchWordStart(possible_action, 'add'):
                    success_message = cmd_team_add(plugin_event, group_cfg, user_hash, possible_group)
                    persist_command_result(plugin_event, bot_hash, group_id, group_cfg, success_message)
                    return
                if isMatchWordStart(possible_action, 'at'):
                    cmd_team_at(plugin_event, group_cfg, user_hash, possible_group)
                    return
                if isMatchWordStart(possible_action, 'leave'):
                    success_message = cmd_team_leave(plugin_event, group_cfg, user_hash, possible_group)
                    persist_command_result(plugin_event, bot_hash, group_id, group_cfg, success_message)
                    return
                if isMatchWordStart(possible_action, 'list'):
                    cmd_team_list(plugin_event, group_cfg, user_hash, possible_group)
                    return

            # 纯 .team → 查看状态
            if tmp_rest == '':
                cmd_team_status(plugin_event, group_cfg, user_hash)
                return

            # 未识别
            replyMsg(plugin_event, HELP_STR)

        except Exception:
            traceback.print_exc()
            try:
                replyMsg(plugin_event, 'QQGuildTeam 处理异常，请查看日志')
            except Exception:
                pass

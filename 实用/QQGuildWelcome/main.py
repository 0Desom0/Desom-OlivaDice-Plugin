# -*- encoding: utf-8 -*-
"""
QQGuildWelcome - QQ官方机器人Markdown入群欢迎插件

仅对 qqGuildV2 平台生效，其他 SDK 直接 return 交由 OlivaDiceCore 原生处理。
默认开启，设置 Markdown 内容后接管入群欢迎并拦截 OlivaDiceCore 默认欢迎；
未设置内容时不拦截，原生欢迎正常触发。
.welcome off 可关闭本插件回退到 OlivaDiceCore 原生 welcomeMsg。

命令：
  .welcome on / off       开关本群 Markdown 欢迎（off 回退原生）
  .welcome set <内容>     设置欢迎 Markdown（支持多行与快捷占位符）
  .welcome show           查看当前欢迎 Markdown 原文
  .welcome clear          清空欢迎 Markdown
  .welcome help           查看完整帮助
  .welcome                查看状态

快捷占位符（发送时自动替换）：
  {at}              → @新成员
  {id}              → 新成员ID
  {enter:文本}      → 点击直接发送的指令按钮
  {input:文本}      → 点击插入输入框的指令按钮
  {input:文本|显示} → 同上，自定义显示文本

权限：骰主 或 群管理（owner/admin/sub_admin）
数据按 bot_hash 分目录存储，群链 bot 自动回退查找链接账号的配置。
"""

import json
import os
import re
import traceback

import OlivOS
import OlivaDiceCore

# 数据存储基础路径（按 bot_hash 分目录）
base_data_path = 'plugin/data/QQGuildWelcome'

# 命令前缀
CMD = '.welcome'

# 帮助文本
HELP_STR = (
    'QQ官方机器人 Markdown 欢迎\n'
    '━━━━━━━━━━━━━━\n'
    '.welcome on  开启本群Markdown欢迎\n'
    '.welcome off  关闭，回退OlivaDiceCore原生欢迎\n'
    '.welcome set <内容>  设置欢迎Markdown（支持多行）\n'
    '.welcome show  查看当前欢迎原文\n'
    '.welcome clear  清空欢迎内容\n'
    '.welcome help  显示本帮助\n'
    '━━━━━━━━━━━━━━\n'
    '快捷占位符（入群时自动替换）：\n'
    '{at}  @新成员\n'
    '{id}  新成员ID\n'
    '{enter:.r 2d6}  点击直接发送\n'
    '{input:.st 力量50}  点击插入输入框\n'
    '{input:.st 力量50|快捷录入}  自定义显示文本\n'
    '━━━━━━━━━━━━━━\n'
    '示例：\n'
    '.welcome set # 欢迎加入\n'
    '{at} 你好！请先阅读群规\n'
    '{enter:.r 2d6}\n'
    '{input:.st 力量50|快捷录入属性}\n'
    '> OlivaDice\n'
    '━━━━━━━━━━━━━━\n'
    '仅 qqGuildV2 平台生效，其他平台走原生欢迎'
)


def get_config_path(bot_hash):
    """获取指定 bot 的配置文件路径"""
    return os.path.join(base_data_path, bot_hash, 'config.json')


def load_bot_config(bot_hash):
    """读取单个 bot 的配置"""
    path = get_config_path(bot_hash)
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {'groups': {}}


def save_bot_config(bot_hash, config):
    """写入单个 bot 的配置"""
    path = get_config_path(bot_hash)
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
    except Exception:
        traceback.print_exc()


def get_linked_bot_hashes(bot_hash):
    """获取群链中所有 bot 的 hash 列表（含自身），参考 OlivaDiceLogger 实现"""
    try:
        relations = OlivaDiceCore.console.getAllAccountRelations()
        # 当前 bot 是主账号
        if bot_hash in relations:
            res = [bot_hash]
            res.extend(relations[bot_hash])
            return res
        # 当前 bot 是从账号
        for master, slaves in relations.items():
            if bot_hash in slaves:
                res = [master]
                res.extend(slaves)
                return res
    except Exception:
        pass
    return [bot_hash]


def get_group_config(bot_hash, group_id):
    """获取单个群的配置，群链回退：先查自身，再查链接账号"""
    # 先查当前 bot
    cfg = load_bot_config(bot_hash).get('groups', {}).get(str(group_id), {})
    if cfg:
        return cfg
    # 群链回退：查链接的其他 bot
    for linked_hash in get_linked_bot_hashes(bot_hash):
        if linked_hash == bot_hash:
            continue
        cfg = load_bot_config(linked_hash).get('groups', {}).get(str(group_id), {})
        if cfg:
            return cfg
    return {}


def set_group_config(bot_hash, group_id, group_cfg):
    """写入单个群的配置（始终写入当前 bot）"""
    config = load_bot_config(bot_hash)
    if 'groups' not in config:
        config['groups'] = {}
    config['groups'][str(group_id)] = group_cfg
    save_bot_config(bot_hash, config)


def is_dice_master(plugin_event):
    """骰主检查"""
    try:
        user_hash = OlivaDiceCore.userConfig.getUserHash(
            str(plugin_event.data.user_id),
            'user',
            plugin_event.platform['platform']
        )
        return OlivaDiceCore.ordinaryInviteManager.isInMasterList(
            plugin_event.bot_info.hash,
            user_hash
        )
    except Exception:
        return False


def is_group_admin(plugin_event):
    """群管理检查（owner/admin/sub_admin）"""
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


def is_qq_guild(plugin_event):
    """判断是否为 qqGuildV2 平台"""
    return plugin_event.platform.get('sdk', '') == 'qqGuildv2_link'


def replace_placeholders(markdown_text, plugin_event):
    """替换欢迎消息中的快捷占位符，调用 markdown_tag 生成实际标签"""
    user_id = str(plugin_event.data.user_id)
    try:
        mt = OlivOS.qqGuildv2SDK.markdown_tag
    except Exception:
        mt = None

    # {at} → @新成员
    if mt is not None:
        res = markdown_text.replace('{at}', mt.at_user(user_id))
    else:
        res = markdown_text.replace('{at}', '<qqbot-at-user id="%s" />' % user_id)

    # {id} → 新成员ID
    res = res.replace('{id}', user_id)

    # {enter:文本} → 点击直接发送的指令按钮
    if mt is not None:
        res = re.sub(
            r'\{enter:([^}]+)\}',
            lambda m: mt.cmd_enter(m.group(1)),
            res
        )
    else:
        res = re.sub(r'\{enter:([^}]+)\}', '', res)

    # {input:文本|显示} 或 {input:文本} → 点击插入输入框的指令按钮
    if mt is not None:
        res = re.sub(
            r'\{input:([^}|]+)(?:\|([^}]+))?\}',
            lambda m: mt.cmd_input(m.group(1), show=m.group(2)),
            res
        )
    else:
        res = re.sub(r'\{input:([^}|]+)(?:\|([^}]+))?\}', '', res)

    return res


class Event(object):

    def init(plugin_event, Proc):
        """初始化：为每个 bot 创建数据目录"""
        try:
            if 'bot_info_dict' in Proc.Proc_data:
                for bot_hash in Proc.Proc_data['bot_info_dict']:
                    dir_path = os.path.join(base_data_path, bot_hash)
                    if not os.path.exists(dir_path):
                        os.makedirs(dir_path)
        except Exception:
            traceback.print_exc()

    def group_message(plugin_event, Proc):
        """处理 .welcome 命令，仅 qqGuildV2，其他 SDK 直接 return"""
        if not is_qq_guild(plugin_event):
            return

        try:
            raw_msg = plugin_event.data.message.strip()
            if not raw_msg.startswith(CMD):
                return

            # 精确匹配 ".welcome" 或 ".welcome " 开头
            rest = raw_msg[len(CMD):]
            if rest != '' and not rest.startswith(' '):
                return

            rest = rest.strip()

            # 拦截事件，防止继续传到 OlivaDiceCore
            plugin_event.set_block()

            bot_hash = plugin_event.bot_info.hash
            group_id = str(plugin_event.data.group_id)
            group_cfg = get_group_config(bot_hash, group_id)

            # .welcome → 查看状态
            if rest == '':
                enabled = group_cfg.get('enabled', True)
                has_md = bool(group_cfg.get('markdown', ''))
                status_str = '开启' if enabled else '关闭（使用原生欢迎）'
                md_str = '已设置' if has_md else '未设置'
                plugin_event.reply(
                    'Markdown 欢迎状态：%s\n欢迎内容：%s\n发送 .welcome help 查看帮助' % (status_str, md_str)
                )
                return

            # .welcome help
            if rest == 'help':
                plugin_event.reply(HELP_STR)
                return

            # 以下操作需要权限
            if not has_permission(plugin_event):
                plugin_event.reply('权限不足：需要骰主或群管理')
                return

            # .welcome on
            if rest == 'on':
                group_cfg['enabled'] = True
                set_group_config(bot_hash, group_id, group_cfg)
                Proc.log(2, '[QQGuildWelcome] 群 %s 开启 Markdown 欢迎' % group_id)
                plugin_event.reply('已开启本群 Markdown 欢迎')
                return

            # .welcome off → 回退 OlivaDiceCore 原生欢迎
            if rest == 'off':
                group_cfg['enabled'] = False
                set_group_config(bot_hash, group_id, group_cfg)
                Proc.log(2, '[QQGuildWelcome] 群 %s 关闭 Markdown 欢迎' % group_id)
                plugin_event.reply('已关闭本群 Markdown 欢迎，恢复 OlivaDiceCore 原生欢迎')
                return

            # .welcome set <内容>
            if rest.startswith('set '):
                content = rest[4:].strip()
                if content == '':
                    plugin_event.reply('用法：.welcome set <Markdown内容>\n支持多行，发送 .welcome help 查看占位符')
                    return
                group_cfg['markdown'] = content
                set_group_config(bot_hash, group_id, group_cfg)
                Proc.log(2, '[QQGuildWelcome] 群 %s 设置欢迎 Markdown (%d 字符)' % (group_id, len(content)))
                plugin_event.reply('已设置欢迎 Markdown（%d 字符）\n.welcome show 查看原文' % len(content))
                return

            # .welcome show
            if rest == 'show':
                md = group_cfg.get('markdown', '')
                if md == '':
                    plugin_event.reply('当前未设置欢迎 Markdown')
                else:
                    plugin_event.reply('当前欢迎 Markdown 原文：\n%s' % md)
                return

            # .welcome clear
            if rest == 'clear':
                group_cfg['markdown'] = ''
                set_group_config(bot_hash, group_id, group_cfg)
                Proc.log(2, '[QQGuildWelcome] 群 %s 清空欢迎 Markdown' % group_id)
                plugin_event.reply('已清空欢迎 Markdown')
                return

            # 未识别的子命令
            plugin_event.reply(HELP_STR)

        except Exception:
            traceback.print_exc()

    def group_member_increase(plugin_event, Proc):
        """入群事件：仅 qqGuildV2，开启时发送 Markdown 欢迎并拦截后续插件"""
        if not is_qq_guild(plugin_event):
            return

        try:
            # 旧版 OlivOS 没有 create_markdown_message 时直接回退原生
            if not plugin_event.indeAPI.hasAPI('create_markdown_message'):
                return

            bot_hash = plugin_event.bot_info.hash
            group_id = str(plugin_event.data.group_id)

            # 机器人自身入群不拦截，交给 OlivaDiceCore 发 strHello
            try:
                new_member_hash = OlivaDiceCore.userConfig.getUserHash(
                    str(plugin_event.data.user_id),
                    'user',
                    plugin_event.platform['platform']
                )
                if new_member_hash == bot_hash:
                    return
            except Exception:
                pass

            # 读取本群配置（群链回退：先查自身，再查链接账号）
            group_cfg = get_group_config(bot_hash, group_id)
            if not group_cfg.get('enabled', True):
                return

            # 未设置 Markdown 内容时不拦截，让 OlivaDiceCore 原生欢迎继续
            md_content = group_cfg.get('markdown', '')
            if md_content == '':
                return

            # 拦截后续插件（阻止 OlivaDiceCore 默认欢迎）
            plugin_event.set_block()

            # 替换快捷占位符
            final_md = replace_placeholders(md_content, plugin_event)

            # 确定会话类型
            extend_data = getattr(plugin_event.data, 'extend', {})
            if type(extend_data) is not dict:
                extend_data = {}
            chat_type = 'qq_group' if extend_data.get('flag_from_qq', False) else 'guild_channel'

            # 发送 Markdown 欢迎（主动消息，GROUP_MEMBER_ADD 不支持被动回复）
            plugin_event.indeAPI.create_markdown_message(
                chat_type=chat_type,
                chat_id=group_id,
                markdown={'content': final_md}
            )
            Proc.log(2, '[QQGuildWelcome] 群 %s 已发送 Markdown 欢迎' % group_id)

        except Exception:
            traceback.print_exc()

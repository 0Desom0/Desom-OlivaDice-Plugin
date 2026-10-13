""".mcs 指令与 Core 的模糊搜索交互。"""

import re

import OlivaDiceCore

from . import msgCustom, runtime
from .store import InvalidInput


def command_text(event, command_name='mcs'):
    text = str(event.data.message)
    text = re.sub(r'^\[CQ:reply,[^\]]*\]\s*', '', text)
    # 只移除开头对当前 Bot / all 的 @，避免他人被 @ 时误触发。
    ids = {str(event.bot_info.id), str(event.base_info.get('self_id')), 'all'}
    extend = getattr(event.data, 'extend', {}) or {}
    ids.update(str(extend[key]) for key in ('sub_self_id', 'sub_self_open_id') if extend.get(key) is not None)
    while True:
        match = re.match(r'^\s*\[CQ:at,qq=([^,\]]+)[^\]]*\]\s*', text)
        if not match or match[1] not in ids:
            break
        text = text[match.end() :]
    text = OlivaDiceCore.msgReply.htmlUnescape(text)
    text, command = OlivaDiceCore.msgReply.msgIsCommand(text, OlivaDiceCore.crossHook.dictHookList['prefix'])
    text = text.strip()
    if not command or not OlivaDiceCore.msgReply.isMatchWordStart(text, command_name, isCommand=True):
        return None
    return OlivaDiceCore.msgReply.getMatchWordStartRight(text, command_name).strip()


def send(event, text):
    values = OlivaDiceCore.msgCustom.dictTValue.copy()
    values.update(OlivaDiceCore.msgCustom.dictGValue)
    values['tUserName'] = event.data.sender.get('name', '用户')
    values['tName'] = values['tUserName']
    OlivaDiceCore.msgCustomManager.dictTValueInit(event, values)
    values['tMcsResult'] = text
    replies = OlivaDiceCore.msgCustom.dictStrCustomDict[event.bot_info.hash]
    template = replies.get('strMcsResult', msgCustom.dictStrCustom['strMcsResult'])
    OlivaDiceCore.msgReply.replyMsg(event, OlivaDiceCore.msgCustomManager.formatReplySTR(template, values))


def allowed(event, global_action):
    if not global_action:
        if event.plugin_info.get('func_type') != 'group_message':
            return False
        if event.data.sender.get('role') in ('owner', 'admin'):
            return True
    # 本群设置允许群管理或当前 bot 的骰主；全局设置仍仅允许骰主。
    user_hash = OlivaDiceCore.userConfig.getUserHash(event.data.user_id, 'user', event.platform['platform'])
    return OlivaDiceCore.ordinaryInviteManager.isInMasterList(event.bot_info.hash, user_hash)


def _name(store, bot, number):
    return next(
        (item['name'] for item in store.list_replies(bot) if item['selection'] == number), f'缺失回复 #{number}'
    )


def handle(event, proc):
    if runtime.STORE is None:
        return
    try:
        text = command_text(event)
        if text is None:
            return
        # 当前指令由本插件完整处理；模糊选择中的数字消息仍交给 Core。
        event.set_block()
        store, bot = runtime.STORE, event.bot_info.hash
        group_hash = store.group_hash(event) if event.plugin_info.get('func_type') == 'group_message' else None
        if text.casefold() == 'help':
            send(event, msgCustom.COMMAND_HELP)
            return
        if text.casefold() == 'list':
            lines = [
                f'{item["selection"]}. {item["name"]}' + ('（文件不可用）' if not item['available'] else '')
                for item in store.list_replies(bot)
            ]
            send(event, '当前 bot 自定义回复：\n' + '\n'.join(lines) + '\n1=Core 原始回复；2=全默认 smp。')
            return
        if not text or text.casefold() == 'show':
            if group_hash is None:
                send(event, '查看本群规则请在群内使用 .mcs show。私聊可用 .mcs list/help 和骰主 global 指令。')
                return
            status = store.status(bot, group_hash)
            group = status['group']
            state = '开' if group is None or group['enabled'] else '关'
            source = '继承全局' if status['inherited'] else '本群单独设置'
            lines = [
                f'全局开关：{"开" if status["global"]["enabled"] else "关"}；本群开关：{state}',
                f'选择：{status["selected"]}. {_name(store, bot, status["selected"])}（{source}）',
                f'实际生效：{status["effective"]}. {_name(store, bot, status["effective"])}',
            ]
            if status['missing']:
                lines.append('所选回复文件不可用，暂使用 Core 原始回复。')
            send(event, '\n'.join(lines))
            return
        global_action = OlivaDiceCore.msgReply.isMatchWordStart(text, 'global')
        if global_action:
            text = OlivaDiceCore.msgReply.getMatchWordStartRight(text, 'global').strip()
        elif group_hash is None:
            send(event, '本群设置只能在群内使用。全局设置请使用 .mcs global …。')
            return
        if not allowed(event, global_action):
            send(
                event,
                '仅骰主可修改当前 bot 的全局设置。'
                if global_action
                else '仅群主、管理员或当前 bot 的骰主可修改本群设置。',
            )
            return
        target = None if global_action else group_hash
        label = '当前 bot 全局' if global_action else '本群'
        if text.casefold() in ('on', 'off'):
            enabled = text.casefold() == 'on'
            store.select(bot, enabled=enabled, group_hash=target)
            send(
                event,
                f'{label}插件已{"开启" if enabled else "关闭"}。'
                + ('关闭期间使用原始回复。' if not enabled else ''),
            )
            return
        if not text:
            send(event, '用法：.mcs global [回复名/序号/on/off]')
            return
        items = [item for item in store.list_replies(bot) if item['available']]
        selected = None
        if text.isascii() and text.isdecimal():
            selected = next((item['selection'] for item in items if item['selection'] == int(text)), None)
        else:
            selected = next((item['selection'] for item in items if item['name'] == text), None)
            if selected is None:
                replies = {**msgCustom.dictStrCustom, **OlivaDiceCore.msgCustom.dictStrCustomDict[bot]}
                values = OlivaDiceCore.msgCustom.dictTValue.copy()
                values.update(OlivaDiceCore.msgCustom.dictGValue)
                values['tUserName'] = event.data.sender.get('name', '用户')
                values['tName'] = values['tUserName']
                OlivaDiceCore.msgCustomManager.dictTValueInit(event, values)
                # 等待用户期间绝不持文件锁。选择结束后再次校验权限及回复存在性。
                name = OlivaDiceCore.helpDoc.fuzzySearchAndSelect(
                    key_str=text,
                    item_list=[item['name'] for item in items],
                    bot_hash=bot,
                    plugin_event=event,
                    strRecommendKey='strMcsRecommend',
                    strErrorKey='strMcsNotFound',
                    dictStrCustom=replies,
                    dictTValue=values,
                )
                if name is None:
                    return
                selected = next((item['selection'] for item in store.list_replies(bot) if item['name'] == name), None)
        if selected is None:
            raise InvalidInput('回复序号不存在，请使用 .mcs list 查看。')
        if not allowed(event, global_action):
            raise InvalidInput('当前用户没有修改权限。')
        status = store.select(bot, model=selected, group_hash=target)
        suffix = '' if status['enabled'] else '（插件开关关闭，当前仍使用 Core 原始回复）'
        send(event, f'{label}已选择 {selected}. {_name(store, bot, selected)}{suffix}。')
    except (InvalidInput, OSError, ValueError) as exc:
        send(event, f'设置失败：{exc}')
    except Exception:
        proc.log(4, 'MultiCustomSwitch: 指令处理失败。')
        try:
            send(event, '处理失败，请检查 OlivOS 日志。')
        except Exception:
            proc.log(4, 'MultiCustomSwitch: 无法发送错误回复。')

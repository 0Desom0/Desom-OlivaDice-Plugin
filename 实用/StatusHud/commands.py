"""hud 命令解析及权限检查。"""

from .storage import StorageError

HELP = (
    'StatusHud 帮助\n'
    '.hud help：显示本帮助\n'
    '.hud on / .hud off：为自己开启 / 关闭 HUD\n'
    '.hud：切换当前有效开关，并保存为个人设置\n'
    '.hud show：查看当前开关、来源和全局默认\n'
    '.hud global on / off：设置全局默认，仅当前 bot 的骰主可用\n'
    '首次默认开启；个人 on/off 优先于全局默认，未手动设置者跟随全局。\n'
    '调用过 OneDice roll 的结果（例如 .ra / .r / .ww / .sh / .dd 等）会在首行显示当前 sn；纯计算和骰点错误也适用。\n'
    '本插件支持群链。'
    '代投使用被代投人的开关与 sn'
)


def command_text(event, olivos):
    message = getattr(event.data, 'message', '')
    if isinstance(message, str):
        mode = event.plugin_info.get('message_mode_tx', 'old_string')
        message = olivos.messageAPI.Message_templet(mode, message)
    elif not isinstance(message, olivos.messageAPI.Message_templet):
        message = olivos.messageAPI.Message_templet('olivos_para', message)
    if not message.active:
        return ''
    parts = list(message.data)
    # 对齐轻量模板：去掉开头的引用段；开头的 at 必须确实指向当前 bot。
    if parts and isinstance(parts[0], olivos.messageAPI.PARA.reply):
        parts.pop(0)
    at_ids = []
    prefix = []
    while parts:
        part = parts[0]
        if isinstance(part, olivos.messageAPI.PARA.at):
            at_ids.append(str(part.data['id']))
            parts.pop(0)
        elif isinstance(part, olivos.messageAPI.PARA.text) and not part.data['text'].strip():
            prefix.append(part.data['text'])
            parts.pop(0)
        else:
            break
    if at_ids:
        bot_ids = {str(event.base_info['self_id']), 'all'}
        extend = getattr(event.data, 'extend', {}) or {}
        for key in ('sub_self_id', 'sub_self_open_id'):
            if extend.get(key) is not None:
                bot_ids.add(str(extend[key]))
        if not bot_ids.intersection(at_ids):
            return ''
    elif prefix:
        # 前导空白可正常忽略。
        pass
    if not parts or not isinstance(parts[0], olivos.messageAPI.PARA.text):
        return ''
    return ''.join(part.data['text'] for part in parts if isinstance(part, olivos.messageAPI.PARA.text)).lstrip()


def is_command(event, olivos, core):
    text = command_text(event, olivos)
    prefixes = core.crossHook.dictHookList.get('prefix', ['.', '。', '/'])
    return bool(text and any(text.startswith(prefix) for prefix in prefixes))


def handle(event, proc, manager, olivos):
    text = command_text(event, olivos)
    if not text or text[0] not in '.。/':
        return
    text = text[1:].lstrip()
    if not text.lower().startswith('hud'):
        return
    argument = text[3:].strip().lower()
    core = manager.core
    if event.plugin_info['func_type'] == 'private_message':
        if core.console.getConsoleSwitchByHash('disablePrivate', event.bot_info.hash) == 1:
            return
    else:
        core.msgReply.nativeMsgBlocker(event, proc)
        if event.blocked:
            return
    bot_hash = event.bot_info.hash
    user_id = event.data.user_id
    platform = event.platform['platform']
    try:
        if argument == 'help':
            response = HELP
        elif argument in ('', 'on', 'off'):
            enabled = None if not argument else argument == 'on'
            enabled = manager.storage.set_user(bot_hash, user_id, platform, enabled)
            response = '个人 HUD 已' + ('开启。' if enabled else '关闭。')
        elif argument == 'show':
            status = manager.storage.status(bot_hash, user_id, platform)
            source = '个人设置' if status['source'] == 'user' else '群链全局默认'
            response = (
                f"HUD：{'开启' if status['enabled'] else '关闭'}（{source}）\n"
                f"群链全局默认：{'开启' if status['global_enabled'] else '关闭'}"
            )
        elif argument.startswith('global'):
            action = argument[6:].strip()
            if action not in ('on', 'off'):
                response = '用法：.hud global on / off'
            elif not core.ordinaryInviteManager.isInMasterList(
                bot_hash, core.userConfig.getUserHash(user_id, 'user', platform),
            ):
                response = '只有当前 bot 的 OlivaDiceCore 骰主可以修改全局默认。'
            else:
                manager.storage.set_global(bot_hash, action == 'on')
                response = '群链全局默认已' + ('开启。' if action == 'on' else '关闭。')
        else:
            response = '未知的 HUD 参数，请使用 .hud help 查看帮助。'
    except StorageError as error:
        manager.log('HUD 设置操作失败', error)
        response = 'HUD 数据读取或保存失败，未确认保存成功；请检查日志。'
    core.msgReply.replyMsg(event, response)
    event.set_block()

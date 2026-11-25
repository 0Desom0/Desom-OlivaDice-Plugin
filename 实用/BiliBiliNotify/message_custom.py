# 固定文案，不从存储加载或通过 WebUI 修改。
TEXT = {
    'help': (
        'B站订阅推送 · 命令\n'
        '{prefix}bili up add|del <UID> / up list\n'
        '{prefix}bili up live|dynamic|video <UID> <on|off>\n'
        '{prefix}bili up sub|unsub <UID> / up subs\n'
        '{prefix}bili push live|dynamic|video <on|off>\n'
        '{prefix}bili atall <on|off> / status / test <UID> / help'
    ),
    'private': '这个功能只在群里用哦~ 把命令发到群里就行。',
    'denied': '需要群主、管理员、骰主或全局白名单权限。',
    'persist': '写入失败，检查目录权限。',
    'error': '处理失败，请稍后重试。',
    'bad_uid': '请提供一个 UID（纯数字）哦~ 比如 {prefix}bili up add 2',
    'up_missing': '没查到 UID {uid} 的主播信息。\n可能是 UID 填错了，或者 B站风控了。稍后再试一次，或在 WebUI 里填 Cookie。',
    'duplicate': '这个主播已经在本群的订阅列表里了~',
    'added': '已添加：{identity}\n本群推送：{switches}\n@全体：{at_all}',
    'at_all_hint': '（{prefix}bili atall on 可开）',
    'removed': '已从本群移除：UID {uid}\n顺带清理了 {count} 位群友的订阅。',
    'list_empty': '本群还没有添加任何主播，管理员可以用 {prefix}bili up add <UID> 添加。',
    'list_head': '本群主播（{count} 个）：',
    'list_item': '{index}. {identity} · {switches} · 订阅 {count} 人',
    'identity': '{name}（UID {uid}{room}）',
    'uid': 'UID {uid}',
    'uid_room': 'UID {uid}（房间 {room_id}）',
    'identity_room': ' / 房间 {room_id}',
    'enabled': '开',
    'disabled': '关',
    'switch_on': '开启',
    'switch_off': '关闭',
    'switch_set': '{label}{state}',
    'switch_summary': '{label} {state}',
    'up_toggle': '已{state} UID {uid} 的{label}检测（影响所有群）。',
    'subscription_missing': '本群还没有添加 UID {uid} 的主播，只有本群已添加的主播才能订阅哦~',
    'subscribed': '订阅成功：UID {uid} 开播时会 @ 你。',
    'unsubscribed': '已取消订阅：UID {uid}',
    'subs_head': '你在本群订阅了 {count} 个主播：',
    'subs_item': '· {identity}',
    'push_toggle': '本群{label}推送已{state}。',
    'atall_on': '本群 @全体 已开启（onebot 每天最多 {limit} 次；{qq}）。',
    'atall_qq_once': 'qqGuild 每次开播只 @ 一次',
    'atall_qq_any': 'qqGuild 不限制每次开播的次数',
    'atall_off': '本群 @全体 已关闭。',
    'status': 'BiliBiliNotify 运行中\n· 主播 {total} 个 / 本群 {local} 个\n{checks}\n· 今日 @全体：{used}/{limit}',
    'last_check': '· 上次{label}检查：{elapsed}',
    'never': '尚未检查',
    'seconds_ago': '{count} 秒前',
    'minutes_ago': '{count} 分钟前',
    'test_empty': '没有可用的测试内容。',
    'test_failed': '测试推送失败，请检查运行日志。',
    'test_prefix': '[测试] ',
    'risk_warning': 'B站风控，请在 WebUI 填 Cookie。',
}

OP = {
    'start': '{at_all}【B站开播】{name} 开播啦！\n标题：{title}\n分区：{area}\n时间：{time}\n{image}{link}{subscribers}',
    'area': '【B站换分区】{name} 切换了分区\n标题：{title}\n新分区：{area}\n{image}{link}',
    'end': '【B站下播】{name} 下播了\n标题：{title}\n下播分区：{area}',
    'dynamic': '【B站动态】{name} 发布了新动态\n{body}\n{image}{link}',
    'video': '【B站投稿】{name} 发布了新视频\n标题：{title}\n{image}{link}',
}

MARKDOWN = {
    'start': ('**B站开播** · {name}\n{image}\n**标题**：{title}\n**分区**：{area}\n'
              '**时间**：{time}\n**链接**：{link}\n{at_all}{subscribers}'),
    'area': '**B站换分区** · {name}\n{image}\n**标题**：{title}\n**新分区**：{area}\n**链接**：{link}',
    'end': '**B站下播** · {name}\n\n**标题**：{title}\n**下播分区**：{area}',
    'dynamic': '**B站动态** · {name}\n{image}\n{body}\n**链接**：{link}',
    'video': '**B站投稿** · {name}\n{image}\n**标题**：{title}\n**链接**：{link}',
}

# 固定文案，不从存储加载或通过 WebUI 修改。
TEXT = {
    'help': (
        'B站订阅推送 · 命令总览（前缀 {prefix}）\n'
        '{prefix}bpush help sub · 订阅与主播管理\n'
        '{prefix}bpush help push · 群推送与提醒\n'
        '{stats}'
        '{prefix}bpush up list · 查看本群主播\n'
        '{prefix}bpush up sub <UID> · 订阅开播提醒\n'
        '{prefix}bpush status · 查看运行状态'
    ),
    'help_stats_entry': '{prefix}bpush help stats · 直播统计与排行查询\n',
    'help_stats': (
        'B站订阅推送 · 直播统计与排行查询\n'
        '{session_images}'
        '{prefix}bpush room [主播] · 房间统计（本场与累计）\n'
        '{prefix}bpush me [B站UID或昵称] [主播] · 个人统计\n'
        '{prefix}bpush bind <B站UID> · 绑定自己的 B站账号\n'
        '{prefix}bpush rank <弹幕|礼物|SC|盲盒|进场|点赞> [本场|总榜] [主播] · 查看前十名\n'
        '{prefix}bpush status · 查看直播及其他类型的检查状态\n'
        '中文命令：房间统计、个人统计、绑定、排行。\n'
        '群成员均可查询。主播支持 UID 或昵称关键词，本群仅订阅一位时可省略。\n'
        '绑定后可用 me 或 me [主播]；昵称含空格时可用英文双引号包住。'
    ),
    'help_stats_report': '{prefix}bpush report [主播]（直播报告）· 查看当前或最近一场的报告图\n',
    'help_stats_cloud': '{prefix}bpush cloud [主播]（词云）· 查看当前或最近一场的弹幕词云\n',
    'stats_empty_session_image': '直播场次记录后，可在群内查询报告和词云。',
    'stats_empty_cloud': '累积有效文字弹幕后即可查看弹幕词云。',
    'stats_image_failed': '图片生成或发送失败，请稍后再试。',
    'session_image_caption': '{label} · {name}',
    'stats_disabled': '在 WebUI「本账号」开启直播数据统计后，即可在群内查询。',
    'stats_bind_sender': '请从自己的群账号发送绑定命令。',
    'stats_bind_uid': '请输入自己的 B站个人空间 UID，例如 {prefix}bpush bind 2。',
    'stats_bound': '已绑定 B站 UID {uid}。用 {prefix}bpush me 查询个人互动。',
    'stats_bind_hint': '可用 {prefix}bpush bind <B站UID> 绑定账号，或在 me 后填入观众 UID 或昵称。',
    'stats_streamer_choose': '请选择本群主播，可填写 UID 或昵称关键词：{choices}',
    'stats_streamer_ambiguous': '关键词匹配了多位本群主播，请用 UID 选择：{choices}',
    'stats_more_streamers': '等 {count} 位',
    'stats_streamer_hint': '请填写本群主播的 UID 或昵称关键词。用 {prefix}bpush up list 查看主播。',
    'stats_cooldown': '本群可在 {seconds} 秒后继续查询直播统计。',
    'stats_pending': '本群统计查询进行中，完成后即可继续。',
    'stats_private_revenue': '本账号已开启营收隐私。可查询弹幕、进场与点赞排行。',
    'stats_empty_room': '直播互动累积后，可在这里查看场次与历史统计。',
    'stats_empty_user': '请填写在此房间有互动记录的观众 UID 或唯一昵称。',
    'stats_empty_rank': '互动记录累积后可查看此排行，也可尝试其他维度或时段。',
    'stats_room_head': '房间统计 · {identity}',
    'stats_user_head': '个人统计 · {viewer}\n直播间 · {identity}',
    'stats_live_scope': '本场（直播中）',
    'stats_pending_scope': '本场（等待续接）',
    'stats_recent_scope': '最近一场',
    'stats_session_scope': '本场 / 最近一场',
    'stats_total_scope': '历史累计',
    'stats_session_duration': '{scope} · 时长 {duration}',
    'stats_total_duration': '历史累计 · {sessions} 场 · 时长 {duration}',
    'stats_title': '标题：{title}',
    'stats_area': '分区：{area}',
    'stats_danmu': '弹幕 {danmu}（文字 {text_danmu} / 表情 {emoticon_danmu}）',
    'stats_interactions': '进房 {entry} 次 / {unique_entry} 人 · 关注 {follow} · 分享 {share} · 点赞 {like}',
    'stats_peaks': '高能峰值 {online_peak} · 看过峰值 {watched_peak}',
    'stats_room_total': '累计弹幕 {danmu} · 场均弹幕 {avg_danmu}',
    'stats_revenue': '付费 {gold}（礼物 {gift_gold} / SC {sc_gold} / 大航海 {guard_gold}）',
    'stats_box_profit': '盲盒盈亏 {profit}',
    'stats_user_activity': '{scope} · 弹幕 {danmu} · 进房 {entry} · 点赞 {like}',
    'stats_user_ranks': '排名：{ranks}',
    'stats_user_rank': '{label} 第 {position} 名',
    'stats_rank_head': '{identity} · {scope} · {label}排行',
    'stats_rank_item': '{index}. {identity} · {value}',
    'stats_rank_session': '本场',
    'stats_rank_total': '总榜',
    'stats_rank_danmu': '弹幕',
    'stats_rank_gift': '礼物',
    'stats_rank_sc': 'SC',
    'stats_rank_box': '盲盒盈亏',
    'stats_rank_entry': '进场',
    'stats_rank_like': '点赞',
    'help_sub': (
        'B站订阅推送 · 订阅与主播管理\n'
        '{prefix}bpush up add <UID> · 添加主播\n'
        '{prefix}bpush up del <UID> · 从本群移除主播\n'
        '{prefix}bpush up list · 查看本群主播\n'
        '{prefix}bpush up live|dynamic|video <UID> on|off · 分主播检测开关\n'
        '{prefix}bpush up sub <UID> · 订阅开播 @ 提醒\n'
        '{prefix}bpush up unsub <UID> · 取消开播订阅\n'
        '{prefix}bpush up subs · 查看我的订阅\n'
        '{prefix}bpush test <UID> · 发送直播测试推送；动态和视频请到 WebUI 测试\n'
        '主播管理与测试权限：群主 / 管理员 / 骰主 / WebUI 白名单。'
    ),
    'help_push': (
        'B站订阅推送 · 群推送与提醒\n'
        '{prefix}bpush push live|dynamic|video on|off · 群推送开关\n'
        '{dynamic_image}'
        '{session_images}'
        '{prefix}bpush atall on|off · 开播 @全体 开关\n'
        '设置权限：群主 / 管理员 / 骰主 / WebUI 白名单。'
    ),
    'help_dynamic_image': '{prefix}bpush push dynamic_img on|off|auto · 图片 / 文字 / 跟随本账号\n',
    'help_push_report': '{prefix}bpush push report on|off|auto · 直播报告：开启 / 关闭 / 跟随本账号\n',
    'help_push_cloud': '{prefix}bpush push cloud on|off|auto · 弹幕词云：开启 / 关闭 / 跟随本账号\n',
    'session_push_on': '本群{label}推送已开启。',
    'session_push_off': '本群{label}推送已关闭。',
    'session_push_auto': '本群{label}推送跟随本账号设置。',
    'dynamic_image_on': '本群动态推送使用图片卡片。',
    'dynamic_image_off': '本群动态推送使用文字模式。',
    'dynamic_image_auto': '本群动态推送跟随本账号设置。',
    'private': '这个功能只在群里用哦~ 把命令发到群里就行。',
    'denied': '需要群主、管理员、骰主或全局白名单权限。',
    'persist': '写入失败，检查目录权限。',
    'error': '处理失败，请稍后重试。',
    'bad_uid': '请输入 B站个人空间 UID，例如 {prefix}bpush up add 2。',
    'up_missing': '请核对主播 UID {uid}。稍后重试，或在 WebUI 配置 Cookie 后再查。',
    'duplicate': '这个主播已经在本群的订阅列表里了~',
    'added': '已添加：{identity}\n本群推送：{switches}\n@全体：{at_all}',
    'at_all_hint': '（{prefix}bpush atall on 可开）',
    'removed': '已从本群移除：UID {uid}\n顺带清理了 {count} 位群友的订阅。',
    'list_empty': '管理员可用 {prefix}bpush up add <UID> 添加本群的第一位主播。',
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
    'subscription_missing': '请先在本群添加主播 UID {uid}，再订阅开播提醒。',
    'subscribed': '订阅成功：UID {uid} 开播时会 @ 你。',
    'unsubscribed': '已取消订阅：UID {uid}',
    'subs_head': '你在本群订阅了 {count} 个主播：',
    'subs_item': '· {identity}',
    'push_toggle': '本群{label}推送已{state}。',
    'atall_on': '本群 @全体 已开启（onebot 每天最多 {limit} 次；{qq}）。',
    'atall_qq_once': 'qqGuild 每次开播只 @ 一次',
    'atall_qq_any': 'qqGuild 每次开播均可 @全体',
    'atall_off': '本群 @全体 已关闭。',
    'atall_not_admin_hint': '将机器人设为本群管理员后，开播推送即可 @全体；其余内容照常发送。',
    'status': 'BiliBiliNotify 运行中\n· 主播 {total} 个 / 本群 {local} 个\n{checks}\n· 今日 @全体：{used}/{limit}',
    'last_check': '· 上次{label}检查：{elapsed}',
    'never': '等待首次检查',
    'seconds_ago': '{count} 秒前',
    'minutes_ago': '{count} 分钟前',
    'test_empty': '请确认主播和接收群已关联，或稍后获取最新内容再试。',
    'test_failed': '测试推送失败，请检查运行日志。',
    'test_prefix': '[测试] ',
    'risk_warning': 'B站风控，请在 WebUI 填 Cookie。',
}

OP = {
    'start': '{at_all}【B站开播】{name} 开播啦！\n标题：{title}\n分区：{area}\n时间：{time}\n{image}{link}{subscribers}',
    'area': '【B站换分区】{name} 切换了分区\n标题：{title}\n新分区：{area}\n{image}{link}',
    'end': '【B站下播】{name} 下播了\n标题：{title}\n下播分区：{area}',
    'dynamic': '【B站动态】{name} 发布了新动态\n时间：{time}\n{body}\n{image}{link}',
    'video': '【B站投稿】{name} 发布了新视频\n标题：{title}\n时间：{time}\n{image}{link}',
}

MARKDOWN = {
    'start': ('**B站开播** · {name}\n{image}\n**标题**：{title}\n**分区**：{area}\n'
              '**时间**：{time}\n**链接**：{link}\n{at_all}{subscribers}'),
    'area': '**B站换分区** · {name}\n{image}\n**标题**：{title}\n**新分区**：{area}\n**链接**：{link}',
    'end': '**B站下播** · {name}\n\n**标题**：{title}\n**下播分区**：{area}',
    'dynamic': '**B站动态** · {name}\n**时间**：{time}\n{image}\n{body}\n**链接**：{link}',
    'video': '**B站投稿** · {name}\n**标题**：{title}\n**时间**：{time}\n{image}\n**链接**：{link}',
}

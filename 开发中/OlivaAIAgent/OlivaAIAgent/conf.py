# -*- encoding: utf-8 -*-
'''
OlivaAIAgent 配置管理
配置文件: plugin/data/OlivaAIAgent/config.json (UTF-8 无 BOM)
群级开关: plugin/data/OlivaAIAgent/groups.json
'''

import copy
import json
import os
import threading
import time

dataPath = 'plugin/data/OlivaAIAgent'
tmpPath = 'plugin/tmp/OlivaAIAgent'
CONFIG_PATH = dataPath + '/config.json'
GROUPS_PATH = dataPath + '/groups.json'
LOG_DIR = dataPath + '/logs'

_lock = threading.RLock()

gConf = {}
gGroups = {}
gProc = None
gPluginName = 'OlivaAIAgent'

# 热重载状态
_config_mtime = 0.0
_groups_mtime = 0.0
_last_hotcheck = 0.0
_HOTCHECK_INTERVAL = 2.0  # 最多每 2 秒检查一次文件变化

DICE_CHEATSHEET = (
    '.r 骰点(.r3d6+1) | .rh 暗骰 | .ra/.rc 技能检定 | .rav 对抗检定 | .sc 理智检定 | .en 成长检定 | '
    '.st 人物卡录入(.st show查看) | .stex 切换卡模板 | .coc 车卡 | .dnd DND车卡 | .nn 命名 | .pc 人物卡管理 | '
    '.set 设置默认骰 | .setcoc 房规 | .draw 抽牌 | .init 先攻(.init clr清空) | .ti/.li 疯狂症状 | '
    '.ob 旁观 | .sn 跑团名片 | .welcome 欢迎词 | .team 小队 | .help 帮助 | .bot 骰子开关 | '
    '.dismiss 退群 | .log 跑团日志(Logger) | .story 剧情(StoryCore) | .jrrp 今日人品(Joy) | .hiy 骰点统计'
)

DEFAULT_SYSTEM_PROMPT = (
    '你是接入 OlivOS(青果) 骰系机器人的 AI 助手，运行在 TRPG 跑团聊天环境中。\n'
    '你可以通过 olivos_discover 和 olivos_call 调用 OlivOS 的插件接口、进程接口和底层 SDK，'
    '并可以通过 run_command 工具以当前用户身份执行 OlivaDice 官方骰点指令。\n'
    '行为准则：\n'
    '1. 任何正式的骰点、检定、录卡、抽牌等操作，一律用 run_command 执行真实指令，绝不自己编造骰点结果。\n'
    '2. 高危操作（踢人/禁言/撤回/退群/设管理等）若无权限，工具会返回错误，向用户礼貌说明即可；执行前应确认意图明确。\n'
    '3. 回复要精炼、口语化，适合 QQ 群聊阅读；除非用户要求，不要长篇大论。\n'
    '4. 你可以用 memory_save 记录用户或群的重要信息（人物卡背景、剧情进度、约定等），需要时用 memory_list 查看。\n'
    '5. 需要实时信息时用 web_search / fetch_url 联网查询。\n'
    '6. 所有 OlivOS 原生操作都先用 olivos_discover 检索初始化后的内存目录，再把返回路径交给 '
    'olivos_call；优先 inde，其次 event/proc，最后 sdk，绝不使用旧的手写工具名或猜接口名。\n'
)

DEFAULT_CONF = {
    '_说明': '完整说明见插件目录 README.md；修改后发 .ai reload 或在托盘菜单点击重载配置生效',
    'backend': 'openai',
    'openai': {
        'api_url': 'https://api.deepseek.com/v1/chat/completions',
        'api_key': '',
        'model': 'deepseek-v4-flash',
        '_model说明': 'DeepSeek: deepseek-v4-flash(快/便宜) 或 deepseek-v4-pro(更强)。旧名 deepseek-chat/'
                    'deepseek-reasoner 已于 2026-07-24 弃用。思考模式用下方 thinking:{"type":"enabled"} 开',
        'stream': False,
        'temperature': 0.7,
        'max_tokens': 2000,
        'vision': False,
        'timeout_sec': 120,
        'thinking': {'type': 'disabled'},
        'reasoning_effort': 'high',
        'extra_headers': {},
        'extra_body': {},
    },
    'anthropic': {
        'api_url': 'https://api.anthropic.com/v1/messages',
        'api_key': '',
        'model': 'claude-sonnet-4-20250514',
        'stream': False,
        'temperature': 0.7,
        'max_tokens': 2000,
        'vision': True,
        'timeout_sec': 120,
        'anthropic_version': '2023-06-01',
        'extra_headers': {},
        'extra_body': {},
    },
    'custom': {
        '_说明': 'wire 可选 openai / anthropic，决定请求报文格式，其余字段同对应后端',
        'wire': 'openai',
        'api_url': '',
        'api_key': '',
        'model': '',
        'stream': False,
        'temperature': 0.7,
        'max_tokens': 2000,
        'vision': False,
        'timeout_sec': 120,
        'thinking': {'type': 'disabled'},
        'reasoning_effort': 'high',
        'extra_headers': {},
        'extra_body': {},
    },
    'trigger': {
        'prefix': ['.ai', '。ai', '/ai'],
        'at_trigger': True,
        'keywords': [],
        '_keywords说明': '统一触发关键词：填这一处即可，潜行开/关都用它触发，命中就强制回复。如 ["骰娘","先攻"]',
        'private_chat': True,
        '_private_chat说明': '私聊/单聊总开关：false=私聊完全不可用；true=私聊可用(默认仅骰主，见 private_master_only)',
        'private_master_only': True,
        '_private_master_only说明': 'true(默认)=私聊只有骰主能用；false=私聊所有人可用(仍受 private_chat 总开关)',
        'ignore_command_regex': '^[.。/].+',
    },
    'groupchain': {
        '_说明': '群链/主账号：读取 OlivaDiceCore 的主从账号关系，把从账号的数据(记忆/知识/侧写/群总结)写入主账号，'
               '使链接的多个bot共享同一份数据。enable=false 则各bot数据独立',
        'enable': True,
    },
    'whitelist': {
        'enabled': False,
        'groups': [],
    },
    'permissions': {
        '_说明': '高危接口管控：全局开关 / 群开关(groups.json) / 角色门槛。均可由骰主用 .ai admin 指令调整。'
               '旧式 admin_tools_master_only 布尔已弃用(默认配置不再保留)，老 config.json 里的 true 仍会被'
               '_migrate 自动迁移为 admin_tools_min_role=master，不会降权',
        'admin_tools_global': True,
        'admin_tools_min_role': 'everyone',
        '_min_role说明': 'everyone=所有人 / group_admin=群管理+群主+骰主 / master=仅骰主。'
                       'OlivaDice官方指令(run_command)另由骰系自身权限判定，不受此项影响',
    },
    'masters': {
        'from_olivadice': True,
        'extra': [],
    },
    'prompt': {
        'system': DEFAULT_SYSTEM_PROMPT,
        'group_persona': {},
        'dice_cheatsheet': DICE_CHEATSHEET,
        'append': '',
    },
    'memory': {
        'max_rounds': 16,
        'user_memory_limit': 40,
        'group_memory_limit': 40,
        'context_buffer': 20,
        'inject_group_buffer': True,
    },
    'search': {
        'enabled': True,
        'tavily_api_url': 'https://api.tavily.com/search',
        'tavily_api_key': '',
        'max_results': 5,
        'fetch_url_max_chars': 5000,
    },
    'ambient': {
        '_说明': '潜行模式：伪装群友、读全部群消息、择机自行插话（默认关闭，用 .ai stealth on 按群开启）',
        'enable_default': False,
        'enabled_groups': [],
        'personality': (
            '你是一个潜伏在群里的群友，冷静温和、理性、不爱花哨表达；有边界感，非必要不回复，'
            '讨厌无意义复读，没话聊时不尬聊，不感兴趣的话题不参与；被找时会回应。别让人发现你是AI。'),
        'mention_reply': True,
        'reply_probability': 1.0,
        'ignore_prefixes': ['.', '。', '/', '!', '！'],
        'integrate_hard_trigger': True,
        '_integrate说明': '被@或命中关键词时，把潜行与全权限Agent整合成同一次请求：'
                       '既有潜行的人设/群上下文/知识，又能调用全部接口和骰点，出一条回复(不再二选一)',
        'history_size': 8,
        'history_size_min': 4,
        'history_dynamic': False,
        'history_dynamic_size': 16,
        'prompt_cache_optimized': True,
        'prompt_cache_history_size': 32,
        'slack_time': 5,
        'slack_cooldown_time': 30,
        'max_message_length': 2048,
        'retry_count': 3,
        'first_thinking': False,
        'first_thinking_cooldown': 60,
        'intent_api': {
            '_说明': '前置二分类判定用的便宜模型；enable=false 时复用主后端',
            'enable': False,
            'api_url': 'https://api.siliconflow.cn/v1/chat/completions',
            'api_key': '',
            'model': 'Qwen/Qwen2.5-7B-Instruct',
            'max_tokens': 32,
            'temperature': 0.0,
            'timeout': 45,
        },
        'intent_image_cache_size': 10,
        'record_memory': True,
        'record_knowledge': True,
        'search_ageing': 900,
        'search_knowledge_deepin': 1,
        'allow_tools': False,
        'agent_max_turns': 4,
        'max_send_delay': 6.0,
        '_max_send_delay说明': '单条消息拟人打字延迟上限(秒)，防止超长回复长时间占住群锁拖住该群后续回复',
    },
    'vision': {
        '_说明': '图片视觉识别：把群里的图/表情转成文字摘要供AI理解，并可主动发表情包',
        'enable': False,
        'use_main': 'auto',
        '_use_main说明': 'auto(默认)=主后端支持视觉(其 vision:true)就直接用主模型识图，不支持就用下面单独配的 OCR 模型；'
                      '也可显式写 true(强制用主) / false(强制用下面独立模型)',
        'api_url': 'https://api.siliconflow.cn/v1/chat/completions',
        'api_key': '',
        'model': 'Pro/moonshotai/Kimi-K2-Instruct',
        'mode': 'base64',
        'queue_size': 8,
        'persist_cache_max': 300,
        'sync_ocr': False,
        '_sync_ocr说明': 'false=整条图片消息转入后台，先识图再生成本轮回复，不阻塞消息总线；'
                       'true=直接在消息总线线程识图，可能卡住其他事件',
    },
    'knowledge': {
        '_说明': '知识库：静态知识放 data/OlivaAIAgent/Knowledge/*.json；动态知识由AI自动记录',
        'cache_max': 0,
    },
    'reminder': {
        '_说明': '定时提醒/定时主动消息：AI 可用 schedule_reminder 工具设定；到点主动推送(非被动回复，官机不超时)',
        'enable': True,
        'max_per_user': 20,          # 每人每 bot 最多挂起的提醒数
        'max_total': 500,            # 全局最多挂起的提醒数
        'max_horizon_days': 30,      # 最远可预约的天数
        'grace_seconds': 5,          # 逾期任务(如重启后)延后触发的缓冲秒数
        'no_sender_retry_seconds': 20,   # 到点时暂无可用发送器的重试间隔
        'no_sender_max_retry': 60,       # 无发送器时最多重试次数
    },
    'skills': {
        '_说明': '技能库：把 SKILL.md 规则书片段按需注入。装了 rank_bm25+jieba 用BM25，否则纯Python降级',
        'enable': True,
        'max_chars': 2000,
        'max_matches': 2,
        'match_rate': 0.12,
        'extra_dirs': [],
        '_翻译说明': '外文提问→中文，帮外语群友命中中文技能库(英文技能库靠 frontmatter 关键词+模型直读，无需翻译)。'
                  '需装 translators 库才生效，未装自动跳过不报错；仅翻译不含中文的提问，中文提问永不翻译',
        'translate_foreign_query': True,
        'translate_to': 'zh',
        'translate_from': 'auto',
        'translate_backend': 'bing',
        'translate_timeout': 2.0,
        '_外文技能说明': '纯外文技能(元数据无中文)自动桥接：索引期把 技能名/描述/关键词/章节标题 翻成中文并按内容哈希'
                    '永久缓存(skills_translation_cache.json)，中文提问即可命中。渠道：translators 优先(免费)，'
                    '缺失则用已配置 AI 后端一次性小请求(translate_meta_use_llm)；都没有则退化为手动 frontmatter '
                    '中文关键词 + 保底注入技能开头片段。translate_query_to_foreign=装了 translators 时把中文提问'
                    '顺带翻成英文一并检索，直接命中英文正文',
        'translate_skill_meta': True,
        'translate_meta_use_llm': True,
        'translate_meta_llm_timeout': 30.0,
        'translate_meta_max_per_build': 30,
        'translate_query_to_foreign': True,
        'translate_query_to': 'en',
    },
    'agent': {
        'max_tool_rounds': 8,
        'tool_result_max_chars': 3500,
        'max_concurrent': 4,
        'run_command_exclude': ['OlivaAIAgent'],
        'busy_reply': '上一条还在思考中，稍等一下嗷~',
        'error_reply': 'AI 出错了：{err}',
    },
    'reply': {
        'quote_reply': True,
        'split_length': 1500,
        'max_split_count': 3,
    },
    'enable': {
        'global': True,
        'group_default': True,
    },
    'debug_log': True,
}


def _deep_merge(base, new):
    '''以 base 为模板补全 new 缺失的键，返回合并结果（new 优先）'''
    if not isinstance(base, dict) or not isinstance(new, dict):
        return new if new is not None else base
    res = {}
    for k in base:
        if k in new:
            res[k] = _deep_merge(base[k], new[k])
        else:
            res[k] = copy.deepcopy(base[k])
    for k in new:
        if k not in res:
            res[k] = new[k]
    return res


def releaseDir(path):
    try:
        if not os.path.exists(path):
            os.makedirs(path, exist_ok=True)
    except Exception:
        pass


def atomicDump(data, path):
    '''原子写 JSON：先写同目录临时文件再 os.replace，避免进程中途被杀/并发写导致文件被截断损坏。'''
    d = os.path.dirname(path)
    if d:
        try:
            os.makedirs(d, exist_ok=True)
        except Exception:
            pass
    tmp = '%s.tmp.%d' % (path, os.getpid())
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
        f.flush()
        try:
            os.fsync(f.fileno())
        except Exception:
            pass
    os.replace(tmp, path)


def initDataPath():
    for p in [dataPath, tmpPath, LOG_DIR, dataPath + '/sessions', dataPath + '/memory']:
        releaseDir(p)


def _mtime(path):
    try:
        return os.path.getmtime(path)
    except Exception:
        return 0.0


def _migrate(cfg):
    '''向后兼容迁移：旧配置 admin_tools_master_only=True 且未设 min_role → 门槛设为 master。'''
    try:
        perm = cfg.get('permissions', {})
        if perm.get('admin_tools_master_only') is True and perm.get('admin_tools_min_role', 'everyone') == 'everyone':
            perm['admin_tools_min_role'] = 'master'
    except Exception:
        pass


def load():
    global gConf, gGroups, _config_mtime, _groups_mtime
    with _lock:
        initDataPath()
        conf_data = {}
        parse_failed = False
        if os.path.exists(CONFIG_PATH):
            try:
                with open(CONFIG_PATH, 'r', encoding='utf-8-sig') as f:
                    conf_data = json.load(f)
                if not isinstance(conf_data, dict):
                    conf_data = {}
                    parse_failed = True
            except Exception:
                # 解析失败：绝不用默认配置覆写用户文件（否则 API Key 等全丢），
                # 先备份坏文件，保留原文件不动，本次用默认值在内存里跑
                conf_data = {}
                parse_failed = True
                try:
                    import shutil
                    shutil.copy(CONFIG_PATH, CONFIG_PATH + '.bad')
                except Exception:
                    pass
        merged = _deep_merge(DEFAULT_CONF, conf_data)
        _migrate(merged)
        gConf = merged
        # 仅在解析成功时回写（补全新默认键）；解析失败时不动磁盘上的用户文件
        if not parse_failed:
            try:
                atomicDump(gConf, CONFIG_PATH)
            except Exception:
                pass
        _config_mtime = _mtime(CONFIG_PATH)
        try:
            if os.path.exists(GROUPS_PATH):
                with open(GROUPS_PATH, 'r', encoding='utf-8') as f:
                    gGroups = json.load(f)
            else:
                gGroups = {}
        except Exception:
            gGroups = {}
        _groups_mtime = _mtime(GROUPS_PATH)
    return gConf


def save():
    global _config_mtime
    with _lock:
        initDataPath()
        try:
            atomicDump(gConf, CONFIG_PATH)
        except Exception:
            pass
        _config_mtime = _mtime(CONFIG_PATH)
        saveGroups()


def saveGroups():
    global _groups_mtime
    with _lock:
        try:
            atomicDump(gGroups, GROUPS_PATH)
        except Exception:
            pass
        _groups_mtime = _mtime(GROUPS_PATH)


def hotReload():
    '''按文件 mtime 检测外部修改并自动载入内存（配置/群开关/知识/记忆）。节流后可高频调用。'''
    global gConf, gGroups, _config_mtime, _groups_mtime, _last_hotcheck
    now = time.time()
    with _lock:
        if now - _last_hotcheck < _HOTCHECK_INTERVAL:
            return
        _last_hotcheck = now
    changed = []
    # config.json —— 只读合并，不回写，避免与用户编辑相互冲刷
    try:
        m = _mtime(CONFIG_PATH)
        if m > _config_mtime and os.path.exists(CONFIG_PATH):
            with open(CONFIG_PATH, 'r', encoding='utf-8-sig') as f:
                data = json.load(f)
            if isinstance(data, dict):
                merged = _deep_merge(DEFAULT_CONF, data)
                _migrate(merged)   # 与 load() 一致，避免旧式 master_only 配置热载后权限降级
                with _lock:
                    gConf = merged
                    _config_mtime = m
                changed.append('config')
    except Exception:
        pass
    # groups.json
    try:
        m = _mtime(GROUPS_PATH)
        if m > _groups_mtime and os.path.exists(GROUPS_PATH):
            with open(GROUPS_PATH, 'r', encoding='utf-8') as f:
                data = json.load(f)
            with _lock:
                gGroups = data if isinstance(data, dict) else {}
                _groups_mtime = m
            changed.append('groups')
    except Exception:
        pass
    # 知识库 / 记忆（潜行群记忆、侧写、知识）— 委托各模块自检
    try:
        import OlivaAIAgent
        k = OlivaAIAgent.knowledge.hotReload()
        if k:
            changed.extend(k)
        mm = OlivaAIAgent.memory.hotReload()
        if mm:
            changed.extend(mm)
    except Exception:
        pass
    if changed:
        log(gProc, 2, '热重载: %s' % ', '.join(changed))


def get(*keys, default=None):
    node = gConf
    for k in keys:
        if isinstance(node, dict) and k in node:
            node = node[k]
        else:
            return default
    return node


def setConf(value, *keys):
    with _lock:
        node = gConf
        for k in keys[:-1]:
            node = node.setdefault(k, {})
        node[keys[-1]] = value


def _groupNode(platform, group_id, create=False):
    p = str(platform)
    g = str(group_id)
    if create:
        return gGroups.setdefault(p, {}).setdefault(g, {})
    return gGroups.get(p, {}).get(g, {})


def getGroupSwitch(platform, group_id, key, default=None):
    with _lock:
        node = _groupNode(platform, group_id)
        if key in node:
            return node[key]
        return default


def setGroupSwitch(platform, group_id, key, value):
    with _lock:
        node = _groupNode(platform, group_id, create=True)
        node[key] = value
        saveGroups()


def isGroupEnabled(platform, group_id):
    return bool(getGroupSwitch(platform, group_id, 'enabled', get('enable', 'group_default', default=True)))


def isGroupAdminTools(platform, group_id):
    return bool(getGroupSwitch(platform, group_id, 'admin_tools', True))


def isWhitelisted(platform, group_id):
    if not get('whitelist', 'enabled', default=False):
        return True
    groups = get('whitelist', 'groups', default=[]) or []
    return str(group_id) in [str(x) for x in groups]


_PLATFORM_NOTES = {
    'qq': 'QQ平台(OneBot类)。支持@[CQ:at,qq=号]、图片[CQ:image]、回复[CQ:reply,id=]、表情回应、群管理、群文件、戳一戳等。',
    'telegram': 'Telegram。无QQ式群管理/精华/戳一戳；@用用户名；发送以文本/图片为主，勿用CQ码专属特性。',
    'discord': 'Discord。用频道概念，无QQ群管理接口；勿用CQ码。',
    'kaiheila': 'KOOK(开黑啦)。有频道(host)层级，部分接口用 host_id；勿套用QQ专属能力。',
    'kook': 'KOOK(开黑啦)。有频道(host)层级，部分接口用 host_id；勿套用QQ专属能力。',
    'qqguild': 'QQ频道。子频道结构，@与消息格式与QQ群略有差异，部分群管理接口不可用。',
    'dodo': 'DoDo。频道结构，勿套用QQ群专属接口。',
    'fanbook': 'Fanbook。勿套用QQ群专属接口。',
    'onebot': 'OneBot协议(通常为QQ)。CQ/OP码可用。',
}


def loadedPlugins(Proc, limit=50):
    '''返回已加载插件的展示串列表 ["namespace(名称)", ...]，供提示 AI 可调用范围。'''
    out = []
    try:
        for ns in Proc.get_plugin_list():
            info = Proc.plugin_models_dict.get(ns, {}) if hasattr(Proc, 'plugin_models_dict') else {}
            name = info.get('name', '') if isinstance(info, dict) else ''
            if name and name != ns:
                out.append('%s(%s)' % (ns, name))
            else:
                out.append(str(ns))
            if len(out) >= limit:
                break
    except Exception:
        pass
    return out


def platformBrief(plugin_event):
    '''返回给 AI 的 platform/sdk 说明；OlivOS 会按事件平台自动路由到对应适配器，AI 只需产出该平台合适的内容。'''
    try:
        pf = plugin_event.platform.get('platform', '')
        sdk = plugin_event.platform.get('sdk', '')
        model = plugin_event.platform.get('model', '')
    except Exception:
        pf, sdk, model = '', '', ''
    note = _PLATFORM_NOTES.get(str(pf).lower(), '')
    if not note:
        for k, v in _PLATFORM_NOTES.items():
            if k in str(sdk).lower():
                note = v
                break
    lines = ['平台: %s | SDK: %s%s' % (pf or '未知', sdk or '未知', (' | 模型: %s' % model) if model else '')]
    lines.append('说明: 你运行在上述平台。发送接口由框架按平台自动路由(你无需关心底层SDK)，'
                 '但要产出该平台合适的内容——不要在不支持的平台使用其专属格式或接口。')
    lines.append('接口调用: 所有 OlivOS 原生操作都先用 olivos_discover 查内存中的 Event/Proc/indeAPI/SDK 真实签名，'
                 '再用 olivos_call 调用；不存在 send_msg 等手写原生工具，不得猜测路径。')
    lines.append('发送选择: 普通聊天直接使用最终回复；用户明确需要 Markdown、键盘、主动发送等协议能力时，'
                 '可发现并调用对应接口。create/send 类接口调用成功即已直接发送，不要再用普通回复重复同一内容；'
                 '如有必要只做简短确认。')
    if note:
        lines.append('平台特性: ' + note)
    return '\n'.join(lines)


def isAmbientEnabled(platform, group_id):
    '''潜行模式本群是否开启：群开关优先，否则看 enable_default / enabled_groups。'''
    sw = getGroupSwitch(platform, group_id, 'ambient', None)
    if sw is not None:
        return bool(sw)
    groups = [str(x) for x in (get('ambient', 'enabled_groups', default=[]) or [])]
    if str(group_id) in groups or 'all' in groups:
        return True
    return bool(get('ambient', 'enable_default', default=False))


def dataBotHash(bot_hash):
    '''群链：把从账号 bot_hash 解析为【主账号】hash，用作数据存储键，使链接的多bot共享数据(记忆/知识/侧写等)。
    读取 OlivaDiceCore 的主从账号关系(与骰系一致)；无链/骰系不可用/开关关闭 → 返回原 hash。'''
    bh = str(bot_hash) if bot_hash is not None else 'unity'
    if not get('groupchain', 'enable', default=True):
        return bh
    try:
        import OlivaDiceCore
        try:
            red = OlivaDiceCore.userConfig.getRedirectedBotHash(bh)   # 与骰系同款重定向
            if red:
                return str(red)
        except Exception:
            lst = OlivaDiceCore.console.getMasterBotHashList(bh)
            if lst:
                return str(lst[0])
    except Exception:
        pass
    return bh


def _rawBotHash(plugin_event):
    try:
        return plugin_event.bot_info.hash if plugin_event.bot_info is not None else 'unity'
    except Exception:
        return 'unity'


def _botHashChain(plugin_event):
    '''本bot原始hash + 群链主账号hash(去重)，用于骰主判定跨链生效。'''
    raw = str(_rawBotHash(plugin_event))
    return list(dict.fromkeys([raw, dataBotHash(raw)]))


def getMasters(plugin_event):
    '''获取骰主列表(字符串id列表)：OlivaDiceCore masterList(含群链主账号) + 配置 extra'''
    res = []
    if get('masters', 'from_olivadice', default=True):
        try:
            import OlivaDiceCore
            for bot_hash in _botHashChain(plugin_event):   # 从账号也认主账号上登记的骰主
                master_list = OlivaDiceCore.console.getConsoleSwitchByHash('masterList', bot_hash)
                if isinstance(master_list, list):
                    for item in master_list:
                        if isinstance(item, (list, tuple)) and len(item) >= 1:
                            res.append(str(item[0]))
                        elif isinstance(item, (int, str)):
                            res.append(str(item))
        except Exception:
            pass
    for item in get('masters', 'extra', default=[]) or []:
        res.append(str(item))
    return list(dict.fromkeys(res))


def isMaster(plugin_event):
    '''判断事件发送者是否为骰主(群链下：主账号上登记的骰主在从账号也认)'''
    try:
        user_id = str(plugin_event.data.user_id)
    except Exception:
        return False
    # 优先用 OlivaDiceCore 官方判定（带 userHash 与平台隔离）
    if get('masters', 'from_olivadice', default=True):
        try:
            import OlivaDiceCore
            user_hash = OlivaDiceCore.userConfig.getUserHash(
                plugin_event.data.user_id, 'user', plugin_event.platform['platform']
            )
            for bot_hash in _botHashChain(plugin_event):
                if OlivaDiceCore.ordinaryInviteManager.isInMasterList(bot_hash, user_hash):
                    return True
        except Exception:
            pass
    return user_id in getMasters(plugin_event)


def log(Proc, level, msg):
    try:
        if Proc is not None:
            Proc.log(level, '[OlivaAIAgent] ' + str(msg))
    except Exception:
        pass


def debugLog(Proc, msg):
    if get('debug_log', default=False):
        # 用 INFO(2) 而非 DEBUG(0)：OlivOS 默认日志窗口只显示 INFO 及以上，
        # 用 level=0 会导致 debug_log=true 也看不到任何输出
        log(Proc, 2, msg)


def _traceValue(key, value):
    '''清洗过程日志字段，避免密钥、Base64 和超长内容进入 Logger。'''
    key_low = str(key).lower()
    if any(word in key_low for word in ('api_key', 'token', 'password', 'authorization', 'secret')):
        return '<redacted>'
    if isinstance(value, bytes):
        return '<bytes:%d>' % len(value)
    if isinstance(value, (list, tuple, set)):
        return '<%s:%d>' % (type(value).__name__, len(value))
    if isinstance(value, dict):
        return '<dict:%d keys>' % len(value)
    text = str(value).replace('\r', ' ').replace('\n', ' ')
    if text.startswith('data:image'):
        return '<image-data-url:%d chars>' % len(text)
    if len(text) > 180:
        text = text[:180] + '...'
    return text


def traceLog(Proc, stage, trace_id=None, **fields):
    '''统一过程日志；仅 debug_log=true 时输出，格式便于按 trace_id 串起一条消息。'''
    if not get('debug_log', default=False):
        return
    parts = ['TRACE', str(stage)]
    if trace_id not in [None, '']:
        parts.append('id=%s' % _traceValue('trace_id', trace_id))
    for key in sorted(fields):
        parts.append('%s=%s' % (key, _traceValue(key, fields[key])))
    log(Proc, 2, ' | '.join(parts))

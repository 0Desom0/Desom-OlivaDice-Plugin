"""
OlivaAIAgent 统一配置 GUI。

配置表单由 DEFAULT_CONF 和当前配置动态生成，避免新增功能后 GUI 漏项。
GUI 只负责编辑配置与触发维护操作，不承载消息处理业务。
"""

import copy
import json
import os
import threading
import tkinter
from tkinter import messagebox, scrolledtext, ttk

import OlivaAIAgent

SECTION_ORDER = [
    'general',
    'openai',
    'anthropic',
    'custom',
    'prompt',
    'trigger',
    'ambient',
    'memory',
    'semantic_memory',
    'vision',
    'media',
    'forward',
    'voice',
    'search',
    'mcp',
    'permissions',
    'security',
    'olivadice_logger',
    'masters',
    'groupchain',
    'reminder',
    'knowledge',
    'skills',
    'agent',
    'reply',
    'message_registry',
]

SECTION_LABELS = {
    'general': '常规与后端',
    'openai': 'OpenAI / 千问兼容',
    'anthropic': 'Anthropic',
    'custom': '自定义网关',
    'prompt': '统一提示词',
    'trigger': '触发与私聊',
    'ambient': '潜行群友',
    'memory': '上下文与群记忆',
    'semantic_memory': '长期事实与向量',
    'vision': '图片视觉',
    'media': '入站语音与视频',
    'forward': '合并转发',
    'voice': '语音模型',
    'search': '联网搜索',
    'mcp': 'MCP 服务',
    'permissions': '工具权限',
    'security': '内容与人设安全',
    'olivadice_logger': 'OlivaDice 团日志',
    'masters': '骰主与专属称呼',
    'groupchain': '群链共享',
    'reminder': '定时提醒',
    'knowledge': '知识库',
    'skills': '技能库',
    'agent': 'Agent 与工具循环',
    'reply': '回复输出',
    'message_registry': '消息与引用索引',
}

FIELD_LABELS = {
    'backend': '当前后端',
    'debug_log': '详细调试日志',
    'api_url': '接口地址',
    'api_key': 'API Key',
    'model': '模型名称',
    'stream': '流式响应',
    'temperature': '温度',
    'max_tokens': '最大输出 Token',
    'vision': '主模型支持视觉',
    'audio': '主模型支持音频',
    'video': '主模型支持视频',
    'image': '识别转发内图片',
    'timeout_sec': '请求超时（秒）',
    'thinking': '思考模式',
    'type': '类型',
    'reasoning_effort': '推理强度',
    'extra_headers': '附加请求头（JSON）',
    'extra_body': '附加请求体（JSON）',
    'anthropic_version': 'Anthropic 版本',
    'wire': '报文格式',
    'system': '系统提示词与人设',
    'group_persona': '分群人设（JSON）',
    'dice_cheatsheet': '骰系指令速查',
    'prefix': '触发前缀',
    'at_trigger': '被 @ 时触发',
    'keywords': '统一触发关键词',
    'private_chat': '启用私聊',
    'private_master_only': '私聊仅骰主',
    'ignore_command_regex': '忽略指令正则',
    'global': '插件全局启用',
    'group_default': '新群默认启用',
    'enable_default': '新群潜行默认启用',
    'reply_probability': '主动插话概率',
    'ignore_prefixes': '潜行忽略前缀',
    'integrate_hard_trigger': '定向触发整合全部能力',
    'history_size': '潜行历史条数',
    'history_size_min': '最少群历史条数',
    'history_dynamic': '动态历史窗口',
    'history_dynamic_size': '动态窗口上限',
    'prompt_cache_optimized': '提示词缓存优化',
    'prompt_cache_history_size': '潜行缓存上限条数',
    'slack_time': '等候连续消息（秒）',
    'slack_cooldown_time': '潜行冷却（秒）',
    'max_message_length': '单条消息长度上限',
    'retry_count': '生成重试次数',
    'first_thinking': '启用前置参与判定',
    'intent_api': '辅助模型（判定/路由/提炼）',
    'timeout': '超时（秒）',
    'intent_image_cache_size': '判定图片缓存数',
    'record_memory': '记录群友侧写',
    'record_knowledge': '记录动态知识',
    'search_ageing': '知识检索有效期（秒）',
    'search_knowledge_deepin': '知识检索深度',
    'allow_tools': '潜行允许工具调用',
    'agent_max_turns': '潜行工具最大轮数',
    'max_send_delay': '拟人发送延迟上限（秒）',
    'max_rounds': '会话历史轮数',
    'prompt_cache_max_rounds': '会话缓存上限轮数',
    'user_memory_limit': '用户记忆上限',
    'group_memory_limit': '群记忆上限',
    'context_buffer': '上下文缓冲条数',
    'inject_group_buffer': '注入近期群消息',
    'history_summary_default': '新群滚动摘要默认开启',
    'long_term_default': '新群长期事实默认开启',
    'extraction_batch_size': '事实提炼批量',
    'embedding_api_url': 'Embedding 接口地址',
    'embedding_api_key': 'Embedding API Key',
    'embedding_model': 'Embedding 模型',
    'embedding_timeout_sec': 'Embedding 超时（秒）',
    'embedding_extra_headers': 'Embedding 请求头（JSON）',
    'failure_backoff_sec': '失败退避（秒）',
    'request_batch_size': 'Embedding 批量',
    'cache_size': '向量缓存数',
    'top_k': '检索返回条数',
    'min_score': '最低相似度',
    'max_scope_facts': '单范围事实总量',
    'use_main': '视觉模型路由',
    'mode': '图片传输模式',
    'queue_size': '识图队列上限',
    'persist_cache_max': '识图持久缓存数',
    'sync_ocr': '同步识图',
    'sync_media': '同步媒体识别',
    'main_mode': '主模型传输模式',
    'max_bytes': '媒体大小上限（字节）',
    'enabled': '启用',
    'tavily_api_url': 'Tavily 地址',
    'tavily_api_key': 'Tavily API Key',
    'max_results': '搜索结果上限',
    'fetch_url_max_chars': '网页正文字符上限',
    'fetch_url_max_bytes': '网页下载字节上限',
    'allow_private_network': '允许访问本机与内网',
    'admin_tools_global': '高危工具全局启用',
    'admin_tools_min_role': '高危工具最低角色',
    'persona_lock': '锁定机器人固定人设',
    'block_persona_memory': '阻止人设注入长期数据',
    'politics_guard': '拒绝现实政治话题',
    'politics_reply': '话题拦截回复',
    'use_olivadice_censor': '跟随 OlivaDiceCore 敏感词',
    'external_sensitive_words': '启用本地选装词库',
    'sensitive_word_files': '本地词库文件（JSON）',
    'sensitive_word_dirs': '本地词库目录（JSON）',
    'from_olivadice': '读取 OlivaDiceCore 骰主',
    'extra': '额外骰主 ID',
    'default_title': '未单独设置时的骰主称呼',
    'titles': '骰主专属称呼（JSON）',
    'groups': '群 ID 列表',
    'max_per_user': '每人提醒上限',
    'max_total': '全局提醒上限',
    'max_horizon_days': '最远预约天数',
    'grace_seconds': '逾期补发缓冲（秒）',
    'no_sender_retry_seconds': '无发送器重试间隔（秒）',
    'no_sender_max_retry': '无发送器最大重试',
    'cache_max': '缓存上限',
    'max_chars': '技能注入字符上限',
    'max_matches': '技能命中上限',
    'match_rate': '技能最低匹配率',
    'extra_dirs': '额外技能目录',
    'translate_foreign_query': '外文问题翻译为中文',
    'translate_to': '问题翻译目标语言',
    'translate_from': '问题来源语言',
    'translate_backend': '翻译服务',
    'translate_timeout': '翻译超时（秒）',
    'translate_skill_meta': '翻译外文技能元数据',
    'translate_meta_use_llm': '允许辅助模型翻译元数据',
    'translate_meta_llm_timeout': '元数据模型超时（秒）',
    'translate_meta_max_per_build': '单次最多翻译技能数',
    'translate_query_to_foreign': '中文问题同时翻译为外文检索',
    'translate_query_to': '外文检索目标语言',
    'max_tool_rounds': '工具调用最大轮数',
    'max_auto_continuations': '未完成任务自动续行次数',
    'tool_result_max_chars': '工具结果字符上限',
    'max_concurrent': '并发对话数',
    'run_command_exclude': '指令重注入排除插件',
    'busy_reply': '忙时回复',
    'error_reply': '错误回复',
    'quote_reply': '引用原消息回复',
    'split_length': '长回复分段长度',
    'max_split_count': '最大分段数',
    'retention_days': '消息索引保留天数',
    'max_records': '消息索引最大记录数',
    'content_max_chars': '单条正文保存上限',
    'storage_max_chars': '转发正文本地保存上限',
    'connect_on_start': '启动时连接',
    'protocol_version': 'MCP 协议版本',
    'refresh_interval_sec': '工具目录刷新间隔（秒）',
    'servers': 'MCP 服务列表（JSON）',
    'provider': '接口类型',
    'voice': '音色',
    'language_type': '合成语种',
    'optimize_instructions': '优化 AI 动态语音表现指令',
    'response_format': '兼容接口音频格式',
    'speed': '兼容接口语速',
    'max_files': '本地语音缓存数（最多10）',
}

PATH_LABELS = {
    ('forward', 'image'): '识别节点内图片',
    ('forward', 'audio'): '识别节点内语音',
    ('forward', 'video'): '识别节点内视频',
    ('media', 'use_main'): '媒体模型路由',
    ('media', 'audio', 'enable'): '启用入站语音识别',
    ('media', 'audio', 'provider'): '独立语音接口协议',
    ('media', 'audio', 'mode'): '独立语音传输模式',
    ('media', 'audio', 'format'): '音频格式（留空自动检测）',
    ('media', 'audio', 'sample_rate'): '采样率（Hz）',
    ('media', 'video', 'mode'): '独立视频传输模式',
    ('media', 'video', 'enable'): '启用入站视频识别',
    ('media', 'audio', 'main_mode'): '主模型语音传输模式',
    ('media', 'video', 'main_mode'): '主模型视频传输模式',
    ('voice', 'max_chars'): '单条语音文本字数上限',
    ('voice', 'model'): '语音模型名称',
    ('voice', 'api_url'): '语音接口地址',
    ('voice', 'api_key'): '语音 API Key',
    ('mcp', 'timeout_sec'): 'MCP 请求超时（秒）',
}

ENUM_VALUES = {
    ('backend',): ('openai', 'anthropic', 'custom'),
    ('custom', 'wire'): ('openai', 'anthropic', 'responses'),
    ('permissions', 'admin_tools_min_role'): ('everyone', 'group_admin', 'master'),
    ('vision', 'use_main'): ('auto', 'true', 'false'),
    ('vision', 'mode'): ('base64', 'url'),
    ('media', 'use_main'): ('auto', 'true', 'false'),
    ('media', 'audio', 'provider'): ('auto', 'openai_compatible', 'dashscope_asr'),
    ('media', 'audio', 'mode'): ('base64', 'url'),
    ('media', 'audio', 'main_mode'): ('base64', 'url'),
    ('media', 'video', 'mode'): ('base64', 'url'),
    ('media', 'video', 'main_mode'): ('base64', 'url'),
    ('voice', 'provider'): ('dashscope_multimodal', 'openai_compatible'),
    ('voice', 'response_format'): ('mp3', 'wav', 'opus', 'ogg', 'aac', 'flac', 'pcm'),
    ('skills', 'translate_from'): ('auto', 'zh', 'en', 'ja', 'ko'),
    ('skills', 'translate_to'): ('zh', 'en', 'ja', 'ko'),
    ('skills', 'translate_query_to'): ('en', 'ja', 'ko'),
    ('skills', 'translate_backend'): ('bing', 'google', 'baidu', 'deepl'),
}

JSON_OBJECT_NAMES = {
    'extra_headers',
    'extra_body',
    'embedding_extra_headers',
    'group_persona',
    'titles',
}
GROUP_SWITCHES = [
    ('enabled', '插件启用'),
    ('ambient', '潜行群友'),
    ('admin_tools', '高危工具'),
    ('memory_history', '滚动摘要'),
    ('memory_long', '长期事实'),
]
GROUP_SWITCH_VALUES = ('继承默认', '开启', '关闭')
GROUP_TREE_COLUMNS = ('platform', 'group_id') + tuple(key for key, _label in GROUP_SWITCHES)
GROUP_TREE_HEADINGS = ('平台', '群 ID') + tuple(label for _key, label in GROUP_SWITCHES)
SECURITY_LEXICON_ACTIONS = ('下载 / 检查更新', '打开词库目录')

_gui_instance = None


def _fieldLabel(path):
    return PATH_LABELS.get(tuple(path), FIELD_LABELS.get(path[-1], path[-1]))


def _sectionHasLexiconActions(section):
    return section == 'security'


def _setNested(root, path, value):
    node = root
    for key in path[:-1]:
        node = node.setdefault(key, {})
    node[path[-1]] = value


def _parseValue(raw_value, template, path):
    """按默认值类型解析 GUI 输入，供保存与单测共用。"""
    if path == ('vision', 'use_main'):
        text = str(raw_value).strip().lower()
        if text == 'true':
            return True
        if text == 'false':
            return False
        return 'auto'
    if isinstance(template, bool):
        return bool(raw_value)
    if isinstance(template, int) and not isinstance(template, bool):
        return int(str(raw_value).strip())
    if isinstance(template, float):
        return float(str(raw_value).strip())
    if isinstance(template, (list, dict)):
        result = json.loads(str(raw_value) or ('[]' if isinstance(template, list) else '{}'))
        if isinstance(template, list) and not isinstance(result, list):
            raise ValueError('必须填写 JSON 数组')
        if isinstance(template, dict) and not isinstance(result, dict):
            raise ValueError('必须填写 JSON 对象')
        return result
    return str(raw_value)


class ConfigWindow:
    def __init__(self, Proc=None):
        self.Proc = Proc
        self.root = None
        self.notebook = None
        self.working_conf = {}
        self.current_section = None
        self.bindings = []
        self.category_list = None
        self.form_canvas = None
        self.form_frame = None
        self.status_var = None
        self.group_tree = None
        self.group_platform_var = None
        self.group_id_var = None
        self.group_switch_vars = {}
        self.group_global_vars = {}
        self.group_default_prefixes = None
        self.group_default_keywords = None
        self.runtime_text = None
        self.owns_mainloop = False

    def _logAction(self, message):
        OlivaAIAgent.conf.log(self.Proc, 2, 'GUI | %s' % str(message))

    def _createRoot(self):
        self.owns_mainloop = tkinter._default_root is None
        return tkinter.Tk() if self.owns_mainloop else tkinter.Toplevel()

    def _configureStyles(self):
        style = ttk.Style(self.root)
        style.configure('Title.TLabel', font=('Microsoft YaHei UI', 15, 'bold'))
        style.configure('Section.TLabel', font=('Microsoft YaHei UI', 11, 'bold'))
        style.configure('Hint.TLabel', foreground='#555555')
        style.configure('Status.TLabel', foreground='#186a3b')
        style.configure('Primary.TButton', padding=(14, 7))
        style.configure('TNotebook.Tab', padding=(14, 7))

    def _buildHeader(self):
        header = ttk.Frame(self.root, padding=(14, 12, 14, 8))
        header.grid(row=0, column=0, sticky='ew')
        header.columnconfigure(1, weight=1)
        ttk.Label(header, text='OlivaAIAgent 设置', style='Title.TLabel').grid(row=0, column=0, sticky='w')
        self.status_var = tkinter.StringVar(value='配置已载入')
        ttk.Label(header, textvariable=self.status_var, style='Status.TLabel').grid(
            row=0,
            column=1,
            sticky='e',
            padx=(16, 12),
        )
        ttk.Button(header, text='保存并应用', style='Primary.TButton', command=self.saveConfig).grid(
            row=0,
            column=2,
            padx=(0, 6),
        )
        ttk.Button(header, text='重新载入', command=self.reloadConfig).grid(row=0, column=3, padx=(0, 6))
        ttk.Button(
            header,
            text='打开数据目录',
            command=lambda: self.openPath(OlivaAIAgent.conf.dataPath),
        ).grid(
            row=0,
            column=4,
        )

    def _buildGlobalTab(self):
        page = ttk.Frame(self.notebook, padding=10)
        page.rowconfigure(0, weight=1)
        page.columnconfigure(1, weight=1)

        left = ttk.Frame(page)
        left.grid(row=0, column=0, sticky='nsw', padx=(0, 10))
        ttk.Label(left, text='配置分类', style='Section.TLabel').pack(anchor='w', pady=(0, 6))
        self.category_list = tkinter.Listbox(left, width=25, exportselection=False, activestyle='none')
        category_scroll = ttk.Scrollbar(left, orient='vertical', command=self.category_list.yview)
        self.category_list.configure(yscrollcommand=category_scroll.set)
        self.category_list.pack(side=tkinter.LEFT, fill=tkinter.Y, expand=True)
        category_scroll.pack(side=tkinter.RIGHT, fill=tkinter.Y)
        for section in SECTION_ORDER:
            self.category_list.insert(tkinter.END, SECTION_LABELS[section])
        self.category_list.bind('<<ListboxSelect>>', self._onSectionSelected)

        right = ttk.Frame(page)
        right.grid(row=0, column=1, sticky='nsew')
        right.rowconfigure(0, weight=1)
        right.columnconfigure(0, weight=1)
        self.form_canvas = tkinter.Canvas(right, highlightthickness=0, background='#ffffff')
        form_scroll = ttk.Scrollbar(right, orient='vertical', command=self.form_canvas.yview)
        self.form_canvas.configure(yscrollcommand=form_scroll.set)
        self.form_canvas.grid(row=0, column=0, sticky='nsew')
        form_scroll.grid(row=0, column=1, sticky='ns')
        self.form_frame = ttk.Frame(self.form_canvas, padding=(18, 14, 18, 18))
        form_window = self.form_canvas.create_window((0, 0), window=self.form_frame, anchor='nw')
        self.form_frame.bind(
            '<Configure>',
            lambda _event: self.form_canvas.configure(scrollregion=self.form_canvas.bbox('all')),
        )
        self.form_canvas.bind(
            '<Configure>',
            lambda event: self.form_canvas.itemconfigure(form_window, width=event.width),
        )
        self.form_canvas.bind('<MouseWheel>', self._onMouseWheel, add='+')
        self.form_frame.bind('<MouseWheel>', self._onMouseWheel, add='+')

        footer = ttk.Frame(page)
        footer.grid(row=1, column=1, sticky='ew', pady=(8, 0))
        ttk.Button(footer, text='恢复本页默认值', command=self.resetCurrentSection).pack(side=tkinter.LEFT)
        ttk.Label(footer, text='修改后点击顶部“保存并应用”', style='Hint.TLabel').pack(side=tkinter.RIGHT)

        self.notebook.add(page, text='全部配置')

    def _buildGroupTab(self):
        page = ttk.Frame(self.notebook, padding=12)
        page.rowconfigure(2, weight=1)
        page.columnconfigure(0, weight=1)

        global_frame = ttk.LabelFrame(page, text='全局群设置', padding=10)
        global_frame.grid(row=0, column=0, columnspan=2, sticky='ew', pady=(0, 10))
        global_frame.columnconfigure(4, weight=1)
        global_switches = (
            ('global', '插件全局启用'),
            ('whitelist', '白名单模式'),
            ('group_default', '新群默认启用'),
            ('ambient_default', '新群潜行默认启用'),
        )
        for index, (key, label) in enumerate(global_switches):
            variable = tkinter.BooleanVar(value=False)
            self.group_global_vars[key] = variable
            ttk.Checkbutton(global_frame, text=label, variable=variable).grid(
                row=0,
                column=index,
                sticky='w',
                padx=(0, 18),
            )
        ttk.Button(global_frame, text='保存全局群设置', command=self.saveGroupGlobals).grid(
            row=0,
            column=4,
            sticky='e',
        )
        ttk.Label(global_frame, text='默认触发前缀（JSON 数组）').grid(row=1, column=0, sticky='nw', pady=(10, 0))
        self.group_default_prefixes = scrolledtext.ScrolledText(global_frame, height=3, wrap='word', undo=True)
        self.group_default_prefixes.grid(row=1, column=1, columnspan=4, sticky='ew', pady=(10, 0))
        ttk.Label(global_frame, text='默认触发关键词（JSON 数组）').grid(row=2, column=0, sticky='nw', pady=(8, 0))
        self.group_default_keywords = scrolledtext.ScrolledText(global_frame, height=3, wrap='word', undo=True)
        self.group_default_keywords.grid(row=2, column=1, columnspan=4, sticky='ew', pady=(8, 0))

        ttk.Label(page, text='群列表与群级覆盖', style='Section.TLabel').grid(
            row=1,
            column=0,
            sticky='w',
            pady=(0, 8),
        )

        self.group_tree = ttk.Treeview(page, columns=GROUP_TREE_COLUMNS, show='headings', height=13)
        widths = [100, 220, 100, 100, 100, 100, 100]
        for column, heading, width in zip(GROUP_TREE_COLUMNS, GROUP_TREE_HEADINGS, widths, strict=False):
            self.group_tree.heading(column, text=heading)
            self.group_tree.column(column, width=width, minwidth=80, anchor='center')
        self.group_tree.grid(row=2, column=0, sticky='nsew')
        tree_scroll = ttk.Scrollbar(page, orient='vertical', command=self.group_tree.yview)
        tree_xscroll = ttk.Scrollbar(page, orient='horizontal', command=self.group_tree.xview)
        self.group_tree.configure(yscrollcommand=tree_scroll.set, xscrollcommand=tree_xscroll.set)
        tree_scroll.grid(row=2, column=1, sticky='ns')
        tree_xscroll.grid(row=3, column=0, sticky='ew')
        self.group_tree.bind('<<TreeviewSelect>>', self._onGroupSelected)

        editor = ttk.LabelFrame(page, text='编辑群覆盖', padding=12)
        editor.grid(row=4, column=0, columnspan=2, sticky='ew', pady=(12, 0))
        editor.columnconfigure(1, weight=1)
        editor.columnconfigure(3, weight=1)
        self.group_platform_var = tkinter.StringVar(value='qq')
        self.group_id_var = tkinter.StringVar(value='')
        ttk.Label(editor, text='平台').grid(row=0, column=0, sticky='w')
        ttk.Combobox(
            editor,
            textvariable=self.group_platform_var,
            values=('*', 'qq', 'qqGuild', 'telegram', 'discord', 'kaiheila', 'kook', 'dodo', 'fanbook'),
            width=18,
        ).grid(
            row=0,
            column=1,
            sticky='ew',
            padx=(6, 18),
        )
        ttk.Label(editor, text='群 ID').grid(row=0, column=2, sticky='w')
        ttk.Entry(editor, textvariable=self.group_id_var).grid(row=0, column=3, sticky='ew', padx=(6, 0))
        switches = ttk.Frame(editor)
        switches.grid(row=1, column=0, columnspan=4, sticky='ew', pady=(12, 0))
        for index, (key, label) in enumerate(GROUP_SWITCHES):
            switches.columnconfigure(index, weight=1)
            slot = ttk.Frame(switches)
            slot.grid(row=0, column=index, sticky='ew', padx=(0 if index == 0 else 5, 5))
            ttk.Label(slot, text=label).pack(anchor='w')
            variable = tkinter.StringVar(value=GROUP_SWITCH_VALUES[0])
            self.group_switch_vars[key] = variable
            ttk.Combobox(
                slot,
                textvariable=variable,
                state='readonly',
                values=GROUP_SWITCH_VALUES,
                width=12,
            ).pack(
                fill=tkinter.X,
                pady=(3, 0),
            )
        ttk.Label(
            editor,
            text='触发前缀和关键词统一使用上方全局设置，不提供群级覆盖。',
            style='Hint.TLabel',
        ).grid(row=2, column=0, columnspan=4, sticky='w', pady=(10, 0))
        buttons = ttk.Frame(editor)
        buttons.grid(row=3, column=0, columnspan=4, sticky='ew', pady=(12, 0))
        ttk.Button(buttons, text='保存群设置', command=self.saveGroupConfig).pack(side=tkinter.LEFT)
        ttk.Button(buttons, text='新建 / 清空表单', command=self.clearGroupForm).pack(
            side=tkinter.LEFT,
            padx=(6, 0),
        )
        ttk.Button(buttons, text='移除选中群', command=self.deleteSelectedGroup).pack(side=tkinter.RIGHT)

        self.notebook.add(page, text='群级设置')

    def _buildMaintenanceTab(self):
        page = ttk.Frame(self.notebook, padding=14)
        page.rowconfigure(2, weight=1)
        page.columnconfigure(0, weight=1)
        toolbar = ttk.Frame(page)
        toolbar.grid(row=0, column=0, sticky='ew', pady=(0, 10))
        ttk.Button(toolbar, text='刷新运行状态', command=self.refreshRuntimeStatus).pack(side=tkinter.LEFT)
        ttk.Button(toolbar, text='重建技能索引', command=self.rebuildSkills).pack(side=tkinter.LEFT, padx=(6, 0))
        ttk.Button(toolbar, text='重载静态知识库', command=self.reloadKnowledge).pack(side=tkinter.LEFT, padx=(6, 0))
        ttk.Button(toolbar, text='刷新 MCP 工具', command=self.refreshMcp).pack(side=tkinter.LEFT, padx=(6, 0))
        ttk.Button(
            toolbar,
            text='打开技能目录',
            command=lambda: self.openPath(os.path.join(OlivaAIAgent.conf.dataPath, 'skills'), '技能目录'),
        ).pack(side=tkinter.RIGHT)
        ttk.Button(
            toolbar,
            text='打开知识目录',
            command=lambda: self.openPath(os.path.join(OlivaAIAgent.conf.dataPath, 'Knowledge'), '知识目录'),
        ).pack(side=tkinter.RIGHT, padx=(0, 6))
        lexicon_frame = ttk.LabelFrame(page, text='选装敏感词库', padding=10)
        lexicon_frame.grid(row=1, column=0, sticky='ew', pady=(0, 10))
        lexicon_frame.columnconfigure(0, weight=1)
        ttk.Label(
            lexicon_frame,
            text='在线安装 konsheng/Sensitive-lexicon 政治分类；再次点击会自动检测并仅下载更新。',
            style='Hint.TLabel',
        ).grid(row=0, column=0, sticky='w')
        ttk.Button(
            lexicon_frame,
            text='在线安装 / 检查更新',
            command=self.updateSensitiveLexicon,
        ).grid(row=0, column=1, padx=(12, 0))
        ttk.Button(
            lexicon_frame,
            text='打开词库目录',
            command=lambda: self.openPath(OlivaAIAgent.lexiconUpdater.lexiconDir(), '敏感词库目录'),
        ).grid(row=0, column=2, padx=(6, 0))
        self.runtime_text = scrolledtext.ScrolledText(page, wrap='word', state='disabled', font=('Consolas', 10))
        self.runtime_text.grid(row=2, column=0, sticky='nsew')
        self.notebook.add(page, text='运行维护')

    def _onMouseWheel(self, event):
        if self.notebook.index(self.notebook.select()) == 0:
            self.form_canvas.yview_scroll(int(-event.delta / 120), 'units')

    def _sectionData(self, section):
        if section == 'general':
            return {
                'backend': self.working_conf.get('backend', 'openai'),
                'debug_log': self.working_conf.get('debug_log', False),
            }, ()
        section_data = self.working_conf.get(section, {})
        if section == 'trigger' and isinstance(section_data, dict):
            section_data = {
                key: value
                for key, value in section_data.items()
                if key not in {'prefix', 'keywords', '_keywords说明'}
            }
        if section == 'ambient' and isinstance(section_data, dict):
            section_data = {key: value for key, value in section_data.items() if key != 'enable_default'}
        return section_data, (section,)

    def _onSectionSelected(self, _event=None):
        selection = self.category_list.curselection()
        if not selection:
            return
        section = SECTION_ORDER[selection[0]]
        if section == self.current_section:
            return
        if self.current_section is not None and not self._commitCurrent(show_error=True):
            old_index = SECTION_ORDER.index(self.current_section)
            self.category_list.selection_clear(0, tkinter.END)
            self.category_list.selection_set(old_index)
            return
        self.current_section = section
        self._renderCurrentSection()

    def _renderCurrentSection(self):
        for child in self.form_frame.winfo_children():
            child.destroy()
        self.bindings = []
        self.form_frame.columnconfigure(1, weight=1)
        section_data, base_path = self._sectionData(self.current_section)
        ttk.Label(
            self.form_frame,
            text=SECTION_LABELS[self.current_section],
            style='Title.TLabel',
        ).grid(row=0, column=0, columnspan=2, sticky='w', pady=(0, 8))
        description = section_data.get('_说明', '') if isinstance(section_data, dict) else ''
        row = 1
        if description:
            ttk.Label(
                self.form_frame,
                text=str(description),
                style='Hint.TLabel',
                wraplength=760,
                justify='left',
            ).grid(row=row, column=0, columnspan=2, sticky='ew', pady=(0, 12))
            row += 1
        row = self._addFields(section_data, base_path, row, depth=0)
        if _sectionHasLexiconActions(self.current_section):
            self._addSecurityLexiconActions(row)
        self.form_canvas.yview_moveto(0)

    def _addSecurityLexiconActions(self, row):
        status = OlivaAIAgent.lexiconUpdater.getStatus()
        frame = ttk.LabelFrame(self.form_frame, text='选装敏感词库在线维护', padding=12)
        frame.grid(row=row, column=0, columnspan=2, sticky='ew', pady=(16, 4))
        frame.columnconfigure(0, weight=1)
        if status['installed']:
            status_text = '已安装：%d 词；上次检查：%s' % (
                status['words'], status['checked_at'] or '未知',
            )
        else:
            status_text = '尚未安装在线政治分类词库'
        ttk.Label(
            frame,
            text='%s\n来源：%s（%s）；本地匹配，不会把词表发送给模型。' % (
                status_text, status['source'], status['license'],
            ),
            style='Hint.TLabel',
            justify='left',
        ).grid(row=0, column=0, sticky='w')
        ttk.Button(
            frame,
            text=SECURITY_LEXICON_ACTIONS[0],
            command=self.updateSensitiveLexicon,
        ).grid(row=0, column=1, padx=(12, 0))
        ttk.Button(
            frame,
            text=SECURITY_LEXICON_ACTIONS[1],
            command=lambda: self.openPath(OlivaAIAgent.lexiconUpdater.lexiconDir(), '敏感词库目录'),
        ).grid(row=0, column=2, padx=(6, 0))

    def _addFields(self, data, base_path, row, depth):
        if not isinstance(data, dict):
            return row
        for key, value in data.items():
            if str(key).startswith('_'):
                continue
            path = base_path + (key,)
            if isinstance(value, dict) and key not in JSON_OBJECT_NAMES:
                ttk.Separator(self.form_frame).grid(row=row, column=0, columnspan=2, sticky='ew', pady=(12, 8))
                row += 1
                ttk.Label(self.form_frame, text=_fieldLabel(path), style='Section.TLabel').grid(
                    row=row,
                    column=0,
                    columnspan=2,
                    sticky='w',
                    pady=(0, 5),
                )
                row += 1
                row = self._addFields(value, path, row, depth + 1)
                continue
            row = self._addField(path, value, row, depth)
        return row

    def _addField(self, path, value, row, depth):
        label = ttk.Label(self.form_frame, text=_fieldLabel(path))
        label.grid(row=row, column=0, sticky='nw', padx=(18 * depth, 16), pady=(6, 4))
        binding = {'path': path, 'template': copy.deepcopy(value)}
        enum_values = ENUM_VALUES.get(path)
        if path[-2:] == ('thinking', 'type'):
            enum_values = ('disabled', 'enabled')

        if isinstance(value, bool):
            variable = tkinter.BooleanVar(value=value)
            widget = ttk.Checkbutton(self.form_frame, variable=variable)
            widget.grid(row=row, column=1, sticky='w', pady=(5, 4))
            binding.update({'kind': 'bool', 'variable': variable})
        elif enum_values:
            shown_value = str(value).lower() if isinstance(value, bool) else str(value)
            variable = tkinter.StringVar(value=shown_value)
            widget = ttk.Combobox(
                self.form_frame,
                textvariable=variable,
                values=enum_values,
                state='readonly',
            )
            widget.grid(row=row, column=1, sticky='ew', pady=(5, 4))
            binding.update({'kind': 'scalar', 'variable': variable})
        elif isinstance(value, (list, dict)) or (isinstance(value, str) and len(value) > 140):
            widget = scrolledtext.ScrolledText(self.form_frame, height=6, wrap='word', undo=True)
            if isinstance(value, (list, dict)):
                widget.insert('1.0', json.dumps(value, ensure_ascii=False, indent=2))
                kind = 'json'
            else:
                widget.insert('1.0', value)
                kind = 'text'
            widget.grid(row=row, column=1, sticky='ew', pady=(5, 6))
            binding.update({'kind': kind, 'widget': widget})
        else:
            variable = tkinter.StringVar(value=str(value))
            widget = ttk.Entry(self.form_frame, textvariable=variable)
            if path[-1] == 'api_key' or path[-1].endswith('_api_key'):
                widget.configure(show='*')
                reveal = ttk.Checkbutton(
                    self.form_frame,
                    text='显示',
                    command=lambda target=widget: target.configure(show='' if target.cget('show') else '*'),
                )
                reveal.grid(row=row, column=2, sticky='w', padx=(6, 0))
            widget.grid(row=row, column=1, sticky='ew', pady=(5, 4))
            binding.update({'kind': 'scalar', 'variable': variable})
        self.bindings.append(binding)
        return row + 1

    def _commitCurrent(self, show_error=False):
        errors = []
        for binding in self.bindings:
            try:
                if binding['kind'] == 'bool':
                    raw = binding['variable'].get()
                elif binding['kind'] in {'json', 'text'}:
                    raw = binding['widget'].get('1.0', tkinter.END).rstrip('\n')
                else:
                    raw = binding['variable'].get()
                value = _parseValue(raw, binding['template'], binding['path'])
                _setNested(self.working_conf, binding['path'], value)
            except Exception as e:
                errors.append('{}：{}'.format(_fieldLabel(binding['path']), e))
        if errors and show_error:
            messagebox.showerror('配置格式错误', '\n'.join(errors[:8]), parent=self.root)
        return not errors

    def saveConfig(self):
        if not self._commitCurrent(show_error=True):
            return
        if not self._commitGroupGlobal(show_error=True):
            return
        self._logAction('正在保存并应用配置')
        try:
            self.working_conf = OlivaAIAgent.conf.replace(self.working_conf, save_now=True)
            OlivaAIAgent.mcp.invalidate()
            self.status_var.set('配置已保存并立即应用')
            self.refreshRuntimeStatus()
        except Exception as e:
            messagebox.showerror('保存失败', f'{type(e).__name__}: {e}', parent=self.root)

    def reloadConfig(self):
        if not messagebox.askyesno('重新载入', '放弃尚未保存的界面修改，并从磁盘重新载入？', parent=self.root):
            return
        self._logAction('正在从磁盘重新载入配置')
        try:
            OlivaAIAgent.conf.load()
            OlivaAIAgent.mcp.invalidate()
            self.working_conf = OlivaAIAgent.conf.snapshot()
            self._renderCurrentSection()
            self._syncGroupGlobalForm()
            self.refreshGroupTree()
            self.refreshRuntimeStatus()
            self.status_var.set('已从磁盘重新载入')
        except Exception as e:
            messagebox.showerror('载入失败', f'{type(e).__name__}: {e}', parent=self.root)

    def resetCurrentSection(self):
        if not self.current_section:
            return
        self._logAction('正在恢复配置分类默认值 | 分类=%s' % SECTION_LABELS[self.current_section])
        if not messagebox.askyesno(
            '恢复默认',
            '恢复当前分类的默认值？保存前仍可重新载入撤销。',
            parent=self.root,
        ):
            return
        if self.current_section == 'general':
            self.working_conf['backend'] = copy.deepcopy(OlivaAIAgent.conf.DEFAULT_CONF['backend'])
            self.working_conf['debug_log'] = copy.deepcopy(OlivaAIAgent.conf.DEFAULT_CONF['debug_log'])
        elif self.current_section == 'trigger':
            prefixes = copy.deepcopy(self.working_conf.get('trigger', {}).get('prefix', []))
            keywords = copy.deepcopy(self.working_conf.get('trigger', {}).get('keywords', []))
            self.working_conf['trigger'] = copy.deepcopy(OlivaAIAgent.conf.DEFAULT_CONF['trigger'])
            self.working_conf['trigger']['prefix'] = prefixes
            self.working_conf['trigger']['keywords'] = keywords
        elif self.current_section == 'ambient':
            enable_default = bool(self.working_conf.get('ambient', {}).get('enable_default', False))
            self.working_conf['ambient'] = copy.deepcopy(OlivaAIAgent.conf.DEFAULT_CONF['ambient'])
            self.working_conf['ambient']['enable_default'] = enable_default
        else:
            self.working_conf[self.current_section] = copy.deepcopy(
                OlivaAIAgent.conf.DEFAULT_CONF[self.current_section]
            )
        self._renderCurrentSection()
        self.status_var.set('当前分类已恢复默认，尚未保存')

    def refreshGroupTree(self):
        self.group_tree.delete(*self.group_tree.get_children())
        groups = OlivaAIAgent.conf.groupsSnapshot()
        for platform in sorted(groups):
            platform_groups = groups.get(platform, {})
            if not isinstance(platform_groups, dict):
                continue
            for group_id in sorted(platform_groups):
                node = platform_groups.get(group_id, {})
                if not isinstance(node, dict):
                    node = {}
                values = [platform, group_id]
                for key, _label in GROUP_SWITCHES:
                    values.append('默认' if key not in node else ('开' if node[key] else '关'))
                self.group_tree.insert('', tkinter.END, values=values)

    def _syncGroupGlobalForm(self):
        if not self.group_global_vars:
            return
        self.group_global_vars['global'].set(bool(self.working_conf.get('enable', {}).get('global', True)))
        self.group_global_vars['whitelist'].set(
            bool(self.working_conf.get('whitelist', {}).get('enabled', False))
        )
        self.group_global_vars['group_default'].set(
            bool(self.working_conf.get('enable', {}).get('group_default', True))
        )
        self.group_global_vars['ambient_default'].set(
            bool(self.working_conf.get('ambient', {}).get('enable_default', False))
        )
        fields = (
            (self.group_default_prefixes, self.working_conf.get('trigger', {}).get('prefix', [])),
            (self.group_default_keywords, self.working_conf.get('trigger', {}).get('keywords', [])),
        )
        for widget, value in fields:
            widget.delete('1.0', tkinter.END)
            widget.insert('1.0', json.dumps(value, ensure_ascii=False, indent=2))

    @staticmethod
    def _parseStringList(raw, label, allow_inherit=False):
        text = str(raw).strip()
        if allow_inherit and not text:
            return None
        value = json.loads(text or '[]')
        if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
            raise ValueError('%s 必须是字符串 JSON 数组' % label)
        return value

    def _commitGroupGlobal(self, show_error=False, target=None):
        try:
            prefixes = self._parseStringList(
                self.group_default_prefixes.get('1.0', tkinter.END),
                '默认触发前缀',
            )
            keywords = self._parseStringList(
                self.group_default_keywords.get('1.0', tkinter.END),
                '默认触发关键词',
            )
            config = self.working_conf if target is None else target
            config.setdefault('enable', {})['global'] = self.group_global_vars['global'].get()
            config.setdefault('enable', {})['group_default'] = self.group_global_vars['group_default'].get()
            config.setdefault('whitelist', {})['enabled'] = self.group_global_vars['whitelist'].get()
            config.setdefault('ambient', {})['enable_default'] = self.group_global_vars[
                'ambient_default'
            ].get()
            config.setdefault('trigger', {})['prefix'] = prefixes
            config.setdefault('trigger', {})['keywords'] = keywords
            return True
        except Exception as e:
            if show_error:
                messagebox.showerror('群设置格式错误', str(e), parent=self.root)
            return False

    def saveGroupGlobals(self):
        live_conf = OlivaAIAgent.conf.snapshot()
        if not self._commitGroupGlobal(show_error=True, target=live_conf):
            return
        self._logAction('正在保存全局群设置')
        try:
            OlivaAIAgent.conf.replace(live_conf, save_now=True)
            self._commitGroupGlobal(target=self.working_conf)
            self._syncGroupGlobalForm()
            self.refreshGroupTree()
            self.refreshRuntimeStatus()
            self.status_var.set('全局群设置已保存并立即应用')
        except Exception as e:
            messagebox.showerror('保存失败', f'{type(e).__name__}: {e}', parent=self.root)

    def _onGroupSelected(self, _event=None):
        selection = self.group_tree.selection()
        if not selection:
            return
        values = self.group_tree.item(selection[0], 'values')
        platform = str(values[0])
        group_id = str(values[1])
        node = OlivaAIAgent.conf.groupsSnapshot().get(platform, {}).get(group_id, {})
        self.group_platform_var.set(platform)
        self.group_id_var.set(group_id)
        for key, _label in GROUP_SWITCHES:
            state = GROUP_SWITCH_VALUES[0] if key not in node else GROUP_SWITCH_VALUES[1 if node[key] else 2]
            self.group_switch_vars[key].set(state)

    def clearGroupForm(self):
        self.group_tree.selection_remove(*self.group_tree.selection())
        self.group_id_var.set('')
        for variable in self.group_switch_vars.values():
            variable.set(GROUP_SWITCH_VALUES[0])

    def saveGroupConfig(self):
        platform = self.group_platform_var.get().strip()
        group_id = self.group_id_var.get().strip()
        values = {}
        for key, variable in self.group_switch_vars.items():
            state = variable.get()
            if state != GROUP_SWITCH_VALUES[0]:
                values[key] = state == GROUP_SWITCH_VALUES[1]
        self._logAction('正在保存群级设置 | 平台=%s | 群=%s' % (platform, group_id))
        try:
            OlivaAIAgent.conf.replaceGroupConfig(platform, group_id, values)
            self.refreshGroupTree()
            self.status_var.set('群级设置已保存')
        except Exception as e:
            messagebox.showerror('保存失败', f'{type(e).__name__}: {e}', parent=self.root)

    def deleteSelectedGroup(self):
        selection = self.group_tree.selection()
        if not selection:
            messagebox.showwarning('删除群覆盖', '请先选择一行。', parent=self.root)
            return
        values = self.group_tree.item(selection[0], 'values')
        if not messagebox.askyesno(
            '移除群设置',
            f'从群列表移除 {values[0]} / {values[1]}？白名单模式开启时，该群将不再可用。',
            parent=self.root,
        ):
            return
        self._logAction('正在删除群级覆盖 | 平台=%s | 群=%s' % (values[0], values[1]))
        OlivaAIAgent.conf.deleteGroupConfig(values[0], values[1])
        self.clearGroupForm()
        self.refreshGroupTree()
        self.status_var.set('群级覆盖已删除')

    def _runtimeLines(self):
        backend = str(OlivaAIAgent.conf.get('backend', default='openai'))
        semantic = OlivaAIAgent.semantic.getStatus()
        vision = OlivaAIAgent.vision.getVisionStatus()
        media = OlivaAIAgent.media.getStatus()
        voice = OlivaAIAgent.voice.getStatus()
        mcp = OlivaAIAgent.mcp.getStatus()
        lexicon = OlivaAIAgent.lexiconUpdater.getStatus()
        core_logger = OlivaAIAgent.coreLogger.getStatus(self.Proc)
        group_override_count = sum(
            len(groups) for groups in OlivaAIAgent.conf.groupsSnapshot().values() if isinstance(groups, dict)
        )
        return [
            f'配置文件: {os.path.abspath(OlivaAIAgent.conf.CONFIG_PATH)}',
            '当前后端: {} / {}'.format(backend, OlivaAIAgent.conf.get(backend, 'model', default='-')),
            f'工具: 内置 {len(OlivaAIAgent.tools.TOOLS)} 个 / MCP {mcp["tools"]} 个',
            f'技能索引: {len(OlivaAIAgent.skills._index)} 个（{OlivaAIAgent.skills.backendName()}）',
            '长期事实: {} / {}'.format(semantic.get('mode', '-'), semantic.get('model') or '-'),
            '图片视觉: {} / {} / {}'.format(
                '启用' if vision.get('enabled') else '关闭',
                vision.get('route', '-'),
                vision.get('model') or '-',
            ),
            '入站语音: {} / {} / {}'.format(
                '就绪' if media['audio'].get('ready') else (
                    '未就绪' if media['audio'].get('enabled') else '关闭'
                ),
                media['audio'].get('route', '-'),
                media['audio'].get('model') or '-',
            ),
            '入站视频: {} / {} / {}'.format(
                '就绪' if media['video'].get('ready') else (
                    '未就绪' if media['video'].get('enabled') else '关闭'
                ),
                media['video'].get('route', '-'),
                media['video'].get('model') or '-',
            ),
            '语音模型: {} / {} / {}'.format(
                '就绪' if voice.get('ready') else ('已启用但未就绪' if voice.get('enabled') else '关闭'),
                voice.get('model') or '-',
                voice.get('voice') or '-',
            ),
            'MCP: {} / 服务 {}/{} / 工具 {}'.format(
                '启用' if mcp.get('enabled') else '关闭',
                mcp.get('connected', 0),
                mcp.get('servers', 0),
                mcp.get('tools', 0),
            ),
            f'待触发提醒: {OlivaAIAgent.reminder.total()} 个',
            'OlivaDice 团日志桥接: {}'.format(
                '已启用，等待 Logger 开团即可记录'
                if core_logger['active'] and core_logger['logger_loaded']
                else ('Core 已就绪，Logger 未加载' if core_logger['active'] else (
                    '已关闭' if not core_logger['enabled'] else '未检测到 Core'
                ))
            ),
            f'群级覆盖: {group_override_count} 个',
            '选装政治词库: {}'.format(
                '{} 词 / 上次检查 {}'.format(
                    lexicon['words'], lexicon['checked_at'] or '未知',
                ) if lexicon['installed'] else '未安装'
            ),
        ]

    def refreshRuntimeStatus(self):
        try:
            content = '\n'.join(self._runtimeLines())
        except Exception as e:
            content = f'读取运行状态失败: {type(e).__name__}: {e}'
        self.runtime_text.configure(state='normal')
        self.runtime_text.delete('1.0', tkinter.END)
        self.runtime_text.insert('1.0', content)
        self.runtime_text.configure(state='disabled')

    def _runMaintenance(self, name, action, success_text, on_success=None):
        self.status_var.set(f'{name}进行中…')
        self._logAction('正在执行%s' % name)

        def worker():
            result = None
            succeeded = False
            try:
                result = action()
                message = success_text(result)
                succeeded = True
            except Exception as e:
                message = f'{name}失败：{type(e).__name__}: {e}'

            def done():
                if on_success is not None and succeeded:
                    try:
                        on_success(result)
                    except Exception as e:
                        self.status_var.set(f'{name}已完成，但界面刷新失败：{type(e).__name__}: {e}')
                        self.refreshRuntimeStatus()
                        return
                self.status_var.set(message)
                self.refreshRuntimeStatus()

            try:
                self.root.after(0, done)
            except Exception:
                pass

        threading.Thread(target=worker, daemon=True, name=f'OlivaAIAgent-GUI-{name}').start()

    def rebuildSkills(self):
        self._runMaintenance(
            '技能索引重建',
            OlivaAIAgent.skills.buildIndex,
            lambda result: f'技能索引已重建：{len(result)} 个',
        )

    def reloadKnowledge(self):
        self._runMaintenance(
            '静态知识重载',
            OlivaAIAgent.knowledge.loadStatic,
            lambda result: f'静态知识已重载：{int(result)} 条',
        )

    def refreshMcp(self):
        self._runMaintenance(
            'MCP 工具刷新',
            lambda: OlivaAIAgent.mcp.refresh(force=True),
            lambda result: 'MCP 已刷新：服务 {}/{}，工具 {} 个'.format(
                result.get('connected', 0),
                result.get('servers', 0),
                result.get('tools', 0),
            ),
        )

    def updateSensitiveLexicon(self):
        if not self._commitCurrent(show_error=True):
            return
        pending_config = copy.deepcopy(self.working_conf)
        if not self._commitGroupGlobal(show_error=True, target=pending_config):
            return

        def action():
            result = OlivaAIAgent.lexiconUpdater.checkAndUpdate()
            OlivaAIAgent.lexiconUpdater.activateConfig(pending_config, result['path'])
            OlivaAIAgent.conf.replace(pending_config, save_now=True)
            return result

        def on_success(_result):
            self.working_conf = OlivaAIAgent.conf.snapshot()
            self._renderCurrentSection()
            self._syncGroupGlobalForm()

        self._runMaintenance(
            '敏感词库更新',
            action,
            lambda result: (
                '敏感词库已更新并启用：%d 词' % result['words']
                if result['updated']
                else '敏感词库已是最新版并保持启用：%d 词' % result['words']
            ),
            on_success=on_success,
        )

    def openPath(self, path, name='数据目录'):
        self._logAction('正在打开%s' % name)
        try:
            OlivaAIAgent.conf.releaseDir(path)
            os.startfile(os.path.abspath(path))
        except Exception as e:
            messagebox.showerror('打开目录失败', f'{type(e).__name__}: {e}', parent=self.root)

    def _close(self):
        global _gui_instance
        _gui_instance = None
        self.root.destroy()

    def start(self):
        self.root = self._createRoot()
        self._logAction('正在打开设置面板')
        self.root.title('OlivaAIAgent 设置')
        self.root.geometry('1120x760')
        self.root.minsize(900, 620)
        self.root.rowconfigure(1, weight=1)
        self.root.columnconfigure(0, weight=1)
        self.root.protocol('WM_DELETE_WINDOW', self._close)
        self._configureStyles()
        self._buildHeader()
        self.notebook = ttk.Notebook(self.root)
        self.notebook.grid(row=1, column=0, sticky='nsew', padx=14, pady=(0, 14))
        self._buildGlobalTab()
        self._buildGroupTab()
        self._buildMaintenanceTab()
        self.working_conf = OlivaAIAgent.conf.snapshot()
        if not self.working_conf:
            self.working_conf = copy.deepcopy(OlivaAIAgent.conf.DEFAULT_CONF)
        self._syncGroupGlobalForm()
        self.category_list.selection_set(0)
        self._onSectionSelected()
        self.refreshGroupTree()
        self.refreshRuntimeStatus()
        if self.owns_mainloop:
            self.root.mainloop()


def openConfigWindow(Proc=None):
    """打开或激活唯一配置窗口。"""
    global _gui_instance
    try:
        if _gui_instance is not None and _gui_instance.root is not None and _gui_instance.root.winfo_exists():
            _gui_instance.root.deiconify()
            _gui_instance.root.lift()
            _gui_instance.root.focus_force()
            return
    except Exception:
        _gui_instance = None
    _gui_instance = ConfigWindow(Proc=Proc)
    _gui_instance.start()

import io
import json
import os
import re
import threading
import time
import traceback
import uuid
import zipfile
from typing import Any
from urllib import parse

import requests

from . import config

try:
    import OlivaDiceCore

    _has_oliva_dice_core = True
except Exception:
    _has_oliva_dice_core = False

try:
    import rarfile

    _has_rarfile = True
except Exception:
    _has_rarfile = False

try:
    import py7zr

    _has_py7zr = True
except Exception:
    _has_py7zr = False

_g_proc = None
_g_data_dir = os.path.join('plugin', 'data', config.plugin_name)
_g_config_file = os.path.join(_g_data_dir, 'config.json')

_default_plugin_config = {
    'api_url': config.DEFAULT_API_URL,
    'api_key': '',
    'model': config.DEFAULT_MODEL,
    'thinking': config.DEFAULT_THINKING,
    'output_mode': config.DEFAULT_OUTPUT_MODE,
    'output_format': config.DEFAULT_OUTPUT_FORMAT,
}

_command_prefixes = ['.', '。', '/']

# ===== 一次性授权码（纯内存，不落盘，重启即清空） =====
_code_lock = threading.Lock()  # 保护下面两个结构的并发安全
_code_store: dict[str, bool] = {}  # {code: True} 有效且未使用的码
_code_in_progress: set = set()  # 正在生成中、被锁定的码（防同一码并发复用）
_pending_qqguild_uploads: dict[tuple[str, str, str, str], dict[str, str | None]] = {}


def _load_config() -> dict[str, Any]:
    """加载插件配置文件，失败时返回默认值。"""
    try:
        if os.path.exists(_g_config_file):
            with open(_g_config_file, encoding='utf-8') as f:
                saved = json.load(f)
            merged = dict(_default_plugin_config)
            if isinstance(saved, dict):
                merged.update(saved)
            return merged
    except Exception:
        pass
    return dict(_default_plugin_config)


def _save_config(cfg: dict[str, Any]) -> bool:
    """保存插件配置文件。"""
    try:
        os.makedirs(_g_data_dir, exist_ok=True)
        with open(_g_config_file, 'w', encoding='utf-8') as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
        return True
    except Exception:
        return False


def _safe_str(value: Any) -> str:
    try:
        return str(value)
    except Exception:
        return ''


def _strip_reply_segment(text: str) -> str:
    return re.sub(r'^\[OP:reply,id=[^\]]+\]\s*', '', text)


def _parse_command(message_text: str):
    """解析 .xxx 命令，返回 (命令名, 参数文本)。"""
    text = _strip_reply_segment(_safe_str(message_text))
    for prefix in _command_prefixes:
        if text.startswith(prefix):
            body = text[len(prefix) :].lstrip()
            parts = body.split(None, 1)
            cmd = parts[0].lower() if parts else ''
            arg = parts[1] if len(parts) > 1 else ''
            return cmd, arg
    return '', ''


def _get_bot_hash(plugin_event) -> str:
    try:
        return _safe_str(plugin_event.bot_info.hash)
    except Exception:
        return ''


def _get_bot_id(plugin_event) -> str:
    try:
        return _safe_str(plugin_event.bot_info.id)
    except Exception:
        return ''


def _get_bot_name(plugin_event) -> str:
    if _has_oliva_dice_core:
        try:
            bot_hash = _get_bot_hash(plugin_event)
            return _safe_str(OlivaDiceCore.msgCustom.dictStrCustomDict.get(bot_hash, {}).get('strBotName', ''))
        except Exception:
            pass
    return ''


def _get_bot_display_name(plugin_event) -> str:
    name = _get_bot_name(plugin_event)
    return name if name else f'Bot({_get_bot_id(plugin_event)})'


def _get_group_id(plugin_event) -> str:
    try:
        return _safe_str(getattr(plugin_event.data, 'group_id', ''))
    except Exception:
        return ''


def _get_host_id(plugin_event) -> str:
    try:
        return _safe_str(getattr(plugin_event.data, 'host_id', '') or '')
    except Exception:
        return ''


def _get_sender_id(plugin_event) -> str:
    try:
        return _safe_str(getattr(plugin_event.data, 'user_id', ''))
    except Exception:
        return ''


def _get_sender_name(plugin_event) -> str:
    try:
        return _safe_str(plugin_event.data.sender.get('name', ''))
    except Exception:
        return ''


def _log(level: int, msg: str) -> None:
    proc = _g_proc
    full = f'[{config.plugin_name}] {msg}'
    if proc is not None and hasattr(proc, 'log'):
        try:
            proc.log(level, full, [])
            return
        except Exception:
            pass
    print(full)


def _reply(plugin_event, msg: str) -> Any:
    try:
        return plugin_event.reply(msg)
    except Exception:
        return None


def _is_qqguild_v2(plugin_event) -> bool:
    try:
        return plugin_event.platform.get('sdk') == 'qqGuildv2_link'
    except Exception:
        return False


def _get_pending_upload_key(plugin_event) -> tuple[str, str, str, str]:
    return (
        _get_bot_hash(plugin_event),
        _get_host_id(plugin_event),
        _get_group_id(plugin_event),
        _get_sender_id(plugin_event),
    )


def _is_master(plugin_event) -> bool:
    """检查发送者是否为骰主（使用OlivaDiceCore的masterList判定）。"""
    if not _has_oliva_dice_core:
        # 无OlivaDiceCore时无法判定身份，默认放行
        return True
    try:
        user_id = str(plugin_event.data.user_id)
        platform = plugin_event.platform['platform']
        bot_hash = _get_bot_hash(plugin_event)
        user_hash = OlivaDiceCore.userConfig.getUserHash(user_id, 'user', platform)
        return OlivaDiceCore.ordinaryInviteManager.isInMasterList(bot_hash, user_hash)
    except Exception as e:
        _log(3, f'骰主判定异常：{e}')
        return False


def _release_code(code: str | None, consume: bool = False) -> None:
    """释放授权码的进行中锁。consume=True 时同时从有效码中删除（即消耗）。"""
    if not code:
        return
    with _code_lock:
        _code_in_progress.discard(code)
        if consume:
            _code_store.pop(code, None)


def handle_init(plugin_event, Proc) -> None:
    global _g_proc
    _g_proc = Proc
    _log(2, '插件初始化完成')


def handle_save(plugin_event, Proc) -> None:
    _log(2, '收到 save 事件')


def handle_menu(plugin_event, Proc) -> None:
    """菜单事件：显示当前配置状态。"""
    plugin_cfg = _load_config()
    api_key_masked = plugin_cfg['api_key'][:8] + '****' if len(plugin_cfg['api_key']) > 8 else '未设置'
    thinking_status = '开' if plugin_cfg.get('thinking', True) else '关'
    output_mode = '合并转发' if plugin_cfg.get('output_mode') == 'forward' else '上传文件'
    info_lines = [
        '===== 跑团日志分析 设置面板 =====',
        f'API地址: {plugin_cfg["api_url"]}',
        f'API Key: {api_key_masked}',
        f'模型: {plugin_cfg["model"]}',
        f'思维链: {thinking_status}',
        f'输出: {output_mode}',
        f'文件格式: {plugin_cfg.get("output_format", "txt")}',
        '',
        '可用命令（群聊中发送）：',
        '.分析帮助              查看帮助',
        '.分析总结              列出群文件；qqGuildv2中等待下一条文件消息',
        '.分析总结 <文件名> (码) 分析指定log文件（非骰主需附授权码）',
        '.分析码                骰主生成一次性授权码',
        '.分析设置 api <URL>    设置Chat Completions地址',
        '.分析设置 key <key>    设置API Key',
        '.分析设置 model <名称> 设置模型名称',
        '.分析设置 thinking 开/关 切换思维链',
        '.分析设置 output 合并/文件 设置结果输出方式',
        '.分析设置 format txt/md 设置上传文件格式',
    ]
    try:
        plugin_event.reply('\n'.join(info_lines))
    except Exception:
        pass


def handle_group_message(plugin_event, Proc) -> None:
    global _g_proc
    _g_proc = Proc

    if _is_qqguild_v2(plugin_event) and _handle_pending_qqguild_upload(plugin_event):
        return

    raw_msg = _safe_str(getattr(plugin_event.data, 'message', ''))
    cmd, arg = _parse_command(raw_msg)

    if cmd not in (
        '分析帮助',
        '分析总结',
        '分析设置',
        '分析码',
        'analysishelp',
        'analysis',
        'analysisset',
        'analysiscode',
    ):
        return

    if cmd in ('分析帮助', 'analysishelp'):
        _cmd_help(plugin_event)
        return

    if cmd in ('分析设置', 'analysisset'):
        _cmd_set(plugin_event, arg)
        return

    if cmd in ('分析码', 'analysiscode'):
        _cmd_code(plugin_event)
        return

    if cmd in ('分析总结', 'analysis'):
        _cmd_summary(plugin_event, arg)
        return


def _cmd_help(plugin_event) -> None:
    help_text = (
        '===== 跑团日志分析 =====\n'
        '使用可配置的OpenAI兼容Chat Completions API分析跑团log。\n\n'
        '支持文件格式：\n'
        '  日志文件：.txt .log .md .json\n'
        '  压缩包：.zip（自动解压提取内部txt）\n'
        '  rar支持需安装：pip install rarfile\n\n'
        '  7z支持需安装：pip install py7zr\n\n'
        '命令列表：\n'
        '.分析帮助               查看本帮助\n'
        '.分析总结               列出群文件中的可用文件\n'
        '.分析总结 <文件名...>   分析指定的文件（骰主无需授权码）\n'
        '.分析总结 <文件名> <码> 非骰主凭授权码分析\n'
        '.分析码                 骰主生成一次性授权码\n'
        '.分析设置 api <URL>     设置完整的Chat Completions接口地址\n'
        '.分析设置 key <key>     设置API Key\n'
        '.分析设置 model <名称>  设置接口支持的模型名称\n'
        '.分析设置 thinking 开/关 切换思维链模式（默认开）\n'
        '.分析设置 output 合并/文件 设置合并转发或上传文件\n'
        '.分析设置 format txt/md 设置上传文件格式\n'
        '.分析设置 查看          查看当前配置\n\n'
        '权限说明：\n'
        '骰主可无限制使用 .分析总结\n'
        '其他人需要骰主通过 .分析码 生成的一次性授权码\n'
        '授权码在成功出结果后自动失效，出错不消耗\n\n'
        'OneBot使用步骤：\n'
        '1. 将跑团log文件（或zip压缩包）上传到本群群文件\n'
        '2. 骰主设置API地址、Key和模型\n'
        '3. 发送 .分析总结 列出文件\n'
        '4. 骰主：.分析总结 文件名\n'
        '   他人：.分析总结 文件名 授权码\n\n'
        'qqGuildv2使用步骤：\n'
        '1. 骰主发送 .分析总结；他人发送 .分析总结 授权码\n'
        '2. 同一用户的下一条消息发送一个受支持的日志文件或压缩包\n'
        '3. 下一条消息无有效文件时，本次等待结束，但授权码不会消耗\n\n'
        '分析结果包含：\n'
        '剧情梳理 | PC多维度评分 | 高光时刻 | 总体评价'
    )
    _reply(plugin_event, help_text)


def _cmd_code(plugin_event) -> None:
    """骰主生成一次性授权码，他人凭码使用 .分析总结。"""
    if not _is_master(plugin_event):
        _reply(plugin_event, '仅骰主可生成授权码')
        return
    code = uuid.uuid4().hex[:6]
    with _code_lock:
        _code_store[code] = True
    usage_text = f'.分析总结 {code}' if _is_qqguild_v2(plugin_event) else f'.分析总结 <文件名> {code}'
    _reply(
        plugin_event,
        f'已生成一次性授权码：{code}\n他人发送 {usage_text} 即可生成分析\n出结果后自动失效，出错不消耗',
    )


def _cmd_set(plugin_event, arg: str) -> None:
    if not _is_master(plugin_event):
        _reply(plugin_event, '仅骰主可修改日志分析设置')
        return

    parts = arg.split(None, 1)
    sub = parts[0].lower() if parts else ''
    val = parts[1] if len(parts) > 1 else ''

    plugin_cfg = _load_config()

    if sub in ('api', 'url', 'api_url'):
        api_url = val.strip()
        if not api_url.lower().startswith(('http://', 'https://')):
            _reply(plugin_event, '请提供完整的HTTP(S) Chat Completions地址')
            return
        plugin_cfg['api_url'] = api_url
        _save_config(plugin_cfg)
        _reply(plugin_event, f'API地址已设置为：{api_url}')
        return

    if sub == 'key':
        if not val:
            _reply(plugin_event, '请提供API Key，例如：.分析设置 key sk-xxxx')
            return
        plugin_cfg['api_key'] = val.strip()
        _save_config(plugin_cfg)
        _reply(plugin_event, 'API Key 已保存')
        return

    if sub == 'model':
        if not val:
            _reply(plugin_event, f'请提供模型名称，当前：{plugin_cfg["model"]}')
            return
        plugin_cfg['model'] = val.strip()
        _save_config(plugin_cfg)
        _reply(plugin_event, f'模型已设置为：{plugin_cfg["model"]}')
        return

    if sub == 'thinking':
        if val in ('开', 'on', '1', 'true'):
            plugin_cfg['thinking'] = True
        elif val in ('关', 'off', '0', 'false'):
            plugin_cfg['thinking'] = False
        else:
            current = '开' if plugin_cfg.get('thinking', True) else '关'
            _reply(plugin_event, f'思维链模式当前为：{current}\n请用 .分析设置 thinking 开 或 .分析设置 thinking 关')
            return
        _save_config(plugin_cfg)
        status = '开' if plugin_cfg['thinking'] else '关'
        _reply(plugin_event, f'思维链模式已{status}')
        return

    if sub in ('output', '输出'):
        output_value = val.strip().lower()
        if output_value in ('合并', '转发', '合并转发', 'forward'):
            plugin_cfg['output_mode'] = 'forward'
        elif output_value in ('文件', '上传', '上传文件', 'file'):
            plugin_cfg['output_mode'] = 'file'
        else:
            _reply(plugin_event, '请用 .分析设置 output 合并 或 .分析设置 output 文件')
            return
        _save_config(plugin_cfg)
        output_text = '合并转发' if plugin_cfg['output_mode'] == 'forward' else '上传文件'
        _reply(plugin_event, f'结果输出方式已设置为：{output_text}')
        return

    if sub in ('format', '格式'):
        output_format = val.strip().lower().lstrip('.')
        if output_format not in ('txt', 'md'):
            _reply(plugin_event, '请用 .分析设置 format txt 或 .分析设置 format md')
            return
        plugin_cfg['output_format'] = output_format
        _save_config(plugin_cfg)
        _reply(plugin_event, f'上传文件格式已设置为：{output_format}')
        return

    if sub == '查看' or sub == '':
        api_key_masked = plugin_cfg['api_key'][:8] + '****' if len(plugin_cfg['api_key']) > 8 else '未设置'
        thinking_status = '开' if plugin_cfg.get('thinking', True) else '关'
        output_mode = '合并转发' if plugin_cfg.get('output_mode') == 'forward' else '上传文件'
        _reply(
            plugin_event,
            f'当前配置：\nAPI地址: {plugin_cfg["api_url"]}\nAPI Key: {api_key_masked}\n'
            f'模型: {plugin_cfg["model"]}\n思维链: {thinking_status}\n'
            f'输出: {output_mode}\n文件格式: {plugin_cfg.get("output_format", "txt")}',
        )
        return

    _reply(plugin_event, '支持的设置项：api / key / model / thinking / output / format / 查看')


def _collect_group_files(plugin_event, group_id, folder_id=None, depth=0, max_depth=3):
    """递归收集群文件（含子文件夹），返回原始文件dict列表。"""
    if depth > max_depth:
        return []
    try:
        if folder_id is None:
            result = plugin_event.get_group_root_files(group_id)
        else:
            result = plugin_event.get_group_files_by_folder(group_id, folder_id)
    except Exception:
        return []

    if not result:
        return []
    # RES 是 dict 子类，active/data 可能是键也可能是属性
    active = getattr(result, 'active', None)
    if active is None and isinstance(result, dict):
        active = result.get('active', True)
    if not active:
        return []

    data_block = getattr(result, 'data', None)
    if data_block is None and isinstance(result, dict):
        data_block = result.get('data', result)
    if not isinstance(data_block, dict):
        return []

    file_list = data_block.get('files', [])
    folder_list = data_block.get('folders', [])

    collected = []
    for f in file_list:
        if isinstance(f, dict):
            collected.append(f)

    for folder in folder_list:
        if isinstance(folder, dict):
            fid = _safe_str(folder.get('folder_id', folder.get('id', '')))
            if fid:
                collected.extend(_collect_group_files(plugin_event, group_id, fid, depth + 1, max_depth))

    return collected


# ===== 分块分析（超长日志轮询+合并） =====
CHUNK_CHARS = config.MAX_LOG_CHARS
CHUNK_SYSTEM_PROMPT = (
    '你是一个专业的TRPG跑团日志分析助手。\n'
    '以下是跑团日志的第{part}部分，共{total}部分。\n'
    '请分析这部分日志内容，提取所有重要信息：剧情进展、角色行动、战斗场景、对话互动等。\n'
    '尽可能详细地记录你在这部分看到的所有内容，不要遗漏任何角色或事件。\n'
    '直接以段落形式输出你的发现，不需要排版格式。'
)


def _split_log(text: str, chunk_size: int = CHUNK_CHARS) -> list[str]:
    """将日志按 chunk_size 分块，尽量在换行处断开。"""
    if len(text) <= chunk_size:
        return [text]
    chunks = []
    start = 0
    while start < len(text):
        end = min(start + chunk_size, len(text))
        if end < len(text):
            # 在范围内找最后一个换行
            nl = text.rfind('\n', start, end)
            if nl > start + chunk_size // 3:
                end = nl + 1
        chunks.append(text[start:end])
        start = end
    return chunks


def _post_chat(plugin_cfg: dict[str, Any], messages: list[dict[str, str]], max_tokens: int) -> str:
    """调用可配置的OpenAI兼容Chat Completions接口。"""
    headers = {
        'Authorization': f'Bearer {plugin_cfg["api_key"]}',
        'Content-Type': 'application/json',
    }
    payload: dict[str, Any] = {
        'model': plugin_cfg['model'],
        'messages': messages,
        'max_tokens': max_tokens,
        'temperature': 0.7,
    }
    if plugin_cfg.get('thinking', True):
        payload['thinking'] = {'type': 'enabled'}
        payload['reasoning_effort'] = 'medium'

    last_error: Exception | None = None
    thinking_fallback_used = False
    for attempt in range(config.API_RETRIES + 1):
        try:
            response = requests.post(
                plugin_cfg['api_url'],
                headers=headers,
                json=payload,
                timeout=config.API_TIMEOUT,
            )
        except Exception as exception_object:
            last_error = exception_object
        else:
            if response.status_code == 200:
                try:
                    data = response.json()
                except Exception as exception_object:
                    raise RuntimeError(f'API返回的JSON无法解析：{exception_object}') from exception_object
                choices = data.get('choices', [])
                if not choices:
                    raise RuntimeError('API返回中没有choices')
                content = choices[0].get('message', {}).get('content') or ''
                return _safe_str(content)

            if response.status_code in (400, 422) and 'thinking' in payload and not thinking_fallback_used:
                payload.pop('thinking', None)
                payload.pop('reasoning_effort', None)
                thinking_fallback_used = True
                _log(2, '当前API不接受思维链扩展参数，已自动关闭扩展参数并重试。')
                continue

            error_detail = _safe_str(response.text)[:500]
            current_error = RuntimeError(f'HTTP {response.status_code}: {error_detail}')
            if response.status_code in (400, 401, 402, 403, 404, 422):
                raise current_error
            last_error = current_error

        if attempt < config.API_RETRIES:
            time.sleep(config.API_RETRY_WAIT_SECONDS)

    raise RuntimeError(f'API调用失败：{last_error}')


def _call_api_chunked(
    plugin_cfg: dict[str, Any],
    full_log: str,
    summary_prompt: str,
    plugin_event=None,
    depth: int = 0,
) -> str:
    """超长日志：递归分块分析 → 合并综合。

    当合并后的中间结果仍超过 MAX_LOG_CHARS 时递归再做一级拆分，
    最多递归 3 层防止无限循环。
    """
    MAX_DEPTH = 3
    if depth > MAX_DEPTH:
        _log(2, f'分块递归达到最大深度 {MAX_DEPTH}，返回截断结果')
        return full_log[:5000] + '\n\n…（递归层数超限，返回原始分析片段）'

    chunks = _split_log(full_log)
    total = len(chunks)
    # 第一阶段：逐块分析
    part_results = []
    for i, chunk in enumerate(chunks):
        if plugin_event:
            _reply(plugin_event, f'正在分析第 {i + 1}/{total} 部分（{len(chunk)} 字符）...')
        messages = [
            {'role': 'system', 'content': CHUNK_SYSTEM_PROMPT.format(part=i + 1, total=total)},
            {'role': 'user', 'content': f'请分析以下日志内容：\n\n{chunk}'},
        ]
        try:
            content = _post_chat(plugin_cfg, messages, config.CHUNK_API_TOKENS)
        except Exception as exception_object:
            raise RuntimeError(f'第{i + 1}部分分析失败：{exception_object}') from exception_object
        part_results.append(content)

    # 检查中间结果长度，决定是否需要递归
    combined = '\n\n---\n\n'.join([f'第{i + 1}部分分析结果：\n{text}' for i, text in enumerate(part_results)])

    if len(combined) > config.MAX_LOG_CHARS:
        if plugin_event:
            _reply(plugin_event, f'中间分析结果 {len(combined)} 字符仍然过长，进入第 {depth + 2} 轮递归拆分...')
        return _call_api_chunked(plugin_cfg, combined, summary_prompt, plugin_event, depth + 1)

    # 第二阶段：合并综合
    if plugin_event:
        _reply(plugin_event, f'正在合并 {total} 部分分析结果，生成最终总结...')
    try:
        final = _post_chat(
            plugin_cfg,
            [
                {'role': 'system', 'content': summary_prompt},
                {
                    'role': 'user',
                    'content': f'以下是跑团日志各部分的初步分析结果，请合并为一份完整流畅的总结报告：\n\n{combined}',
                },
            ],
            config.MAX_API_TOKENS,
        )
    except Exception as exception_object:
        raise RuntimeError(f'合并分析结果失败：{exception_object}') from exception_object

    return final


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _claim_code(code: str) -> str | None:
    """占用一次性码；返回错误文本，成功返回None。"""
    with _code_lock:
        if code not in _code_store:
            return '授权码无效或已过期'
        if code in _code_in_progress:
            return '该授权码正在使用中，请稍候再试'
        _code_in_progress.add(code)
    return None


def _cmd_summary_qqguild(plugin_event, arg: str, plugin_cfg: dict[str, Any]) -> None:
    """qqGuildv2不读取群文件，等待当前用户的下一条文件消息。"""
    used_code = None
    if not _is_master(plugin_event):
        code_parts = arg.strip().split()
        if len(code_parts) != 1:
            _reply(plugin_event, 'qqGuildv2中请使用：.分析总结 <授权码>\n骰主可通过 .分析码 生成授权码')
            return
        used_code = code_parts[0]
        code_error = _claim_code(used_code)
        if code_error:
            _reply(plugin_event, code_error)
            return

    pending_key = _get_pending_upload_key(plugin_event)
    previous_code = None
    with _code_lock:
        previous = _pending_qqguild_uploads.pop(pending_key, None)
        if previous:
            previous_code = previous.get('code')
            if previous_code and previous_code != used_code:
                _code_in_progress.discard(previous_code)
        _pending_qqguild_uploads[pending_key] = {'code': used_code}

    if previous_code and previous_code != used_code:
        _log(2, f'qqGuildv2用户重新获取文件输入，已释放旧授权码：{previous_code}')

    output_mode = _get_effective_output_mode(plugin_event, plugin_cfg)
    output_note = '文件' if output_mode == 'file' else '合并转发'
    _reply(
        plugin_event,
        '请在下一条消息中发送要分析的日志文件或压缩包。\n'
        '支持：.txt .log .md .json .zip .rar .7z\n'
        f'分析结果将以{output_note}输出。下一条消息无有效文件时需重新发送本命令，授权码不会消耗。',
    )


def _build_received_file(file_data: dict[str, Any]) -> dict[str, Any] | None:
    resource = ''
    for key in ('url', 'file', 'path'):
        value = _safe_str(file_data.get(key, '')).strip()
        if value and value != 'None':
            resource = value
            break
    if not resource:
        return None
    if resource.startswith('//'):
        resource = 'https:' + resource

    file_name = _safe_str(file_data.get('name', '')).strip()
    resource_parsed = parse.urlparse(resource)
    if not file_name:
        query = parse.parse_qs(resource_parsed.query)
        file_name = _safe_str((query.get('fname') or query.get('name') or [''])[0]).strip()
    if not file_name:
        file_name = parse.unquote(resource_parsed.path).replace('\\', '/').rsplit('/', 1)[-1]
    file_name = parse.unquote(file_name)

    return {
        'file_name': file_name,
        'file_size': _safe_int(file_data.get('size', 0)),
        'url': resource,
    }


def _extract_file_segments_from_message(message_object) -> list[dict[str, Any]]:
    results = []
    message_data = getattr(message_object, 'data', None)
    if not isinstance(message_data, list):
        return results
    for segment in message_data:
        if getattr(segment, 'type', None) != 'file' or not isinstance(getattr(segment, 'data', None), dict):
            continue
        file_info = _build_received_file(segment.data)
        if file_info:
            results.append(file_info)
    return results


def _extract_qqguild_files(plugin_event) -> list[dict[str, Any]]:
    """优先读取框架结构化消息段，原始附件和OP字符串仅作兼容兜底。"""
    results = []
    data_object = getattr(plugin_event, 'data', None)
    for attribute_name in ('message_sdk', 'raw_message_sdk', 'raw_message'):
        results.extend(_extract_file_segments_from_message(getattr(data_object, attribute_name, None)))
        if results:
            break

    if not results:
        extend_data = getattr(data_object, 'extend', {})
        attachments = extend_data.get('qq_attachments', []) if isinstance(extend_data, dict) else []
        for attachment in attachments:
            if not isinstance(attachment, dict):
                continue
            file_info = _build_received_file({
                'url': attachment.get('url', attachment.get('voice_wav_url')),
                'name': attachment.get('filename'),
                'size': attachment.get('size'),
            })
            if file_info:
                results.append(file_info)

    raw_message = _safe_str(getattr(data_object, 'message', ''))
    if not results and raw_message:
        try:
            import OlivOS

            parsed_message = OlivOS.messageAPI.Message_templet('olivos_string', raw_message)
            results.extend(_extract_file_segments_from_message(parsed_message))
        except Exception:
            pass

    if not results and raw_message:
        for matched in re.finditer(r'\[OP:file,(?P<data>[^\]]+)\]', raw_message):
            file_data = {}
            for item in re.split(r',(?=[A-Za-z_][A-Za-z0-9_]*=)', matched.group('data')):
                key, separator, value = item.partition('=')
                if separator:
                    file_data[key] = value
            file_info = _build_received_file(file_data)
            if file_info:
                results.append(file_info)

    unique_results = []
    seen = set()
    for file_info in results:
        unique_key = (file_info['url'], file_info['file_name'])
        if unique_key not in seen:
            seen.add(unique_key)
            unique_results.append(file_info)
    return unique_results


def _validate_received_files(file_list: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], str | None]:
    if not file_list:
        return [], '下一条消息中没有识别到文件'

    validated = []
    for file_info in file_list:
        file_name = file_info['file_name']
        file_name_lower = file_name.lower()
        is_archive = file_name_lower.endswith(config.ARCHIVE_EXTENSIONS)
        is_log = file_name_lower.endswith(config.LOG_FILE_EXTENSIONS)
        if not file_name or not (is_archive or is_log):
            return [], f'不支持的文件格式：{file_name or "未知文件"}'
        if parse.urlparse(file_info['url']).scheme not in ('http', 'https'):
            return [], f'文件缺少可下载的HTTP(S)地址：{file_name}'
        if file_info['file_size'] > config.MAX_FILE_SIZE_BYTES:
            limit_mb = config.MAX_FILE_SIZE_BYTES / 1024 / 1024
            return [], f'文件过大：{file_name}（上限{limit_mb:.0f}MB）'
        validated.append({**file_info, 'is_archive': is_archive})
    return validated, None


def _handle_pending_qqguild_upload(plugin_event) -> bool:
    pending_key = _get_pending_upload_key(plugin_event)
    with _code_lock:
        pending = _pending_qqguild_uploads.pop(pending_key, None)
    if pending is None:
        return False

    used_code = pending.get('code')
    file_list, error_text = _validate_received_files(_extract_qqguild_files(plugin_event))
    if error_text:
        _release_code(used_code)
        _reply(
            plugin_event,
            f'{error_text}。本次文件输入已结束，授权码未消耗。\n请重新发送 .分析总结（非骰主附授权码）后再发送文件。',
        )
        return True

    _analyze_remote_files(plugin_event, _get_group_id(plugin_event), file_list, used_code, _load_config())
    return True


def _cmd_summary(plugin_event, arg: str) -> None:
    plugin_cfg = _load_config()
    if not plugin_cfg['api_key']:
        _reply(plugin_event, '请先由骰主设置API Key：\n.分析设置 key <API Key>')
        return

    group_id = _get_group_id(plugin_event)
    if not group_id:
        _reply(plugin_event, '请在群聊中使用此命令')
        return

    if _is_qqguild_v2(plugin_event):
        _cmd_summary_qqguild(plugin_event, arg, plugin_cfg)
        return

    is_master = _is_master(plugin_event)
    used_code = None
    parts = arg.strip().split() if arg.strip() else []

    if not is_master and parts:
        used_code = parts[-1]
        parts = parts[:-1]
        if not parts:
            _reply(plugin_event, '请指定要分析的文件名\n格式：.分析总结 <文件名> <授权码>')
            return
        code_error = _claim_code(used_code)
        if code_error:
            _reply(plugin_event, code_error)
            return

    target_files = parts
    _reply(plugin_event, '正在读取群文件列表...')
    file_list = _collect_group_files(plugin_event, group_id)

    log_files = []
    for file_info in file_list:
        if not isinstance(file_info, dict):
            continue
        file_name = _safe_str(file_info.get('file_name', file_info.get('name', '')))
        file_name_lower = file_name.lower()
        is_archive = file_name_lower.endswith(config.ARCHIVE_EXTENSIONS)
        if is_archive or file_name_lower.endswith(config.LOG_FILE_EXTENSIONS):
            log_files.append({
                'file_id': _safe_str(file_info.get('file_id', file_info.get('id', ''))),
                'file_name': file_name,
                'busid': file_info.get('busid', 102),
                'file_size': _safe_int(file_info.get('file_size', file_info.get('size', 0))),
                'is_archive': is_archive,
            })

    if not log_files:
        _reply(plugin_event, '未在群文件中找到日志文件或压缩包\n支持：.txt .log .md .json .zip .rar .7z')
        _release_code(used_code)
        return

    if not target_files:
        file_lines = ['群文件中找到以下文件（发送 .分析总结 文件名 来分析）：', '——日志文件——']
        log_only = [file_info for file_info in log_files if not file_info['is_archive']]
        archive_only = [file_info for file_info in log_files if file_info['is_archive']]
        index = 1
        for file_info in log_only:
            file_lines.append(f'{index}. {file_info["file_name"]} ({file_info["file_size"] / 1024:.1f}KB)')
            index += 1
        if archive_only:
            file_lines.append('——压缩包（自动解压提取内部文本）——')
            for file_info in archive_only:
                file_lines.append(f'{index}. {file_info["file_name"]} ({file_info["file_size"] / 1024:.1f}KB)')
                index += 1
        _reply(plugin_event, '\n'.join(file_lines))
        return

    matched_files = []
    for target in target_files:
        target_lower = target.lower()
        found = next(
            (
                file_info
                for file_info in log_files
                if file_info['file_name'].lower() == target_lower
                or file_info['file_name'].lower().startswith(target_lower)
            ),
            None,
        )
        if found is None:
            found = next(
                (file_info for file_info in log_files if target_lower in file_info['file_name'].lower()),
                None,
            )
        if found and found not in matched_files:
            matched_files.append(found)
        elif found is None:
            _reply(plugin_event, f'未找到文件：{target}')
            _release_code(used_code)
            return

    for file_info in matched_files:
        try:
            url_result = plugin_event.get_group_file_url(group_id, file_info['file_id'], file_info['busid'])
        except Exception as exception_object:
            _reply(plugin_event, f'获取 {file_info["file_name"]} 下载链接失败：{exception_object}')
            _release_code(used_code)
            return

        if hasattr(url_result, 'data'):
            file_info['url'] = _safe_str(url_result.data.get('url', ''))
        elif isinstance(url_result, dict):
            result_data = url_result.get('data', {})
            file_info['url'] = _safe_str(
                result_data.get('url', '') if isinstance(result_data, dict) else url_result.get('url', '')
            )
        if not file_info.get('url'):
            _reply(plugin_event, f'无法获取 {file_info["file_name"]} 的下载链接')
            _release_code(used_code)
            return

    _analyze_remote_files(plugin_event, group_id, matched_files, used_code, plugin_cfg)


def _download_remote_file(file_info: dict[str, Any]) -> bytes:
    declared_size = _safe_int(file_info.get('file_size', 0))
    if declared_size > config.MAX_FILE_SIZE_BYTES:
        raise RuntimeError(f'文件大小超过{config.MAX_FILE_SIZE_BYTES // 1024 // 1024}MB限制')

    response = requests.get(file_info['url'], timeout=60, stream=True)
    try:
        if response.status_code >= 400:
            raise RuntimeError(f'HTTP {response.status_code}: {_safe_str(response.text)[:200]}')
        content_length = _safe_int(response.headers.get('Content-Length', 0))
        if content_length > config.MAX_FILE_SIZE_BYTES:
            raise RuntimeError(f'文件大小超过{config.MAX_FILE_SIZE_BYTES // 1024 // 1024}MB限制')

        chunks = []
        total_size = 0
        for chunk in response.iter_content(chunk_size=64 * 1024):
            if not chunk:
                continue
            total_size += len(chunk)
            if total_size > config.MAX_FILE_SIZE_BYTES:
                raise RuntimeError(f'文件大小超过{config.MAX_FILE_SIZE_BYTES // 1024 // 1024}MB限制')
            chunks.append(chunk)
        return b''.join(chunks)
    finally:
        response.close()


def _decode_file_content(raw_bytes: bytes) -> str:
    for encoding_name in config.ENCODING_CANDIDATES:
        try:
            return raw_bytes.decode(encoding_name)
        except (UnicodeDecodeError, LookupError):
            continue
    return raw_bytes.decode('utf-8', errors='replace')


def _analyze_remote_files(
    plugin_event,
    group_id: str,
    file_list: list[dict[str, Any]],
    used_code: str | None,
    plugin_cfg: dict[str, Any],
) -> None:
    all_content_parts = []
    for file_info in file_list:
        file_name = file_info['file_name']
        _reply(plugin_event, f'正在下载：{file_name} ...')
        try:
            raw_bytes = _download_remote_file(file_info)
            if file_info['is_archive']:
                _reply(plugin_event, f'正在解压：{file_name} ...')
                extracted = _extract_archive(file_name, raw_bytes)
                if not extracted:
                    raise RuntimeError('压缩包中未找到可读文本文件')
                all_content_parts.extend(
                    f'=== {file_name} / {entry_name} ===\n{entry_content}' for entry_name, entry_content in extracted
                )
            else:
                all_content_parts.append(f'=== {file_name} ===\n{_decode_file_content(raw_bytes)}')
        except Exception as exception_object:
            _reply(plugin_event, f'处理 {file_name} 失败：{exception_object}')
            _release_code(used_code)
            return

    full_log = '\n\n'.join(all_content_parts)
    summary_prompt = _get_summary_prompt(plugin_event, plugin_cfg)
    try:
        if len(full_log) > config.MAX_LOG_CHARS:
            _reply(plugin_event, f'日志总长度 {len(full_log)} 字符超过限制，将分块分析后合并...')
            analysis_text = _call_api_chunked(
                plugin_cfg,
                full_log,
                summary_prompt,
                plugin_event=plugin_event,
            )
        else:
            _reply(plugin_event, f'已读取 {len(file_list)} 个文件，正在调用AI接口分析...')
            analysis_text = _call_api(plugin_cfg, full_log, summary_prompt)
    except Exception as exception_object:
        _reply(plugin_event, f'API调用失败：{exception_object}')
        _log(3, f'API调用异常：{traceback.format_exc()}')
        _release_code(used_code)
        return

    if not analysis_text.strip():
        _reply(plugin_event, '分析结果为空，请检查日志内容或API设置')
        _release_code(used_code)
        return

    try:
        _send_summary_output(
            plugin_event,
            group_id,
            analysis_text,
            [file_info['file_name'] for file_info in file_list],
            plugin_cfg,
        )
    except Exception:
        _reply(plugin_event, f'发送结果失败，回退为普通文本：\n{analysis_text[:1000]}')
        _log(3, f'分析结果发送异常：{traceback.format_exc()}')

    _release_code(used_code, consume=True)


def _extract_archive(filename: str, raw_bytes: bytes) -> list:
    results = []
    fname_lower = filename.lower()

    if fname_lower.endswith('.zip'):
        with zipfile.ZipFile(io.BytesIO(raw_bytes)) as zf:
            entries = [
                entry_info
                for entry_info in zf.infolist()
                if not entry_info.is_dir()
                and entry_info.file_size <= config.MAX_FILE_SIZE_BYTES
                and entry_info.filename.lower().endswith(config.ARCHIVE_LOG_EXTENSIONS)
            ][: config.MAX_EXTRACT_FILES]
            for entry_info in entries:
                try:
                    entry_bytes = zf.read(entry_info)
                except Exception:
                    continue
                content = _decode_file_content(entry_bytes)
                if content.strip():
                    results.append((entry_info.filename, content))
        return results

    if fname_lower.endswith('.rar') and _has_rarfile:
        with rarfile.RarFile(io.BytesIO(raw_bytes)) as rf:
            entries = [entry for entry in rf.namelist() if entry.lower().endswith(config.ARCHIVE_LOG_EXTENSIONS)]
            entries = entries[: config.MAX_EXTRACT_FILES]
            for entry in entries:
                try:
                    entry_bytes = rf.read(entry)
                except Exception:
                    continue
                if len(entry_bytes) > config.MAX_FILE_SIZE_BYTES:
                    continue
                content = _decode_file_content(entry_bytes)
                if content.strip():
                    results.append((entry, content))
        return results

    if fname_lower.endswith('.rar') and not _has_rarfile:
        raise RuntimeError('不支持rar格式，请安装rarfile库：pip install rarfile\n或改用zip格式上传')

    if fname_lower.endswith('.7z') and _has_py7zr:
        with py7zr.SevenZipFile(io.BytesIO(raw_bytes)) as seven_zip_file:
            extracted_data = seven_zip_file.readall() or {}
            entries = [
                (entry_name, entry_buffer)
                for entry_name, entry_buffer in extracted_data.items()
                if entry_name.lower().endswith(config.ARCHIVE_LOG_EXTENSIONS)
            ][: config.MAX_EXTRACT_FILES]
            for entry_name, entry_buffer in entries:
                entry_bytes = entry_buffer.read(config.MAX_FILE_SIZE_BYTES + 1)
                if len(entry_bytes) > config.MAX_FILE_SIZE_BYTES:
                    continue
                content = _decode_file_content(entry_bytes)
                if content.strip():
                    results.append((entry_name, content))
        return results

    if fname_lower.endswith('.7z') and not _has_py7zr:
        raise RuntimeError('不支持7z格式，请安装py7zr库：pip install py7zr\n或改用zip格式上传')

    raise RuntimeError(f'不支持的压缩格式：{filename}')


def _get_effective_output_mode(plugin_event, plugin_cfg: dict[str, Any]) -> str:
    output_mode = plugin_cfg.get('output_mode', config.DEFAULT_OUTPUT_MODE)
    if output_mode not in ('forward', 'file'):
        output_mode = config.DEFAULT_OUTPUT_MODE
    if output_mode == 'forward' and _is_qqguild_v2(plugin_event):
        return 'file'
    return output_mode


def _get_summary_prompt(plugin_event, plugin_cfg: dict[str, Any]) -> str:
    output_format = plugin_cfg.get('output_format', config.DEFAULT_OUTPUT_FORMAT)
    if _get_effective_output_mode(plugin_event, plugin_cfg) == 'file' and output_format == 'md':
        return config.SUMMARY_SYSTEM_PROMPT_MARKDOWN
    return config.SUMMARY_SYSTEM_PROMPT_TEXT


def _call_api(plugin_cfg: dict[str, Any], log_content: str, summary_prompt: str) -> str:
    return _post_chat(
        plugin_cfg,
        [
            {'role': 'system', 'content': summary_prompt},
            {'role': 'user', 'content': f'请分析以下跑团日志：\n\n{log_content}'},
        ],
        config.MAX_API_TOKENS,
    )


def _render_file_summary(
    analysis_text: str,
    source_names: list[str],
    plugin_cfg: dict[str, Any],
) -> str:
    generated_time = time.strftime('%Y-%m-%d %H:%M:%S')
    thinking_text = '开' if plugin_cfg.get('thinking', True) else '关'
    source_text = '、'.join(source_names)
    body = analysis_text.strip()

    if plugin_cfg.get('output_format') == 'md':
        header = (
            '# 跑团日志分析总结\n\n'
            f'> 源文件：{source_text}  \n'
            f'> 模型：{plugin_cfg["model"]}（思维链：{thinking_text}）  \n'
            f'> 生成时间：{generated_time}\n\n'
            '---\n\n'
        )
        return header + body + '\n'

    body = re.sub(
        r'^##\s+(.+?)\s*$',
        lambda matched: f'============== {matched.group(1).strip()} ==============',
        body,
        flags=re.MULTILINE,
    )
    header = (
        '跑团日志分析总结\n'
        f'源文件：{source_text}\n'
        f'模型：{plugin_cfg["model"]}（思维链：{thinking_text}）\n'
        f'生成时间：{generated_time}\n'
        '----------------------------------------\n\n'
    )
    return header + body + '\n'


def _write_summary_file(
    analysis_text: str,
    source_names: list[str],
    plugin_cfg: dict[str, Any],
) -> str:
    output_format = plugin_cfg.get('output_format', config.DEFAULT_OUTPUT_FORMAT)
    if output_format not in ('txt', 'md'):
        output_format = config.DEFAULT_OUTPUT_FORMAT
    result_dir = os.path.join(_g_data_dir, 'results')
    os.makedirs(result_dir, exist_ok=True)
    file_name = f'跑团日志分析_{time.strftime("%Y%m%d_%H%M%S")}_{uuid.uuid4().hex[:6]}.{output_format}'
    file_path = os.path.abspath(os.path.join(result_dir, file_name))
    output_text = _render_file_summary(analysis_text, source_names, {**plugin_cfg, 'output_format': output_format})
    encoding_name = 'utf-8-sig' if output_format == 'txt' else 'utf-8'
    with open(file_path, 'w', encoding=encoding_name, newline='\n') as file_object:
        file_object.write(output_text)
    return file_path


def _send_file_summary(plugin_event, file_path: str) -> Any:
    file_name = os.path.basename(file_path)
    try:
        import OlivOS

        message_object = OlivOS.messageAPI.Message_templet(
            'olivos_para',
            [OlivOS.messageAPI.PARA.file(file=file_path, path=file_path, name=file_name)],
        )
        return plugin_event.reply(message_object)
    except ImportError:
        return plugin_event.reply(f'[OP:file,path={file_path},name={file_name}]')


def _send_summary_output(
    plugin_event,
    group_id: str,
    analysis_text: str,
    source_names: list[str],
    plugin_cfg: dict[str, Any],
) -> None:
    effective_mode = _get_effective_output_mode(plugin_event, plugin_cfg)
    if effective_mode == 'forward':
        _send_forward_summary(plugin_event, group_id, analysis_text)
        return

    if plugin_cfg.get('output_mode') == 'forward' and _is_qqguild_v2(plugin_event):
        _reply(plugin_event, 'qqGuildv2不支持合并转发，本次自动改为上传文件。')
    file_path = _write_summary_file(analysis_text, source_names, plugin_cfg)
    _send_file_summary(plugin_event, file_path)


def _send_forward_summary(plugin_event, group_id: str, analysis_text: str) -> None:
    sections = _split_sections(analysis_text)
    bot_name = _get_bot_display_name(plugin_event)
    bot_uin = int(_get_bot_id(plugin_event)) if _get_bot_id(plugin_event).isdigit() else 10000

    if not sections:
        _reply(plugin_event, analysis_text[:500])
        return

    messages = []
    for section_title, section_content in sections:
        if not section_content.strip():
            continue
        formatted = f'{section_title}\n{section_content.strip()}'
        messages.append({
            'type': 'node',
            'data': {
                'name': bot_name,
                'uin': bot_uin,
                'content': formatted,
            },
        })

    if not messages:
        _reply(plugin_event, analysis_text[:500])
        return

    try:
        plugin_event.send_group_forward_msg(group_id, messages)
    except Exception:
        plugin_event.send_group_forward_msg(group_id, messages[:1])
        raise


def _split_sections(text: str) -> list:
    pattern = re.compile(r'^##\s+(.+)$', re.MULTILINE)
    matches = list(pattern.finditer(text))

    if not matches:
        return [('## 分析结果', text)]

    sections = []
    for i, match in enumerate(matches):
        title = match.group(1).strip()
        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        content = text[start:end].strip()
        sections.append((f'## {title}', content))

    return sections

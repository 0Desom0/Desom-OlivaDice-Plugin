# -*- encoding: utf-8 -*-
"""
OlivaAIAgent WebUI 配置与状态接口。
动态内省 DEFAULT_CONF 与 gui 模块元数据，通过 OlivOS WebUI 消息桥提供沙箱配置。
"""

import copy
import json
import os
import threading

import OlivaAIAgent

WEBUI_EVENT = 'OlivaAIAgent_WebUI_Config'
PLUGIN_NAME = 'OlivaAIAgent'

_dispatch_lock = threading.RLock()


def _getNested(root, path, default=None):
    node = root
    for key in path:
        if not isinstance(node, dict) or key not in node:
            return default
        node = node[key]
    return node


def _parse_field_value(raw_val, template, path):
    """安全解析前端传入的字段值，支持直接传入 dict/list 或字符串 JSON。"""
    if path == ('vision', 'use_main') or path == ('media', 'use_main'):
        text = str(raw_val).strip().lower()
        if text == 'true':
            return True
        if text == 'false':
            return False
        return 'auto'
    if isinstance(template, bool):
        return bool(raw_val)
    if isinstance(template, int) and not isinstance(template, bool):
        return int(str(raw_val).strip())
    if isinstance(template, float):
        return float(str(raw_val).strip())
    if isinstance(template, (list, dict)):
        if isinstance(raw_val, (list, dict)):
            return raw_val
        if isinstance(raw_val, str):
            result = json.loads(raw_val.strip() or ('[]' if isinstance(template, list) else '{}'))
            if isinstance(template, list) and not isinstance(result, list):
                raise ValueError('必须填写 JSON 数组')
            if isinstance(template, dict) and not isinstance(result, dict):
                raise ValueError('必须填写 JSON 对象')
            return result
        raise ValueError('必须为有效的列表或对象')
    return str(raw_val)


def _buildSectionSchema(section_key):
    """提取指定分类的表单元数据（标签、类型、枚举值、说明等）。"""
    gui = OlivaAIAgent.gui
    conf = OlivaAIAgent.conf

    if section_key == 'general':
        base_path = ()
        section_data = {
            '_说明': conf.DEFAULT_CONF.get('_说明', ''),
            'backend': conf.DEFAULT_CONF.get('backend', 'openai'),
            'debug_log': conf.DEFAULT_CONF.get('debug_log', False),
        }
    elif section_key in gui.VIRTUAL_SECTION_PATHS:
        base_path = gui.VIRTUAL_SECTION_PATHS[section_key]
        section_data = _getNested(conf.DEFAULT_CONF, base_path, {})
    else:
        base_path = (section_key,)
        section_data = conf.DEFAULT_CONF.get(section_key, {})
        if section_key == 'trigger' and isinstance(section_data, dict):
            section_data = {
                k: v for k, v in section_data.items()
                if k not in {'prefix', 'keywords', '_keywords说明'}
            }
        elif section_key == 'ambient' and isinstance(section_data, dict):
            section_data = {
                k: v for k, v in section_data.items()
                if k not in {'enable_default', 'intent_api'}
            }

    if not isinstance(section_data, dict):
        return {'description': '', 'fields': []}

    description = str(section_data.get('_说明', '') or '').strip()
    fields = []

    def walk(data, current_path):
        if not isinstance(data, dict):
            return
        hints, _notes = gui.collectFieldHints(data)
        for key, value in data.items():
            if str(key).startswith('_'):
                continue
            path = current_path + (key,)
            if isinstance(value, dict) and key not in gui.JSON_OBJECT_NAMES:
                walk(value, path)
                continue

            enum_values = list(gui.ENUM_VALUES.get(path, ()))
            if path[-2:] == ('thinking', 'type'):
                enum_values = ['disabled', 'enabled']
            elif path == ('vision', 'use_main') or path == ('media', 'use_main'):
                enum_values = ['auto', 'true', 'false']

            if enum_values:
                field_type = 'enum'
            elif isinstance(value, bool):
                field_type = 'bool'
            elif isinstance(value, int):
                field_type = 'int'
            elif isinstance(value, float):
                field_type = 'float'
            elif isinstance(value, list):
                field_type = 'json_list'
            elif isinstance(value, dict):
                field_type = 'json_dict'
            elif isinstance(value, str) and len(value) > 100:
                field_type = 'text'
            else:
                field_type = 'string'

            hint = hints.get(key, '')
            is_secret = key == 'api_key' or str(key).endswith('_api_key')

            fields.append({
                'path': list(path),
                'key': key,
                'label': gui._fieldLabel(path),
                'type': field_type,
                'enum_values': enum_values,
                'hint': hint,
                'is_secret': is_secret,
                'template': copy.deepcopy(value),
            })

    walk(section_data, base_path)
    return {'description': description, 'fields': fields}


def get_schema():
    """获取所有分类的表单 schema。"""
    schema = {}
    for section in OlivaAIAgent.gui.SECTION_ORDER:
        schema[section] = _buildSectionSchema(section)
    return schema


def get_runtime_status():
    """获取运行状态信息（视觉、媒体、语音、模型等）。"""
    status = {
        'backend': OlivaAIAgent.conf.get('backend', default='openai'),
        'model': '',
        'vision_ready': False,
        'vision_text': '',
        'media_text': '',
        'voice_ready': False,
        'voice_text': '',
    }
    backend = status['backend']
    status['model'] = str(OlivaAIAgent.conf.get(backend, 'model', default='-'))

    try:
        vision_info = OlivaAIAgent.vision.getVisionStatus()
        status['vision_ready'] = bool(vision_info.get('ready'))
        status['vision_text'] = '视觉: 启用=%s | 就绪=%s | 路由=%s | 模型=%s' % (
            '是' if vision_info.get('enabled') else '否',
            '是' if vision_info.get('ready') else '否',
            vision_info.get('route', '-'),
            vision_info.get('model', '-'),
        )
    except Exception:
        status['vision_text'] = '视觉: 未就绪或未配置'

    try:
        media_info = OlivaAIAgent.media.getStatus()
        audio = media_info.get('audio', {})
        video = media_info.get('video', {})
        status['media_text'] = '媒体: 语音=%s(%s) | 视频=%s(%s)' % (
            '就绪' if audio.get('ready') else '关闭/未就绪', audio.get('model', '-'),
            '就绪' if video.get('ready') else '关闭/未就绪', video.get('model', '-'),
        )
    except Exception:
        status['media_text'] = '媒体: 未就绪'

    try:
        voice_info = OlivaAIAgent.voice.getStatus()
        status['voice_ready'] = bool(voice_info.get('ready'))
        status['voice_text'] = '语音: 启用=%s | 就绪=%s | 音色=%s' % (
            '是' if voice_info.get('enabled') else '否',
            '是' if voice_info.get('ready') else '否',
            voice_info.get('voice', '-'),
        )
    except Exception:
        status['voice_text'] = '语音: 未就绪'

    return status


def get_state(Proc=None) -> dict:
    """返回 WebUI 渲染所需的完整状态。"""
    gui = OlivaAIAgent.gui
    conf = OlivaAIAgent.conf
    return {
        'plugin_name': PLUGIN_NAME,
        'conf': conf.snapshot(),
        'groups': conf.groupsSnapshot(),
        'sections': [{'id': s, 'label': gui.SECTION_LABELS[s]} for s in gui.SECTION_ORDER],
        'group_switches': [{'key': k, 'label': l} for k, l in gui.GROUP_SWITCHES],
        'runtime_status': get_runtime_status(),
        'data_dir': os.path.abspath(conf.dataPath),
    }


def dispatch(payload: dict, Proc=None) -> dict:
    """分发 WebUI 业务请求。"""
    action = payload.get('action')
    conf = OlivaAIAgent.conf
    gui = OlivaAIAgent.gui

    with _dispatch_lock:
        if action == 'get_state':
            return {'ok': True, 'state': get_state(Proc), 'schema': get_schema()}

        if action == 'save_conf':
            raw_conf = payload.get('conf')
            if not isinstance(raw_conf, dict):
                raise ValueError('conf 必须为对象。')

            current_snapshot = conf.snapshot()
            schema = get_schema()
            for sec_key, sec_data in schema.items():
                for field in sec_data.get('fields', []):
                    path = tuple(field['path'])
                    template = field['template']
                    raw_val = _getNested(raw_conf, path)
                    if raw_val is not None:
                        parsed = _parse_field_value(raw_val, template, path)
                        gui._setNested(current_snapshot, path, parsed)

            conf.replace(current_snapshot, save_now=True)
            OlivaAIAgent.mcp.invalidate()
            conf.log(Proc, 2, 'WebUI | 配置已保存并应用')
            return {'ok': True, 'state': get_state(Proc)}

        if action == 'save_group_globals':
            live_conf = conf.snapshot()
            live_conf.setdefault('enable', {})['global'] = bool(payload.get('global', True))
            live_conf.setdefault('enable', {})['group_default'] = bool(payload.get('group_default', True))
            live_conf.setdefault('whitelist', {})['enabled'] = bool(payload.get('whitelist', False))
            live_conf.setdefault('ambient', {})['enable_default'] = bool(payload.get('ambient_default', False))

            prefixes = payload.get('prefix')
            if isinstance(prefixes, list):
                live_conf.setdefault('trigger', {})['prefix'] = [str(x) for x in prefixes]
            keywords = payload.get('keywords')
            if isinstance(keywords, list):
                live_conf.setdefault('trigger', {})['keywords'] = [str(x) for x in keywords]

            conf.replace(live_conf, save_now=True)
            conf.log(Proc, 2, 'WebUI | 全局群设置已保存')
            return {'ok': True, 'state': get_state(Proc)}

        if action == 'save_group':
            platform = str(payload.get('platform') or '').strip()
            group_id = str(payload.get('group_id') or '').strip()
            if not platform or not group_id:
                raise ValueError('平台与群 ID 不能为空。')
            values = payload.get('values')
            if not isinstance(values, dict):
                raise ValueError('群配置值必须为对象。')
            conf.replaceGroupConfig(platform, group_id, values)
            conf.saveGroups()
            conf.log(Proc, 2, f'WebUI | 群配置已更新：{platform}:{group_id}')
            return {'ok': True, 'state': get_state(Proc)}

        if action == 'delete_group':
            platform = str(payload.get('platform') or '').strip()
            group_id = str(payload.get('group_id') or '').strip()
            if not platform or not group_id:
                raise ValueError('平台与群 ID 不能为空。')
            conf.deleteGroupConfig(platform, group_id)
            conf.saveGroups()
            conf.log(Proc, 2, f'WebUI | 群配置已删除：{platform}:{group_id}')
            return {'ok': True, 'state': get_state(Proc)}

        if action == 'reload_conf':
            conf.load()
            OlivaAIAgent.mcp.invalidate()
            conf.log(Proc, 2, 'WebUI | 已从磁盘重新载入配置')
            return {'ok': True, 'state': get_state(Proc)}

        if action == 'reset_section':
            section = payload.get('section')
            if not section or section not in gui.SECTION_ORDER:
                raise ValueError(f'未知配置分类：{section}')
            live_conf = conf.snapshot()
            if section == 'general':
                live_conf['backend'] = copy.deepcopy(conf.DEFAULT_CONF['backend'])
                live_conf['debug_log'] = copy.deepcopy(conf.DEFAULT_CONF['debug_log'])
            elif section in gui.VIRTUAL_SECTION_PATHS:
                base_path = gui.VIRTUAL_SECTION_PATHS[section]
                parent = live_conf
                for key in base_path[:-1]:
                    parent = parent.setdefault(key, {})
                parent[base_path[-1]] = copy.deepcopy(
                    _getNested(conf.DEFAULT_CONF, base_path, {}),
                )
            elif section == 'trigger':
                prefixes = copy.deepcopy(live_conf.get('trigger', {}).get('prefix', []))
                keywords = copy.deepcopy(live_conf.get('trigger', {}).get('keywords', []))
                live_conf['trigger'] = copy.deepcopy(conf.DEFAULT_CONF['trigger'])
                live_conf['trigger']['prefix'] = prefixes
                live_conf['trigger']['keywords'] = keywords
            elif section == 'ambient':
                enable_default = bool(live_conf.get('ambient', {}).get('enable_default', False))
                live_conf['ambient'] = copy.deepcopy(conf.DEFAULT_CONF['ambient'])
                live_conf['ambient']['enable_default'] = enable_default
            else:
                live_conf[section] = copy.deepcopy(conf.DEFAULT_CONF[section])
            conf.replace(live_conf, save_now=True)
            conf.log(Proc, 2, f'WebUI | 已恢复分类默认值：{section}')
            return {'ok': True, 'state': get_state(Proc)}

        raise ValueError(f'未知的 WebUI 操作：{action}')


def handle_menu_event(plugin_event, Proc=None) -> None:
    """处理来自宿主 WebUI 的菜单事件。"""
    data = getattr(plugin_event, 'data', None)
    if getattr(data, 'namespace', None) != PLUGIN_NAME:
        return
    context = getattr(data, 'webui', None)
    if not isinstance(context, dict):
        return
    request_id = context.get('request_id')
    if not isinstance(request_id, str) or not request_id or len(request_id) > 128:
        return
    try:
        payload = getattr(data, 'payload', None)
        if not isinstance(payload, dict):
            raise ValueError('请求数据必须为对象。')
        response = dispatch(payload, Proc)
    except ValueError as error:
        response = {'ok': False, 'error': str(error)}
    except Exception as error:
        OlivaAIAgent.conf.log(Proc, 3, f'WebUI 配置操作失败：{type(error).__name__}: {error}')
        response = {'ok': False, 'error': '配置处理失败，请检查数据目录权限并重试。'}
    try:
        plugin_event.send('webui', request_id, response)
    except Exception as error:
        OlivaAIAgent.conf.log(Proc, 3, f'WebUI 回包失败：{type(error).__name__}: {error}')


# WebUI 静态资源的内存快照：OPK 插件由宿主解包到 plugin/tmp 下，该目录随时可能被宿主
# 清理；只有模块导入这一刻能保证文件还在，而本模块会被 __init__.py 导入，所以在这里
# 把 webui/ 整体读进内存。
_webui_assets = {}


def loadWebuiAssets():
    """模块导入时调用：把 webui/ 下的静态资源读进内存。"""
    global _webui_assets
    if _webui_assets:
        return
    root = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'webui')
    if not os.path.isdir(root):
        return
    for dir_path, _, file_names in os.walk(root):
        for file_name in file_names:
            full_path = os.path.join(dir_path, file_name)
            key = os.path.relpath(full_path, root).replace(os.sep, '/')
            try:
                with open(full_path, 'rb') as handle:
                    _webui_assets[key] = handle.read()
            except OSError:
                continue


def ensureWebuiAssets(Proc=None):
    """WebUI 资源兜底：解包目录被宿主清理后，把缺失文件从内存快照写回。

    宿主已为 /plugin/<namespace>/ 注册好 webui_root，这里只补文件、不改路径。
    不要用文件锁阻止宿主清理 —— 那会让宿主的目录清理中途失败、留下残缺目录，
    反而导致页面 404。
    """
    root = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'webui')
    restored = 0
    try:
        for key, content in list(_webui_assets.items()):
            target = os.path.join(root, *key.split('/'))
            if os.path.isfile(target):
                continue
            os.makedirs(os.path.dirname(target), exist_ok=True)
            with open(target, 'wb') as handle:
                handle.write(content)
            restored += 1
    except OSError as error:
        OlivaAIAgent.conf.log(Proc, 4, 'WebUI 资源兜底失败: %s' % error)
        return
    if restored:
        OlivaAIAgent.conf.log(Proc, 2, 'WebUI 资源已从内存快照恢复 %d 个文件' % restored)


loadWebuiAssets()

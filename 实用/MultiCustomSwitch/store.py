"""回复库、共享 Core 数据、群选择和序号管理。"""

import copy
import hashlib
import os
import re
import sys
import unicodedata
from pathlib import Path

import OlivaDiceCore

from . import files, msgCustom

DEFAULT_MODULES = [
    'OlivaDiceCore',
    'OlivaDiceJoy',
    'OlivaDiceMaster',
    'OlivaDiceLogger',
    'OlivaDiceOdyssey',
    'OlivaStoryCore',
]
MAX_BYTES = 8 * 1024 * 1024


class InvalidInput(ValueError):
    pass


class Conflict(InvalidInput):
    pass


def validate_replies(value):
    if not isinstance(value, dict) or len(value) > 5000:
        raise InvalidInput('自定义回复必须是 JSON 对象（回复键: 字符串），最多 5000 项。')
    for key, text in value.items():
        if not isinstance(key, str) or not key or len(key) > 200 or not isinstance(text, str) or len(text) > 20000:
            raise InvalidInput('回复键须为 1 至 200 字，回复内容须为不超过 20000 字的字符串。')
    if len(files.json_bytes(value)) > MAX_BYTES:
        raise InvalidInput('回复文件超过 8 MiB。')
    return dict(value)


def validate_name(name, allow_builtin=False):
    if not isinstance(name, str):
        raise InvalidInput('回复名必须是文本。')
    name = unicodedata.normalize('NFC', name.strip())
    if not name or len(name) > 100 or name in {'.', '..'} or name.endswith(('.', ' ')):
        raise InvalidInput('回复名须为 1 至 100 字，不能以点或空格结尾。')
    if re.search(r'[<>:"/\\|?*\x00-\x1f]', name):
        raise InvalidInput('回复名不能包含路径、控制字符或 Windows 文件名非法字符。')
    stem = name.split('.')[0].casefold()
    reserved = {'con', 'prn', 'aux', 'nul'}
    reserved.update(f'{prefix}{number}' for prefix in ('com', 'lpt') for number in range(1, 10))
    full_reserved = {'config', 'custom_list'} | (set() if allow_builtin else {'default', 'smp'})
    if stem in reserved or name.casefold() in full_reserved:
        raise InvalidInput('此名称为内置回复、配置文件或系统保留名称，请换一个名称。')
    return name


def model_int(value):
    if type(value) is int and value >= 1:
        return value
    if isinstance(value, str) and value.isascii() and value.isdecimal() and int(value) >= 1:
        return int(value)
    raise InvalidInput('回复序号必须是正整数。')


def core_defaults():
    manager = OlivaDiceCore.msgCustomManager
    getter = getattr(manager, 'getDictStrCustomDefault', None)
    if callable(getter):
        return dict(getter())
    # Core 3.5.0 没有此辅助接口，按新版 Core 相同的已加载模块顺序汇总源码默认值。
    result = dict(OlivaDiceCore.msgCustom.dictStrCustom)
    for module in list(sys.modules.values()):
        try:
            values = getattr(getattr(module, 'msgCustom', None), 'dictStrCustom', None)
            if type(values) is dict:
                result.update(
                    {key: text for key, text in values.items() if isinstance(key, str) and isinstance(text, str)}
                )
        except Exception:
            # 与 Core 一样，忽略不提供默认回复的模块属性访问异常。
            continue
    return {key: text for key, text in result.items() if isinstance(key, str) and isinstance(text, str)}


class ReplyStore:
    def __init__(self, proc, root=None):
        self.proc = proc
        self.root = Path(root or './plugin/data/MultiCustomSwitch')
        self.indexes = {}
        self.configs = {}
        self.groups = {}
        self.packs = {}
        self.recover_model = {}
        self.bot_names = {}
        with files.LOCK:
            (self.root / 'unity').mkdir(parents=True, exist_ok=True)
            self.reload('unity')
            for bot in self.bots:
                self.reload(bot)

    @property
    def bots(self):
        return self.proc.Proc_data['bot_info_dict']

    def check_scope(self, scope, allow_unity=True):
        if scope not in self.bots and not (allow_unity and scope == 'unity'):
            raise InvalidInput('账号不存在。')

    def directory(self, scope):
        self.check_scope(scope)
        return self.root / scope

    def core_file(self, bot, name):
        self.check_scope(bot, False)
        return Path(OlivaDiceCore.data.dataDirRoot) / bot / 'console' / name

    def log(self, message):
        self.proc.log(3, f'MultiCustomSwitch: {message}')

    def _validate_state(self, value):
        if not isinstance(value, dict) or type(value.get('enabled')) is not bool:
            raise InvalidInput('配置必须包含 enabled（布尔值）和 reply_model（整数）。')
        if type(value.get('reply_model')) is not int or value['reply_model'] < 1:
            raise InvalidInput('reply_model 必须是正整数。')
        return {'reply_model': value['reply_model'], 'enabled': value['enabled']}

    def reload(self, scope):
        self.check_scope(scope)
        with files.LOCK:
            directory = self.directory(scope)
            directory.mkdir(parents=True, exist_ok=True)
            loaded = {}
            for path in directory.glob('*.json'):
                if path.stem in {'config', 'custom_list'}:
                    continue
                name = validate_name(path.stem, allow_builtin=scope == 'unity')
                try:
                    raw = files.read_json(path)
                    # {} 与 Core 一致，表示没有偏离默认值。
                    loaded[name] = validate_replies(raw) if raw else self._empty_pack(raw)
                except (ValueError, OSError) as exc:
                    self.log(f'无法加载回复文件 {path.name}: {exc}')
            if scope != 'unity':
                index_path = directory / 'custom_list.json'
                index = files.read_json(index_path, {})
                if not isinstance(index, dict):
                    raise InvalidInput(f'{scope}/custom_list.json 必须是序号到回复名的 JSON 对象。')
                clean = {}
                used_names = set()
                for key, name in index.items():
                    number = model_int(key)
                    name = validate_name(name)
                    if number < 3 or number in clean or name.casefold() in used_names:
                        raise InvalidInput('自定义序号须 >=3；序号及回复名不能重复。')
                    clean[number] = name
                    used_names.add(name.casefold())
                for name in sorted(loaded):
                    if name.casefold() not in used_names:
                        number = max([2, *clean]) + 1
                        clean[number] = name
                        used_names.add(name.casefold())
                if {str(key): value for key, value in clean.items()} != index or not index_path.is_file():
                    files.write_json(index_path, {str(key): value for key, value in sorted(clean.items())})
                config_path = directory / 'config.json'
                config = self._validate_state(files.read_json(config_path, {'reply_model': 1, 'enabled': True}))
                if not config_path.is_file():
                    files.write_json(config_path, config)
                group_dir = directory / 'group'
                group_dir.mkdir(exist_ok=True)
                groups = {}
                for path in group_dir.glob('*.json'):
                    try:
                        groups[path.stem] = self._validate_state(files.read_json(path))
                    except (ValueError, OSError) as exc:
                        # 无效群配置不能意外继承并启用模板。
                        self.log(f'群配置 {path.name} 无效，暂使用原始回复: {exc}')
                        groups[path.stem] = {'reply_model': 1, 'enabled': False}
                self.indexes[scope], self.configs[scope], self.groups[scope] = clean, config, groups
                self.modules(scope)
            self.packs[scope] = loaded

    @staticmethod
    def _empty_pack(value):
        if value != {}:
            raise InvalidInput('回复文件必须是 JSON 对象。')
        return {}

    def modules(self, bot, values=None):
        path = self.core_file(bot, 'recover_model.json')
        with files.LOCK:
            if values is not None:
                if (
                    not isinstance(values, list)
                    or len(values) > 50
                    or any(
                        not isinstance(item, str) or not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]{0,99}', item)
                        for item in values
                    )
                ):
                    raise InvalidInput('恢复模块必须是模块名列表，最多 50 项。')
                clean = list(values) or DEFAULT_MODULES.copy()
                files.write_json(path, {'modules': clean})
            else:
                try:
                    data = files.read_json(path, {})
                    clean = data.get('modules') if isinstance(data, dict) else None
                    if not isinstance(clean, list) or not clean or any(not isinstance(item, str) for item in clean):
                        clean = DEFAULT_MODULES.copy()
                except (ValueError, OSError):
                    clean = DEFAULT_MODULES.copy()
            self.recover_model[bot] = list(clean)
            return list(clean)

    def default_values(self, bot):
        mapping = OlivaDiceCore.msgCustom.dictStrCustomDict
        with files.LOCK:
            values = mapping.original_get(bot, {}) if hasattr(mapping, 'original_get') else mapping.get(bot, {})
            return dict(values)

    def smp(self, bot=None):
        with files.LOCK:
            values = core_defaults()
            if bot is not None:
                self.check_scope(bot, False)
                # 登录 API 不可用时用账号 ID；不会使用虚假的三字母 Bot。
                values['strBotName'] = self.bot_names.get(bot, str(self.bots[bot].id))
            return values

    def baseline(self, scope, baseline_bot=None):
        bot = scope if scope != 'unity' else baseline_bot
        if bot is None:
            return self.smp()
        self.check_scope(bot, False)
        result = {}
        with files.LOCK:
            for name in self.modules(bot):
                module = sys.modules.get(name)
                values = getattr(getattr(module, 'msgCustom', None), 'dictStrCustom', None)
                if isinstance(values, dict):
                    result.update({key: text for key, text in values.items() if isinstance(text, str)})
        return result

    def _name(self, scope, selection):
        if scope == 'unity':
            for name in self.packs[scope]:
                if name == selection:
                    return name
        else:
            number = model_int(selection)
            if number in self.indexes[scope]:
                return self.indexes[scope][number]
        raise InvalidInput('回复不存在，请刷新列表。')

    def values(self, scope, selection):
        self.check_scope(scope)
        with files.LOCK:
            if scope != 'unity' and model_int(selection) in (1, 2):
                return self.default_values(scope) if model_int(selection) == 1 else self.smp(scope)
            name = self._name(scope, selection)
            if name not in self.packs[scope]:
                raise InvalidInput('回复文件缺失或无法读取，请修复文件后刷新。')
            return {**self.smp(scope if scope != 'unity' else None), **self.packs[scope][name]}

    def list_replies(self, scope):
        self.check_scope(scope)
        with files.LOCK:
            if scope == 'unity':
                return [
                    {'selection': name, 'name': name, 'readonly': False, 'available': True}
                    for name in sorted(self.packs[scope])
                ]
            return [
                {'selection': 1, 'name': 'default', 'readonly': False, 'available': True},
                {'selection': 2, 'name': 'smp', 'readonly': True, 'available': True},
                *[
                    {'selection': number, 'name': name, 'readonly': False, 'available': name in self.packs[scope]}
                    for number, name in sorted(self.indexes[scope].items())
                ],
            ]

    def snapshot(self, scope, selection, baseline_bot=None):
        with files.LOCK:
            values = self.values(scope, selection)
            baseline = self.baseline(scope, baseline_bot)
            readonly = scope != 'unity' and model_int(selection) == 2
            if readonly:
                baseline = values
            notes = dict(msgCustom.dictStrCustomNote)
            for module_name in ('OlivaDiceWebUI', 'OlivaDiceNativeGUI'):
                module = sys.modules.get(module_name)
                candidate = getattr(getattr(module, 'service', None), 'REPLY_NOTES', {})
                notes.update(candidate if isinstance(candidate, dict) else {})
                candidate = getattr(getattr(module, 'msgCustom', None), 'dictStrCustomNote', {})
                notes.update(candidate if isinstance(candidate, dict) else {})
            identity = (
                ('default' if model_int(selection) == 1 else 'smp')
                if scope != 'unity' and model_int(selection) < 3
                else self._name(scope, selection)
            )
            revision = hashlib.sha256(
                files.json_bytes(
                    {
                        'scope': scope,
                        'selection': selection,
                        'identity': identity,
                        'values': values,
                        'baseline': baseline,
                    }
                )
            ).hexdigest()
            entries = [
                {
                    'key': key,
                    'value': text,
                    'default': baseline.get(key),
                    'modified': key not in baseline or baseline[key] != text,
                    'note': notes.get(key, ''),
                }
                for key, text in sorted(values.items())
                if isinstance(text, str)
            ]
            return {'entries': entries, 'revision': revision, 'readonly': readonly}

    def _save_values(self, scope, selection, values):
        if scope != 'unity' and model_int(selection) == 2:
            raise InvalidInput('smp 为只读回复。')
        if scope != 'unity' and model_int(selection) == 1:
            core = OlivaDiceCore
            mapping = core.msgCustom.dictStrCustomDict
            old = self.default_values(scope)
            old_updates = copy.deepcopy(core.msgCustom.dictStrCustomUpdateDict.get(scope, {}))
            defaults = core_defaults()
            mapping[scope] = dict(values)
            core.msgCustom.dictStrCustomUpdateDict[scope] = {
                key: text for key, text in values.items() if key not in defaults or defaults[key] != text
            }
            try:
                core.msgCustomManager.saveMsgCustomByBotHash(scope)
            except Exception:
                mapping[scope] = old
                core.msgCustom.dictStrCustomUpdateDict[scope] = old_updates
                raise
            return
        name = self._name(scope, selection)
        defaults = self.smp(scope if scope != 'unity' else None)
        changes = {key: text for key, text in values.items() if key not in defaults or defaults[key] != text}
        files.write_json(self.directory(scope) / f'{name}.json', changes)
        self.packs[scope][name] = changes

    def edit(self, scope, selection, key, value, revision, reset=False, baseline_bot=None, delete=False):
        with files.LOCK:
            snapshot = self.snapshot(scope, selection, baseline_bot)
            if snapshot['readonly']:
                raise InvalidInput('smp 为只读回复。')
            if revision != snapshot['revision']:
                raise Conflict('回复已被其他窗口或官方面板修改，请刷新后再编辑。')
            values = self.values(scope, selection)
            baseline = self.baseline(scope, baseline_bot)
            if delete:
                if key in self.smp(scope if scope != 'unity' else None):
                    raise InvalidInput('内置回复键不能删除，请使用恢复默认。')
                values.pop(key, None)
            elif reset:
                if key not in baseline:
                    raise InvalidInput('此回复键没有所选恢复模块的默认值。')
                values[key] = baseline[key]
            else:
                validate_replies({key: value})
                values[key] = value
            self._save_values(scope, selection, values)
            return self.snapshot(scope, selection, baseline_bot)

    def import_pack(self, scope, name, data, conflict=None):
        self.check_scope(scope)
        name, data = validate_name(name, allow_builtin=True), validate_replies(data)
        with files.LOCK:
            if scope != 'unity' and name.casefold() in {'default', 'smp'}:
                builtin = name.casefold()
                if conflict is None:
                    return {'conflict': True, 'name': builtin, 'options': ['overwrite', 'copy', 'cancel']}
                if conflict == 'cancel':
                    return {'cancelled': True}
                if conflict == 'overwrite':
                    if builtin == 'smp':
                        raise InvalidInput('smp 为只读回复；请选择创建为副本或取消导入。')
                    baseline = self.baseline(scope)
                    custom = {key: text for key, text in self.default_values(scope).items() if key not in baseline}
                    self._save_values(scope, 1, {**baseline, **custom, **data})
                    return {'selection': 1, 'name': 'default'}
                if conflict != 'copy':
                    raise InvalidInput('请选择覆盖、创建为副本或取消导入。')
                count = 1
                occupied = {path.stem.casefold() for path in self.directory(scope).glob('*.json')}
                while f'{builtin} - 副本{count}'.casefold() in occupied:
                    count += 1
                name = f'{builtin} - 副本{count}'
                conflict = None
            existing = next((item for item in self.packs[scope] if item.casefold() == name.casefold()), None)
            if scope != 'unity':
                existing = existing or next(
                    (item for item in self.indexes[scope].values() if item.casefold() == name.casefold()), None
                )
            # 同名但损坏的文件也不能绕过重名选择。
            existing = existing or next(
                (p.stem for p in self.directory(scope).glob('*.json') if p.stem.casefold() == name.casefold()), None
            )
            if existing:
                if conflict is None:
                    return {'conflict': True, 'name': existing, 'options': ['overwrite', 'copy', 'cancel']}
                if conflict == 'cancel':
                    return {'cancelled': True}
                if conflict == 'copy':
                    count = 1
                    occupied = {p.stem.casefold() for p in self.directory(scope).glob('*.json')}
                    while f'{name} - 副本{count}'.casefold() in occupied:
                        count += 1
                    name = validate_name(f'{name} - 副本{count}')
                elif conflict == 'overwrite':
                    name = existing
                else:
                    raise InvalidInput('请选择覆盖、创建为副本或取消导入。')
            elif conflict not in (None, 'overwrite', 'copy', 'cancel'):
                raise InvalidInput('重名处理选项无效。')
            if conflict == 'cancel':
                return {'cancelled': True}
            changes = {self.directory(scope) / f'{name}.json': files.json_bytes(data)}
            selection = name
            index = dict(self.indexes.get(scope, {}))
            if scope != 'unity':
                selection = next((number for number, item in index.items() if item == name), None)
                if selection is None:
                    selection = max([2, *index]) + 1
                    index[selection] = name
                changes[self.directory(scope) / 'custom_list.json'] = files.json_bytes(
                    {str(key): value for key, value in sorted(index.items())},
                )
            files.transaction(changes)
            self.packs[scope][name] = dict(data)
            if scope != 'unity':
                self.indexes[scope] = index
            return {'selection': selection, 'name': name}

    def clone(self, scope, name, source_scope, source_selection):
        self.check_scope(source_scope)
        with files.LOCK:
            values = self.values(source_scope, source_selection)
            result = self.import_pack(scope, name, values)
            if result.get('conflict'):
                raise Conflict('此文件夹已经存在同名回复，请换一个名称。')
            return result

    def rename(self, scope, selection, name):
        name = validate_name(name, allow_builtin=scope == 'unity')
        with files.LOCK:
            old = self._name(scope, selection)
            occupied = {path.stem for path in self.directory(scope).glob('*.json')}
            if any(item != old and item.casefold() == name.casefold() for item in occupied):
                raise Conflict('此文件夹已经存在同名回复。')
            if name == old:
                return {'selection': selection, 'name': name}
            source = self.directory(scope) / f'{old}.json'
            target = self.directory(scope) / f'{name}.json'
            if not source.is_file():
                raise InvalidInput('原回复文件不存在。')
            index = dict(self.indexes.get(scope, {}))
            changes = {source: None, target: files.read_bytes(source)}
            if scope != 'unity':
                index[model_int(selection)] = name
                changes[self.directory(scope) / 'custom_list.json'] = files.json_bytes(
                    {str(key): value for key, value in sorted(index.items())},
                )
            if old.casefold() == name.casefold():
                # Windows 的 Path 比较忽略大小写，不能用同一个变更字典表示两个路径。
                os.rename(source, target)
                try:
                    if scope != 'unity':
                        files.write_json(
                            self.directory(scope) / 'custom_list.json',
                            {str(key): value for key, value in sorted(index.items())},
                        )
                except Exception:
                    os.rename(target, source)
                    raise
            else:
                files.transaction(changes)
            self.packs[scope][name] = self.packs[scope].pop(old)
            if scope != 'unity':
                self.indexes[scope] = index
            return {'selection': name if scope == 'unity' else selection, 'name': name}

    def index_revision(self, bot):
        self.check_scope(bot, False)
        with files.LOCK:
            return hashlib.sha256(files.json_bytes(self.indexes[bot])).hexdigest()

    def reindex(self, bot, mapping, revision=None):
        self.check_scope(bot, False)
        with files.LOCK:
            if revision is not None and revision != self.index_revision(bot):
                raise Conflict('回复列表已经改变，请刷新后重新设置序号。')
            if not isinstance(mapping, dict):
                raise InvalidInput('新序号表必须是旧序号到新序号的 JSON 对象。')
            remap = {model_int(old): model_int(new) for old, new in mapping.items()}
            if (
                len(remap) != len(mapping)
                or set(remap) != set(self.indexes[bot])
                or any(number < 3 for number in remap.values())
            ):
                raise InvalidInput('必须提供全部自定义回复，且新序号均 >=3。')
            if len(set(remap.values())) != len(remap):
                raise InvalidInput('新序号不能重复。')
            index = {remap[old]: name for old, name in self.indexes[bot].items()}
            config_path = self.directory(bot) / 'config.json'
            raw_config = files.read_json(config_path)
            config = self._validate_state(raw_config)
            config['reply_model'] = remap.get(config['reply_model'], config['reply_model'])
            changes = {
                self.directory(bot) / 'custom_list.json': files.json_bytes(
                    {str(key): name for key, name in sorted(index.items())},
                ),
                config_path: files.json_bytes({**raw_config, **config}),
            }
            groups = {}
            for path in (self.directory(bot) / 'group').glob('*.json'):
                raw = files.read_json(path)
                state = self._validate_state(raw)
                state['reply_model'] = remap.get(state['reply_model'], state['reply_model'])
                changes[path] = files.json_bytes({**raw, **state})
                groups[path.stem] = state
            files.transaction(changes)
            self.indexes[bot], self.configs[bot], self.groups[bot] = index, config, groups
            return self.list_replies(bot)

    def group_hash(self, event):
        if event.plugin_info.get('func_type') in ('group_message', 'private_message'):
            # 消息群标识直接取 Core 实现；私聊即使携带群字段也不读取群设置。
            hag_id = OlivaDiceCore.msgReply.getHagIDFromMsg(event, self.proc)
        else:
            # 入群、戳一戳等通知沿用 Core 的 host_id|group_id 规则。
            group_id = getattr(event.data, 'group_id', None)
            if group_id in (None, -1, '-1'):
                return None
            host_id = getattr(event.data, 'host_id', None)
            hag_id = f'{host_id}|{group_id}' if host_id is not None else str(group_id)
        if hag_id is None:
            return None
        return OlivaDiceCore.userConfig.getUserHash(
            userId=hag_id, userType='group', platform=event.platform['platform']
        )

    def status(self, bot, group_hash=None):
        self.check_scope(bot, False)
        with files.LOCK:
            global_state = dict(self.configs[bot])
            group = self.groups[bot].get(group_hash) if group_hash else None
            selected = group['reply_model'] if group else global_state['reply_model']
            enabled = global_state['enabled'] and (group is None or group['enabled'])
            effective = selected if enabled else 1
            available = {item['selection'] for item in self.list_replies(bot) if item['available']}
            missing = effective not in available
            if missing:
                effective = 1
            return {
                'global': global_state,
                'group': dict(group) if group else None,
                'selected': selected,
                'effective': effective,
                'enabled': enabled,
                'inherited': group is None,
                'missing': missing,
            }

    def select(self, bot, model=None, enabled=None, group_hash=None):
        self.check_scope(bot, False)
        if enabled is not None and type(enabled) is not bool:
            raise InvalidInput('开关必须是布尔值。')
        if group_hash is not None and not re.fullmatch(r'[a-f0-9]{32}', group_hash):
            raise InvalidInput('群 hash 格式无效。')
        with files.LOCK:
            inherited = {'reply_model': self.configs[bot]['reply_model'], 'enabled': True}
            current = self.groups[bot].get(group_hash, inherited) if group_hash else self.configs[bot]
            state = dict(current)
            if model is not None:
                model = model_int(model)
                if not any(item['selection'] == model and item['available'] for item in self.list_replies(bot)):
                    raise InvalidInput('回复序号不存在或回复文件无法读取。')
                state['reply_model'] = model
            if enabled is not None:
                state['enabled'] = enabled
            path = self.directory(bot) / 'config.json'
            if group_hash:
                path = self.directory(bot) / 'group' / f'{group_hash}.json'
            existing = files.read_json(path, {})
            if not isinstance(existing, dict):
                raise InvalidInput('原配置不是 JSON 对象，已中止写入。')
            files.write_json(path, {**existing, **state})
            if group_hash:
                self.groups[bot][group_hash] = state
            else:
                self.configs[bot] = state
            return self.status(bot, group_hash)

    def effective(self, event):
        bot = event.bot_info.hash
        with files.LOCK:
            status = self.status(bot, self.group_hash(event))
            return self.values(bot, status['effective'])

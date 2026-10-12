"""按裸 .sn 的优先级生成文本，读取 Core 内存快照，不更新群名片或写人物卡。"""

import threading


class SnProvider:
    def __init__(self, core):
        self.core = core
        self.lock = threading.RLock()

    def get(self, user_id, platform, hag_id):
        with self.lock:
            pc = self.core.pcCard
            pc_hash = pc.getPcHash(user_id, platform)
            pc_name = pc.pcCardDataGetSelectionKey(pc_hash, hag_id)
            if pc_name is None:
                return None
            template_name = pc.pcCardDataGetTemplateKey(pc_hash, pc_name) or 'default'
            template = pc.pcCardDataGetTemplateByKey(template_name) or {}
            records = dict(pc.pcCardDataGetTemplateDataByKey(pc_hash, pc_name, 'noteRecord', {}) or {})
            title = None
            if hag_id is not None:
                group_hash = self.core.userConfig.getUserHash(hag_id, 'group', platform)
                title = records.get('名片' + group_hash[:8])
                # 有群记录时，空值和全局记录的处理与 Core .sn 相同。
                if '名片' + group_hash[:8] not in records:
                    title = records.get('名片')
            else:
                title = records.get('名片')
            if title is None:
                if 'snTitle' in template:
                    title = template['snTitle']
                else:
                    default_template = pc.pcCardDataGetTemplateByKey('default') or {}
                    title = default_template.get('snTitle')
            if not isinstance(title, str) or not title.strip():
                return None

            # getNoteFormat 内部的 getter 会补写缺失的默认属性，因此在本地快照上对齐格式化。
            values = dict(pc.dictPcCardData.get('unity', {}).get(pc_hash, {}).get(pc_name, {}))
            for key, value in (template.get('defaultSkillValue') or {}).items():
                if type(value) is int:
                    values.setdefault(key, value)
            result = title.replace('{tName}', str(pc_name))
            for key, value in values.items():
                result = result.replace('{' + str(key) + '}', str(int(value)))
            result = result.replace('{SANMAX}', str(int(99 - values.get('克苏鲁神话', 0))))
            result = ' '.join(result.splitlines()).strip()
            return result or None

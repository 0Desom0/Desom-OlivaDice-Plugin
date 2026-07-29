# -*- encoding: utf-8 -*-
'''
OlivaAIAgent 事件回调入口
'''

import os

import OlivaAIAgent

gProc = None


class Event(object):
    def init(plugin_event, Proc):
        # 初始化：建目录、载入/生成配置
        try:
            OlivaAIAgent.conf.load()
            OlivaAIAgent.conf.log(Proc, 2, '配置已加载 (plugin/data/OlivaAIAgent/config.json)')
        except Exception as e:
            OlivaAIAgent.conf.log(Proc, 4, '初始化失败: %s' % e)

    def init_after(plugin_event, Proc):
        global gProc
        gProc = Proc
        OlivaAIAgent.conf.gProc = Proc
        OlivaAIAgent.conf.traceLog(Proc, 'plugin.init_after.start')
        try:
            vision_status = OlivaAIAgent.vision.getVisionStatus()
            OlivaAIAgent.conf.log(
                Proc,
                2 if not vision_status['enabled'] or vision_status['ready'] else 3,
                '视觉配置：启用=%s | 就绪=%s | 路由=%s | 模型=%s | 模式=%s' % (
                    '是' if vision_status['enabled'] else '否',
                    '是' if vision_status['ready'] else '否',
                    {'main': '主模型', 'independent': '独立视觉模型', 'disabled': '已关闭'}.get(
                        vision_status['route'],
                        vision_status['route'],
                    ),
                    vision_status['model'] or '-',
                    vision_status['mode'] or '-',
                ),
            )
        except Exception as e:
            OlivaAIAgent.conf.log(Proc, 3, '视觉配置检查失败: %s' % e)
        # 所有 OlivOS 接口在初始化阶段扫描并写入内存目录。
        try:
            stats = OlivaAIAgent.introspection.initialize(plugin_event, Proc, force=True)
            OlivaAIAgent.conf.log(
                Proc,
                2,
                'OlivOS接口目录: %d个SDK模块 / %d个SDK接口，Event/Proc 已缓存' % (
                    stats['sdk_modules'],
                    stats['sdk_interfaces'],
                ),
            )
        except Exception as e:
            OlivaAIAgent.conf.log(Proc, 3, 'OlivOS接口目录初始化失败: %s' % e)
        # 加载知识库/技能索引（不阻塞：技能索引可能较慢，放后台）
        try:
            n_kb = OlivaAIAgent.knowledge.loadStatic()
            OlivaAIAgent.conf.log(Proc, 2, '静态知识库: %d 条' % n_kb)
        except Exception as e:
            OlivaAIAgent.conf.log(Proc, 3, '知识库加载失败: %s' % e)
        try:
            OlivaAIAgent.semantic.initialize()
            semantic_status = OlivaAIAgent.semantic.getStatus()
            OlivaAIAgent.conf.log(Proc, 2, '长期事实库: SQLite 就绪 | 检索=%s | 模型=%s' % (
                '向量' if semantic_status['mode'] == 'vector' else '关键词降级',
                semantic_status['model'] or '-',
            ))
        except Exception as e:
            OlivaAIAgent.conf.log(Proc, 3, '长期事实库初始化失败: %s' % e)

        def _load_skills():
            try:
                idx = OlivaAIAgent.skills.buildIndex()
                OlivaAIAgent.conf.log(Proc, 2, '技能索引: %d 个 (引擎 %s)' % (
                    len(idx), OlivaAIAgent.skills.backendName()))
            except Exception as e:
                OlivaAIAgent.conf.log(Proc, 3, '技能索引构建失败: %s' % e)
        import threading
        threading.Thread(target=_load_skills, daemon=True).start()

        # 载入并重新挂起持久化的定时提醒(重启/重载后不丢)
        try:
            n_rmd = OlivaAIAgent.reminder.loadAndReschedule()
            if n_rmd:
                OlivaAIAgent.conf.log(Proc, 2, '定时提醒: 恢复 %d 个待触发任务' % n_rmd)
        except Exception as e:
            OlivaAIAgent.conf.log(Proc, 3, '定时提醒恢复失败: %s' % e)

        backend = OlivaAIAgent.conf.get('backend', default='openai')
        api_key = str(OlivaAIAgent.conf.get(backend, 'api_key', default=''))
        if api_key == '':
            OlivaAIAgent.conf.log(
                Proc, 3,
                '尚未配置 API Key，请编辑 plugin/data/OlivaAIAgent/config.json 后发送 .ai reload')
        else:
            OlivaAIAgent.conf.log(Proc, 2, '就绪 | 后端: %s | 模型: %s' % (
                backend, OlivaAIAgent.conf.get(backend, 'model', default='')))
        OlivaAIAgent.conf.traceLog(Proc, 'plugin.init_after.done')

    def private_message(plugin_event, Proc):
        OlivaAIAgent.msgReply.onPrivateMessage(plugin_event, Proc)

    def group_message(plugin_event, Proc):
        OlivaAIAgent.msgReply.onGroupMessage(plugin_event, Proc)

    def save(plugin_event, Proc):
        # 插件重载前持久化
        try:
            OlivaAIAgent.memory.saveAll()
            OlivaAIAgent.knowledge.saveAll()
            OlivaAIAgent.ambient.saveAll()
            OlivaAIAgent.reminder.saveAll()
            OlivaAIAgent.conf.saveGroups()
        except Exception:
            pass

    def menu(plugin_event, Proc):
        if plugin_event.data.namespace != 'OlivaAIAgent':
            return
        if plugin_event.data.event == 'OlivaAIAgent_Menu_OpenConf':
            try:
                OlivaAIAgent.conf.initDataPath()
                os.startfile(os.path.abspath(OlivaAIAgent.conf.dataPath))
            except Exception as e:
                OlivaAIAgent.conf.log(Proc, 3, '打开配置目录失败: %s' % e)
        elif plugin_event.data.event == 'OlivaAIAgent_Menu_Reload':
            OlivaAIAgent.conf.load()
            OlivaAIAgent.conf.log(Proc, 2, '配置已重载')

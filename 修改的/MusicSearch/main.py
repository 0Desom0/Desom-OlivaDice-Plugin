# -*- encoding=utf8 -*-

import urllib.parse
import urllib.request
import urllib.error
import json
import ssl
from . import load

oliva_dice_core_available = False
try:
    import OlivaDiceCore
    oliva_dice_core_available = True
except Exception:
    oliva_dice_core_available = False


class MusicSearchProcessor:
    """
    点歌处理类，用于处理点歌的核心逻辑
    """
    
    # 配置初始化
    config = load.get_default_config().copy()
    
    # 调试模式开关
    DEBUG_MODE = False
    
    # 当前进程对象（用于调试日志）
    current_Proc = None

    # bot 列表缓存（初始化阶段可从 Proc 获取）
    bot_info_dict = {}
    
    # API 地址
    API_URL = "https://oiapi.net/api/Music_163"

    # 默认请求头，提升第三方接口兼容性
    DEFAULT_HEADERS = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0 Safari/537.36',
        'Accept': 'application/json, text/plain, */*',
        'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
        'Connection': 'close'
    }
    
    @classmethod
    def reload_config(cls):
        """
        重新加载配置
        """
        cls.config = load.get_default_config().copy()
        cls.DEBUG_MODE = cls.config.get('debug_mode', False)

    @classmethod
    def reload_config_for_bot(cls, bot_hash):
        """
        按 bot 重载配置
        """
        cls.config = load.load_json_config('config.json', default=load.get_default_config(), bot_hash=bot_hash)
        cls.DEBUG_MODE = cls.config.get('debug_mode', False)
    
    @classmethod
    def debug_log(cls, Proc, message):
        """
        调试日志输出方法
        :param Proc: 进程对象
        :param message: 日志消息
        """
        if cls.DEBUG_MODE:
            actual_Proc = Proc if Proc else cls.current_Proc
            if actual_Proc:
                actual_Proc.log(2, f">>> [调试] {message}", [])
    
    @classmethod
    def init(cls, Proc):
        """
        初始化方法
        :param Proc: 进程对象
        """
        cls.current_Proc = Proc

        # 初始化阶段 plugin_event 可能为 None，因此这里从 Proc 中预先为每个 bot 建立配置目录
        try:
            bot_info_dict = getattr(Proc, 'Proc_data', {}).get('bot_info_dict', {})
            if isinstance(bot_info_dict, dict):
                cls.bot_info_dict = bot_info_dict
                for bot_hash in bot_info_dict.keys():
                    load.init_config(bot_hash=bot_hash)
                    Proc.log(2, f">>> 已初始化点歌插件 bot 配置目录: {bot_hash}", [])
        except Exception as e:
            Proc.log(3, f">>> 点歌插件 bot 配置目录初始化失败: {type(e).__name__}: {str(e)}", [])

        Proc.log(2, ">>> 点歌插件已初始化", [])
    
    @classmethod
    def search_music(cls, song_name=None, Proc=None, song_id=None):
        """
        搜索歌曲
        :param song_name: 歌曲名称
        :param Proc: 进程对象，用于输出日志
        :param song_id: 歌曲 ID，若传入则按 ID 查询
        :return: 搜索结果，失败返回 None
        """
        try:
            # 构建请求参数
            params = {}
            if song_id is not None:
                params['id'] = int(song_id)
            elif song_name is not None:
                params['name'] = song_name
            else:
                raise ValueError('song_name 和 song_id 不能同时为空')

            url_params = urllib.parse.urlencode(params)
            full_url = f"{cls.API_URL}?{url_params}"
            request = urllib.request.Request(full_url, headers=cls.DEFAULT_HEADERS, method='GET')
            
            cls.debug_log(Proc, f"请求 URL: {full_url}")
            
            def do_request(context=None):
                with urllib.request.urlopen(request, timeout=10, context=context) as response:
                    raw_data = response.read()
                    charset = response.headers.get_content_charset() or 'utf-8'
                    data = raw_data.decode(charset, errors='replace')
                    result = json.loads(data)
                    cls.debug_log(Proc, f"API 返回结果: {json.dumps(result, ensure_ascii=False, indent=2)}")
                    return result

            try:
                # 优先使用默认 SSL 校验
                return do_request()
            except ssl.SSLError as e:
                cls.debug_log(Proc, f"SSL 校验失败，尝试兼容模式: {type(e).__name__}: {str(e)}")
                insecure_context = ssl._create_unverified_context()
                return do_request(insecure_context)
            except urllib.error.URLError as e:
                reason = getattr(e, 'reason', e)
                if isinstance(reason, ssl.SSLError):
                    cls.debug_log(Proc, f"URL 请求触发 SSL 错误，尝试兼容模式: {type(reason).__name__}: {str(reason)}")
                    insecure_context = ssl._create_unverified_context()
                    return do_request(insecure_context)
                raise
        except Exception as e:
            error_message = f"搜索歌曲失败: {type(e).__name__}: {str(e)}"
            cls.debug_log(Proc, error_message)
            if Proc:
                Proc.log(3, f">>> {error_message}", [])
            return None
    
    @classmethod
    def build_cq_music(cls, song_data):
        """
        构建 CQ 码音乐消息
        :param song_data: 歌曲数据
        :return: CQ 码字符串
        """
        song_id = song_data.get('id', '')
        jump_url = song_data.get('jumpurl', '')
        title = song_data.get('name', '')
        image = song_data.get('picurl', '')
        
        # 处理歌手信息
        singers = song_data.get('singers', [])
        singer_names = [s.get('name', '') for s in singers]
        content = '/'.join(singer_names)
        
        # 构建音频 URL
        audio_url = f"http://music.163.com/song/media/outer/url?id={song_id}"
        
        cq_code = f"[CQ:music,type=163,id={song_id},url={jump_url},audio={audio_url},title={title},image={image},content={content}]"
        
        cls.debug_log(None, f"构建的 CQ 码: {cq_code}")
        
        return cq_code

    @classmethod
    def get_hag_id(cls, plugin_event):
        """
        获取 OlivaDice 的 host|group / group 标识
        """
        try:
            host_id = getattr(plugin_event.data, 'host_id', None)
        except Exception:
            host_id = None

        try:
            group_id = getattr(plugin_event.data, 'group_id', None)
        except Exception:
            group_id = None

        group_id = str(group_id) if group_id is not None else ''
        host_id = str(host_id) if host_id is not None else ''
        if host_id:
            return f"{host_id}|{group_id}"
        return group_id

    @classmethod
    def get_group_id(cls, plugin_event):
        """
        获取当前群号；群级配置只按群号保存，一个群一个文件
        """
        try:
            group_id = getattr(plugin_event.data, 'group_id', None)
            if group_id is not None:
                return str(group_id)
        except Exception:
            pass
        return None

    @classmethod
    def is_enabled_for_context(cls, plugin_event):
        """
        若存在 OlivaDiceCore，则遵循其 bot on/off 逻辑
        """
        if not oliva_dice_core_available:
            return True

        try:
            flag_is_from_group = plugin_event.plugin_info['func_type'] == 'group_message'
            flag_is_from_host = False
            if flag_is_from_group and getattr(plugin_event.data, 'host_id', None) is not None:
                flag_is_from_host = True

            flag_host_local_enable = True
            if flag_is_from_host:
                flag_host_local_enable = OlivaDiceCore.userConfig.getUserConfigByKey(
                    userId=plugin_event.data.host_id,
                    userType='host',
                    platform=plugin_event.platform['platform'],
                    userConfigKey='hostLocalEnable',
                    botHash=plugin_event.bot_info.hash,
                )

            flag_group_enable = True
            if flag_is_from_group:
                tmp_hag_id = cls.get_hag_id(plugin_event)
                if tmp_hag_id:
                    flag_group_enable = OlivaDiceCore.userConfig.getUserConfigByKey(
                        userId=tmp_hag_id,
                        userType='group',
                        platform=plugin_event.platform['platform'],
                        userConfigKey='groupEnable',
                        botHash=plugin_event.bot_info.hash,
                    )

            if not flag_host_local_enable:
                return False
            if not flag_group_enable:
                return False
        except Exception:
            return True

        return True

    @classmethod
    def get_song_result(cls, song_name, Proc):
        """
        根据输入获取歌曲结果；纯数字按 id 查询，其余按名称查询
        """
        if isinstance(song_name, str) and song_name.isdecimal():
            Proc.log(2, f">>> 检测到纯数字输入，按歌曲ID查询: {song_name}", [])
            return cls.search_music(song_id=int(song_name), Proc=Proc)
        return cls.search_music(song_name=song_name, Proc=Proc)

    @classmethod
    def is_config_master(cls, plugin_event):
        """
        判断当前用户是否为配置骰主（按 bot 配置）
        """
        try:
            masters = cls.config.get('masters', [])
            if not isinstance(masters, list):
                return False
            return str(plugin_event.data.user_id) in [str(x).strip() for x in masters]
        except Exception:
            return False

    @classmethod
    def is_dice_master(cls, plugin_event):
        """
        判断当前用户是否为 OlivaDice 骰主
        """
        if oliva_dice_core_available:
            try:
                user_hash = OlivaDiceCore.userConfig.getUserHash(
                    plugin_event.data.user_id,
                    'user',
                    plugin_event.platform['platform']
                )
                return bool(OlivaDiceCore.ordinaryInviteManager.isInMasterList(
                    plugin_event.bot_info.hash,
                    user_hash
                ))
            except Exception:
                return False

        return False

    @classmethod
    def is_group_admin(cls, plugin_event):
        """
        判断当前用户是否为群主/群管
        """
        try:
            role = plugin_event.data.sender.get('role')
            return role in ['owner', 'admin', 'sub_admin']
        except Exception:
            return False

    @classmethod
    def can_manage_plugin(cls, plugin_event, scope='group'):
        """
        判断当前用户是否可以管理插件开关
        - 分群：群主/群管/骰主/配置骰主
        - 全局：骰主/配置骰主
        """
        is_config_master = cls.is_config_master(plugin_event)

        is_dice_master = cls.is_dice_master(plugin_event)
        if scope == 'global':
            return is_dice_master or is_config_master

        return cls.is_group_admin(plugin_event) or is_dice_master or is_config_master

    @classmethod
    def parse_control_command(cls, message_content):
        """
        解析插件开关控制命令
        """
        if not isinstance(message_content, str):
            return None

        normalized = message_content.strip()
        if normalized.startswith('.'):
            normalized = normalized[1:].strip()
        elif normalized.startswith('。'):
            normalized = normalized[1:].strip()

        if not normalized.startswith('点歌'):
            return None

        rest = normalized[2:].strip()
        if not rest:
            return None

        parts = rest.split()
        if not parts:
            return None

        scope = 'group'
        action = None

        if parts[0] in ['全局', 'global']:
            scope = 'global'
            if len(parts) < 2:
                return {'scope': scope, 'action': None}
            action = parts[1].strip().lower()
        else:
            action = parts[0].strip().lower()

        action_map = {
            'on': 'on',
            '开启': 'on',
            '开': 'on',
            'off': 'off',
            '关闭': 'off',
            '关': 'off',
            'status': 'status',
            '状态': 'status',
        }

        mapped_action = action_map.get(action)
        if mapped_action is None:
            return None

        return {
            'scope': scope,
            'action': mapped_action
        }

    @classmethod
    def handle_control_command(cls, plugin_event, Proc, message_content, bot_hash):
        """
        处理插件 on/off/status 控制命令
        """
        control = cls.parse_control_command(message_content)
        if control is None:
            return False

        action = control.get('action')
        scope = control.get('scope', 'group')

        if not cls.can_manage_plugin(plugin_event, scope=scope):
            if scope == 'global':
                plugin_event.reply('权限不足：仅骰主或配置骰主可控制点歌插件全局开关')
            else:
                plugin_event.reply('权限不足：仅群主、群管、骰主或配置骰主可控制本群点歌开关')
            return True

        if scope == 'global':
            target_config = cls.config
            target_name = '点歌插件全局状态'
            save_func = lambda data: load.save_json_config('config.json', data, bot_hash=bot_hash)
        else:
            group_id = cls.get_group_id(plugin_event)
            if group_id is None:
                plugin_event.reply('当前不是群聊环境，分群开关不可用；如需控制请使用【.点歌 全局 on/off】')
                return True
            target_config = load.load_group_config(group_id, bot_hash=bot_hash, default=load.get_default_group_config())
            target_name = f"点歌插件群({group_id})状态"
            save_func = lambda data: load.save_group_config(group_id, data, bot_hash=bot_hash)

        if action == 'status':
            plugin_event.reply(f"{target_name}：{'开启' if target_config.get('enabled', True) else '关闭'}")
            return True

        target_config['enabled'] = (action == 'on')
        save_func(target_config)

        if scope == 'global':
            cls.config = target_config
            cls.DEBUG_MODE = cls.config.get('debug_mode', False)

        plugin_event.reply(f"{target_name}已{'开启' if target_config['enabled'] else '关闭'}")
        Proc.log(2, f">>> {target_name}已设置为: {'开启' if target_config['enabled'] else '关闭'}", [])
        return True

    @classmethod
    def is_group_enabled(cls, plugin_event, bot_hash):
        """
        获取当前群级开关状态；无群聊上下文则默认开启
        """
        group_id = cls.get_group_id(plugin_event)
        if group_id is None:
            return True
        group_config = load.load_group_config(group_id, bot_hash=bot_hash, default=load.get_default_group_config())
        return bool(group_config.get('enabled', True))

    @classmethod
    def normalize_song_list(cls, result):
        """
        统一整理 API 返回结果，兼容 name 搜索与 id 查询
        """
        data = result.get('data', [])
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            return [data]
        return []
    
    @classmethod
    def handle_message(cls, plugin_event, Proc, is_group):
        """
        处理消息的主方法
        :param plugin_event: 插件事件对象
        :param Proc: 进程对象
        :param is_group: 是否为群聊
        """
        # 重新加载配置，确保使用最新的配置（按 bot 隔离）
        bot_hash = getattr(plugin_event.bot_info, 'hash', None)
        cls.reload_config_for_bot(bot_hash)

        # 获取消息内容
        message_content = plugin_event.data.message.strip()

        # 插件独立开关控制命令（默认分群，.点歌 全局 on/off 控制全局）
        if cls.handle_control_command(plugin_event, Proc, message_content, bot_hash):
            return
        
        # 检查插件全局是否启用
        if not cls.config.get('enabled', True):
            return

        # 检查当前群是否启用（一个群一个文件）
        if not cls.is_group_enabled(plugin_event, bot_hash):
            return

        # 若存在 OlivaDiceCore，则遵循其 bot on/off 开关
        if not cls.is_enabled_for_context(plugin_event):
            return
        
        # 检查是否为点歌指令
        if not message_content.startswith('.点歌') and not message_content.startswith('。点歌'):
            return
        
        # 提取歌曲名称
        song_name = message_content[3:].strip()
        
        if not song_name:
            plugin_event.reply("请输入歌曲名称，例如：【.点歌爱不会绝迹】或【。点歌爱不会绝迹】")
            return
        
        cls.debug_log(Proc, f"收到点歌指令，歌曲名称: {song_name}")
        
        # 设置当前进程对象
        cls.current_Proc = Proc
        
        # 搜索歌曲
        Proc.log(2, f">>> 正在搜索歌曲: {song_name}", [])
        result = cls.get_song_result(song_name, Proc)
        
        if not result:
            plugin_event.reply("搜索失败，请稍后重试")
            return
        
        # 检查返回结果
        if result.get('code') != 0:
            cls.debug_log(Proc, f"API 返回错误: {result.get('message', '未知错误')}")
            plugin_event.reply(f"搜索失败: {result.get('message', '未知错误')}")
            return
        
        # 获取歌曲列表
        song_list = cls.normalize_song_list(result)
        
        if not song_list or len(song_list) == 0:
            Proc.log(2, f">>> 未查询到对应歌曲: {song_name}", [])
            plugin_event.reply("未查询到对应歌曲")
            return
        
        # 取第一条结果
        first_song = song_list[0]
        cls.debug_log(Proc, f"找到歌曲: {first_song.get('name', '')} - {[s.get('name', '') for s in first_song.get('singers', [])]}")
        
        # 构建 CQ 码
        cq_music = cls.build_cq_music(first_song)
        
        # 返回结果
        Proc.log(2, f">>> 成功返回歌曲: {first_song.get('name', '')}", [])
        plugin_event.reply(cq_music)


# 事件处理类
class Event(object):
    """
    事件处理类，用于处理各种事件
    """
    
    @staticmethod
    def init(plugin_event, Proc):
        """
        插件初始化事件
        :param plugin_event: 插件事件对象
        :param Proc: 进程对象
        """
        MusicSearchProcessor.init(Proc)
    
    @staticmethod
    def group_message(plugin_event, Proc):
        """
        群聊消息事件处理
        :param plugin_event: 插件事件对象
        :param Proc: 进程对象
        """
        MusicSearchProcessor.handle_message(plugin_event, Proc, is_group=True)
    
    @staticmethod
    def private_message(plugin_event, Proc):
        """
        私聊消息事件处理
        :param plugin_event: 插件事件对象
        :param Proc: 进程对象
        """
        MusicSearchProcessor.handle_message(plugin_event, Proc, is_group=False)

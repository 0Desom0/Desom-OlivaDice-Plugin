# -*- encoding=utf8 -*-

import os
import json
from threading import Lock

oliva_dice_core_available = False
try:
    import OlivaDiceCore
    oliva_dice_core_available = True
except Exception:
    oliva_dice_core_available = False

# 数据目录设置
# 不使用 __file__ 向上回溯，避免插件被加载到 plugin/tmp 时把数据写进临时目录。
data_dir = os.path.join('plugin', 'data', 'MusicSearch')
os.makedirs(data_dir, exist_ok=True)
file_lock = Lock()

# 全局配置变量
global_config = {}

def get_redirected_bot_hash(bot_hash):
    """
    遵循 OlivaDiceCore 主从账号链接：从账号读写主账号目录
    """
    if oliva_dice_core_available and bot_hash:
        try:
            master = OlivaDiceCore.console.getMasterBotHash(bot_hash)
            if master:
                return str(master)
        except Exception:
            pass
    return str(bot_hash) if bot_hash is not None else 'default'

def get_bot_conf_hash(bot_hash):
    """
    获取 bot 对应的配置目录名
    对于 OlivaDiceCore，仅遵循主从账号链接，仍然使用 bot hash 体系
    """
    redirected_hash = get_redirected_bot_hash(bot_hash)
    return redirected_hash or 'default'

def get_data_dir(bot_hash=None):
    """
    获取 bot 级别的数据目录
    """
    if bot_hash is None:
        path = data_dir
    else:
        path = os.path.join(data_dir, get_bot_conf_hash(bot_hash))
    os.makedirs(path, exist_ok=True)
    return path

def get_group_dir(bot_hash=None):
    """
    获取 bot 级别的群配置目录
    """
    path = os.path.join(get_data_dir(bot_hash), 'groups')
    os.makedirs(path, exist_ok=True)
    return path

def get_group_config_file(group_id, bot_hash=None):
    """
    获取群配置文件路径；一个群一个文件，仅使用群号
    """
    return os.path.join(get_group_dir(bot_hash), f"{str(group_id).strip()}.json")

# 配置文件操作函数
def load_json_config(filename, default=None, bot_hash=None):
    """
    加载 JSON 配置文件
    :param filename: 文件名
    :param default: 默认值
    :param bot_hash: bot 哈希，用于按 bot 分配置
    :return: 配置数据
    """
    global global_config
    file_path = os.path.join(get_data_dir(bot_hash), filename)
    
    if not os.path.exists(file_path):
        save_json_config(filename, default, bot_hash=bot_hash)
        global_config = default.copy() if default else {}
        return global_config
    
    with file_lock:
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                global_config = json.load(f)
                if isinstance(global_config, dict):
                    default_cfg = get_default_config() if filename == 'config.json' else {}
                    for key, value in default_cfg.items():
                        if key not in global_config:
                            global_config[key] = value
                    if 'masters' in global_config and not isinstance(global_config.get('masters'), list):
                        global_config['masters'] = []
                return global_config
        except Exception as e:
            print(f"加载配置文件失败：{e}")
            global_config = default.copy() if default else {}
            return global_config

def save_json_config(filename, data, bot_hash=None):
    """
    保存 JSON 配置文件
    :param filename: 文件名
    :param data: 配置数据
    :param bot_hash: bot 哈希，用于按 bot 分配置
    """
    global global_config
    file_path = os.path.join(get_data_dir(bot_hash), filename)
    with file_lock:
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        # 更新全局配置
        global_config = data.copy()

def load_group_config(group_id, bot_hash=None, default=None):
    """
    加载群配置文件
    """
    if default is None:
        default = get_default_group_config()

    file_path = get_group_config_file(group_id, bot_hash=bot_hash)
    if not os.path.exists(file_path):
        save_group_config(group_id, default, bot_hash=bot_hash)
        return default.copy()

    with file_lock:
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                if isinstance(data, dict):
                    return data
        except Exception as e:
            print(f"加载群配置文件失败：{e}")

    return default.copy()

def save_group_config(group_id, data, bot_hash=None):
    """
    保存群配置文件
    """
    file_path = get_group_config_file(group_id, bot_hash=bot_hash)
    with file_lock:
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

def get_default_config():
    """
    获取默认配置
    :return: 默认配置字典
    """
    return {
        "enabled": True,  # 是否启用
        "debug_mode": False,  # 调试模式开关
        "masters": []  # 配置骰主（按 bot 隔离）
    }

def get_default_group_config():
    """
    获取群级配置
    """
    return {
        "enabled": True
    }

def init_config(bot_hash=None):
    """
    初始化配置
    :return: 配置数据
    """
    get_group_dir(bot_hash=bot_hash)
    return load_json_config('config.json', default=get_default_config(), bot_hash=bot_hash)

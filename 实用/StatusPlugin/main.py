from .status_report import build_status_report, parse_status_command
import OlivOS
# 如果存在 OlivaDiceCore 插件，则按 OlivaDice 的常用初始化与权限检查流程处理
_has_olivadice = False
try:
    import OlivaDiceCore  # type: ignore
    _has_olivadice = True
except Exception:
    _has_olivadice = False

gProc = None

gPluginName = 'StatusPlugin'


class Event(object):
    def init(plugin_event, Proc):
        # 初始化流程
        pass

    def init_after(plugin_event, Proc):
        # 初始化后处理流程
        # 区别是前面的初始化流程不基于优先级
        # 而本流程基于优先级
        global gProc
        gProc = Proc
        # 不再在此处注册触发词；运行时遵循 OlivaDice 的 bot on/off 开关

    def private_message(plugin_event, Proc):
        # 私聊消息事件入口
        unity_reply(plugin_event, Proc)

    def group_message(plugin_event, Proc):
        # 群消息事件入口
        unity_reply(plugin_event, Proc)

    def save(plugin_event, Proc):
        # 插件卸载时执行的保存流程
        pass


def unity_reply(plugin_event, Proc):
    # 被动回复消息示例

    if _has_olivadice:
        try:
            tmp_reast_str = plugin_event.data.message
            tmp_reast_str = OlivaDiceCore.msgReply.to_half_width(tmp_reast_str)

            tmp_id_str = str(plugin_event.base_info['self_id'])
            tmp_id_str_sub = None
            if 'sub_self_id' in plugin_event.data.extend and plugin_event.data.extend['sub_self_id'] is not None:
                tmp_id_str_sub = str(plugin_event.data.extend['sub_self_id'])

            # 检查是否被 at 强制回复
            flag_force_reply = False
            tmp_reast_obj = OlivOS.messageAPI.Message_templet('olivos_string', tmp_reast_str)
            tmp_at_list: list[str] = []
            for tmp_reast_obj_this in tmp_reast_obj.data:
                tmp_para_str_this = tmp_reast_obj_this.OP()
                if type(tmp_reast_obj_this) is OlivOS.messageAPI.PARA.at:
                    tmp_at_list.append(str(tmp_reast_obj_this.data['id']))
                    tmp_reast_str = tmp_reast_str.lstrip(tmp_para_str_this)
                elif type(tmp_reast_obj_this) is OlivOS.messageAPI.PARA.text:
                    if tmp_para_str_this.strip(' ') == '':
                        tmp_reast_str = tmp_reast_str.lstrip(tmp_para_str_this)
                        pass
                    else:
                        break
                else:
                    break
            if tmp_id_str in tmp_at_list or tmp_id_str_sub in tmp_at_list or 'all' in tmp_at_list:
                flag_force_reply = True
                tmp_reast_str = OlivaDiceCore.msgReply.skipSpaceStart(tmp_reast_str)
            # 判断是否为命令
            msgIsCommand = OlivaDiceCore.msgReply.msgIsCommand
            tmp_reast_str, flag_is_command = msgIsCommand(tmp_reast_str, OlivaDiceCore.crossHook.dictHookList['prefix'])
            if flag_is_command:
                flag_is_from_group = plugin_event.plugin_info['func_type'] == 'group_message'
                flag_is_from_host = False
                if flag_is_from_group and plugin_event.data.host_id is not None:
                    flag_is_from_host = True

                tmp_hagID = None
                if flag_is_from_host and flag_is_from_group:
                    tmp_hagID = f"{plugin_event.data.host_id}|{plugin_event.data.group_id}"
                elif flag_is_from_group:
                    tmp_hagID = str(plugin_event.data.group_id)

                # 检查开关
                flag_hostLocalEnable = True
                if flag_is_from_host:
                    flag_hostLocalEnable = OlivaDiceCore.userConfig.getUserConfigByKey(
                        userId=plugin_event.data.host_id,
                        userType='host',
                        platform=plugin_event.platform['platform'],
                        userConfigKey='hostLocalEnable',
                        botHash=plugin_event.bot_info.hash,
                    )

                flag_groupEnable = True
                if flag_is_from_group and tmp_hagID is not None:
                    flag_groupEnable = OlivaDiceCore.userConfig.getUserConfigByKey(
                        userId=tmp_hagID,
                        userType='group',
                        platform=plugin_event.platform['platform'],
                        userConfigKey='groupEnable',
                        botHash=plugin_event.bot_info.hash,
                    )
                pass
                if not flag_hostLocalEnable and not flag_force_reply:
                    return
                if not flag_groupEnable and not flag_force_reply:
                    return
        except Exception:
            # 出错则忽略 OlivaDice 检查
            pass
    status_cmd = parse_status_command(message=tmp_reast_str, self_id=str(plugin_event.base_info['self_id']))
    if status_cmd is not None:
        plugin_event.reply(build_status_report())
        plugin_event.set_block()
        return

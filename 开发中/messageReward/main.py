import OlivOS

class Event(object):
    def init(plugin_event, Proc):
        pass

    def group_message(plugin_event, Proc):
        unity_reply(plugin_event, Proc)

def unity_reply(plugin_event, Proc):
    is_reply_flag = False
    is_at_self_flag = False
    is_delete_flag = False
    message_id = None
    tmp_reast_str = plugin_event.data.message
    tmp_id_str = str(plugin_event.base_info['self_id'])
    tmp_id_str_sub = None
    
    if 'sub_self_id' in plugin_event.data.extend:
        if plugin_event.data.extend['sub_self_id'] is not None:
            tmp_id_str_sub = str(plugin_event.data.extend['sub_self_id'])
    
    # 检测回复标识
    if isMatchWordStart(tmp_reast_str, '[OP:reply,id='):
        message_id = extractMessageId(tmp_reast_str)
        end_pos = tmp_reast_str.find(']')
        if end_pos != -1:
            tmp_reast_str = tmp_reast_str[end_pos + 1:]
        is_reply_flag = True
        tmp_reast_str = tmp_reast_str.strip()
    
    # 检测多个at标识 - 检查是否at了机器人，并移除所有at标识
    message_parts = tmp_reast_str
    while '[OP:at,id=' in message_parts:
        # 找到at标识的起始位置
        at_start = message_parts.find('[OP:at,id=')
        if at_start == -1:
            break
        # 提取at的id
        id_start = at_start + len('[OP:at,id=')
        at_end = message_parts.find(']', id_start)
        if at_end == -1:
            break
        # 提取完整的at内容
        at_content = message_parts[id_start:at_end]
        comma_pos = at_content.find(',')
        if comma_pos != -1:
            at_id = at_content[:comma_pos]
        else:
            at_id = at_content
        # 检查是否at的是机器人自己
        if at_id == tmp_id_str or (tmp_id_str_sub and at_id == tmp_id_str_sub):
            is_at_self_flag = True
        # 继续检查下一个at
        message_parts = message_parts[at_end + 1:]
    
    # 移除所有at标识
    while '[OP:at,id=' in tmp_reast_str:
        at_start_in_original = tmp_reast_str.find('[OP:at,id=')
        at_end_in_original = tmp_reast_str.find(']', at_start_in_original)
        if at_start_in_original != -1 and at_end_in_original != -1:
            tmp_reast_str = tmp_reast_str[:at_start_in_original] + tmp_reast_str[at_end_in_original + 1:]
            tmp_reast_str = tmp_reast_str.strip()
        else:
            break
    
    # 双标识都有执行撤回
    if isMatchWordStart(tmp_reast_str, '转发') and is_reply_flag is True and is_at_self_flag is True:
        msg = plugin_event.get_msg(message_id)
        reward_msg = msg.get('data')
        print(f"完整msg内容: {msg}")

def skipSpaceStart(data):
    tmp_output_str = ''
    if len(data) > 0:
        flag_have_para = False
        tmp_offset = 0
        tmp_total_offset = 0
        while True:
            tmp_offset += 1
            tmp_total_offset = tmp_offset - 1
            if tmp_total_offset >= len(data):
                break
            if data[tmp_total_offset] != ' ':
                flag_have_para = True
                break
        if flag_have_para:
            tmp_output_str = data[tmp_total_offset:]
    return tmp_output_str

def skipToRight(data, key):
    tmp_output_str = ''
    if len(data) > 0:
        flag_have_para = False
        tmp_offset = 0
        tmp_total_offset = 0
        while True:
            tmp_offset += 1
            tmp_total_offset = tmp_offset - 1
            if tmp_total_offset >= len(data):
                break
            if data[tmp_total_offset] == key:
                flag_have_para = True
                break
        if flag_have_para:
            tmp_output_str = data[tmp_total_offset:]
    return tmp_output_str

def isMatchWordStart(data, key, ignoreCase=True, fullMatch=False, isCommand=False):
    tmp_output = False
    flag_skip = False
    tmp_data = data.strip()
    tmp_keys = [key] if isinstance(key, str) else key
    if not flag_skip:
        if ignoreCase:
            tmp_data = tmp_data.lower()
            tmp_keys = [k.lower() for k in tmp_keys]
        # 按长度从长到短排序
        tmp_keys_sorted = sorted(tmp_keys, key=lambda x: len(x), reverse=True)
        for tmp_key in tmp_keys_sorted:
            if not fullMatch and len(tmp_data) >= len(tmp_key):
                if tmp_data[:len(tmp_key)] == tmp_key:
                    tmp_output = True
                    break
            elif fullMatch and tmp_data == tmp_key:
                tmp_output = True
                break
    return tmp_output

def getMatchWordStartRight(data, key, ignoreCase=True):
    tmp_output_str = ''
    tmp_data = data
    tmp_keys = [key] if isinstance(key, str) else key
    if ignoreCase:
        tmp_data = tmp_data.lower()
        tmp_keys = [k.lower() for k in tmp_keys]
    # 按长度从长到短排序
    tmp_keys_sorted = sorted(tmp_keys, key=lambda x: len(x), reverse=True)
    for tmp_key in tmp_keys_sorted:
        if len(tmp_data) > len(tmp_key):
            if tmp_data[:len(tmp_key)] == tmp_key:
                tmp_output_str = data[len(tmp_key):]
                break
    return tmp_output_str

def extractMessageId(reply_str):
    if not reply_str.startswith('[OP:reply,id='):
        return None
    start_pos = len('[OP:reply,id=')
    end_pos = reply_str.find(']', start_pos)
    comma_pos = reply_str.find(',', start_pos)
    if comma_pos != -1 and comma_pos < end_pos:
        end_pos = comma_pos
    
    if end_pos == -1:
        return None
    
    message_id = reply_str[start_pos:end_pos]
    return message_id.strip()


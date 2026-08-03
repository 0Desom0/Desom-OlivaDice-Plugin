# -*- encoding: utf-8 -*-
'''
电所有人前列腺图片生成器
'''

import OlivOS
import qianliexian
import OlivaDiceCore
import os
import time
import hashlib
import base64
from PIL import Image, ImageDraw, ImageFont, ImageFilter


# 数据路径配置
BASE_IMAGE_PATH = "data/images/qianliexian/电所有人前列腺_底图.png"
TEMP_DIR = "data/images/qianliexian/temp"
MAX_TEMP_FILES = 20

def release_base_image(Proc):
    """释放底图到指定路径"""
    try:
        # 如果底图已存在,不重复释放
        if os.path.exists(BASE_IMAGE_PATH):
            return
        
        # 确保目录存在
        os.makedirs(os.path.dirname(BASE_IMAGE_PATH), exist_ok=True)
        
        # 从imageData模块导入底图数据
        from . import imageData
        
        # 解码base64数据
        image_data = base64.b64decode(imageData.BASE_IMAGE_DATA)
        
        # 写入文件
        with open(BASE_IMAGE_PATH, 'wb') as f:
            f.write(image_data)
        
        Proc.log(2,f"[qianliexian] 底图已自动释放到: {BASE_IMAGE_PATH}")
    except Exception as e:
        Proc.log(2,f"[qianliexian] 释放底图失败: {e}")

def unity_init(plugin_event, Proc):
    """插件初始化"""
    # 确保目录存在
    os.makedirs(os.path.dirname(BASE_IMAGE_PATH), exist_ok=True)
    os.makedirs(TEMP_DIR, exist_ok=True)
    
    # 释放底图
    release_base_image(Proc)

def data_init(plugin_event, Proc):
    """数据初始化"""
    qianliexian.msgCustomManager.initMsgCustom(Proc.Proc_data['bot_info_dict'])

def clean_temp_folder(Proc):
    """清理temp文件夹,保持文件数不超过20"""
    try:
        files = []
        for f in os.listdir(TEMP_DIR):
            if f.endswith('.png'):
                file_path = os.path.join(TEMP_DIR, f)
                files.append((file_path, os.path.getctime(file_path)))
        
        # 按创建时间排序
        files.sort(key=lambda x: x[1])
        
        # 如果超过20个,删除最早的
        while len(files) >= MAX_TEMP_FILES:
            os.remove(files[0][0])
            files.pop(0)
    except Exception as e:
        Proc.log(2,f"清理临时文件夹失败: {e}")

def create_gradient_stroke(text, font, base_color, start_color, end_color, stroke_width):
    """创建渐变描边效果"""
    # 创建临时图像来绘制文字
    temp_size = (800, 200)
    temp_img = Image.new('RGBA', temp_size, (0, 0, 0, 0))
    temp_draw = ImageDraw.Draw(temp_img)
    
    # 获取文字边界框
    bbox = temp_draw.textbbox((0, 0), text, font=font)
    text_width = bbox[2] - bbox[0]
    text_height = bbox[3] - bbox[1]
    
    # 创建最终图像(考虑描边宽度)
    final_size = (text_width + stroke_width * 4, text_height + stroke_width * 4)
    final_img = Image.new('RGBA', final_size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(final_img)
    
    center_x = stroke_width * 2
    center_y = stroke_width * 2 - bbox[1]
    
    # 绘制多层描边创建渐变效果
    for i in range(stroke_width, 0, -1):
        # 计算当前层的颜色(从start_color到end_color渐变)
        ratio = (stroke_width - i) / stroke_width
        r = int(start_color[0] + (end_color[0] - start_color[0]) * ratio)
        g = int(start_color[1] + (end_color[1] - start_color[1]) * ratio)
        b = int(start_color[2] + (end_color[2] - start_color[2]) * ratio)
        color = (r, g, b, 255)
        
        # 绘制描边
        draw.text((center_x, center_y), text, font=font, fill=color, stroke_width=i)
    
    # 绘制白色文字
    draw.text((center_x, center_y), text, font=font, fill=base_color)
    
    return final_img

def generate_image(Proc, text, dictStrCustom):
    """生成电前列腺图片"""
    try:
        # 检查底图是否存在
        if not os.path.exists(BASE_IMAGE_PATH):
            return None, dictStrCustom['strQlxNoBase']
        
        # 打开底图
        base_img = Image.open(BASE_IMAGE_PATH).convert('RGBA')
        
        # 文字区域的四个顶点
        left_top = (98, 354)      
        left_bottom = (110, 390)  
        right_top = (371, 307)    
        right_bottom = (397, 319) 
        
        # 计算中心线(从左中点到右中点)
        left_mid_x = (left_top[0] + left_bottom[0]) / 2
        left_mid_y = (left_top[1] + left_bottom[1]) / 2
        right_mid_x = (right_top[0] + right_bottom[0]) / 2
        right_mid_y = (right_top[1] + right_bottom[1]) / 2
        
        # 文字长度
        text_len = len(text)
        
        # 固定字体大小
        fixed_font_size = 40
        
        # 加载字体
        try:
            font = ImageFont.truetype("C:/Windows/Fonts/simsun.ttc", fixed_font_size)
        except:
            try:
                font = ImageFont.truetype("C:/Windows/Fonts/simhei.ttf", fixed_font_size)
            except:
                try:
                    font = ImageFont.truetype("C:/Windows/Fonts/msyh.ttc", fixed_font_size)
                except:
                    font = ImageFont.load_default()
        
        # 固定间距10像素
        spacing = 2
        
        # 获取字符宽度(用于计算偏移)
        temp_draw = ImageDraw.Draw(Image.new('RGBA', (1, 1)))
        test_bbox = temp_draw.textbbox((0, 0), "测", font=font)
        char_width = test_bbox[2] - test_bbox[0]
        
        # 渐变描边颜色
        start_color = (23, 15, 108) 
        end_color = (0, 0, 0)  # 黑色
        base_color = (255, 255, 255, 255)  # 白色
        stroke_width = 4  # 加粗描边
        
        # 创建一个用于叠加文字的透明层
        text_layer = Image.new('RGBA', base_img.size, (0, 0, 0, 0))
        
        # 计算旋转角度(文字沿着中心线倾斜)
        import math
        angle = math.degrees(math.atan2(right_mid_y - left_mid_y, right_mid_x - left_mid_x))
        
        # 计算起始位置(从中心线的中点开始,往两边排列)
        center_x = (left_mid_x + right_mid_x) / 2
        center_y = (left_mid_y + right_mid_y) / 2
        
        # 从中心往外排列字符
        current_offset = 0
        char_positions = []
        
        # 第一遍:计算每个字符的实际宽度和间距
        for i, char in enumerate(text):
            # 获取当前字符的实际宽度
            char_bbox = temp_draw.textbbox((0, 0), char, font=font)
            actual_char_width = char_bbox[2] - char_bbox[0]
            
            # 判断当前字符是否为英文字母或数字
            is_current_alnum = char.isalnum() and ord(char) < 128
            
            # 判断是否为中文字符(用于计算字符宽度权重)
            is_chinese = ord(char) > 127 and not char.isalnum()
            
            # 中文字符算2倍宽度
            if is_chinese:
                actual_char_width = actual_char_width * 2
            
            # 计算当前字符后面的间距(基于当前字符和下一个字符的关系)
            if i < len(text) - 1:  # 如果不是最后一个字符
                next_char = text[i + 1]
                # 判断下一个字符是否为英文字母或数字
                is_next_alnum = next_char.isalnum() and ord(next_char) < 128
                # 判断下一个字符是否为中文
                is_next_chinese = ord(next_char) > 127
                
                # 只有当前和下一个字符都是英文字母/数字时,才使用英文间距
                # 否则(包括符号、中文等)就使用中文间距
                if is_current_alnum and is_next_alnum:
                    char_spacing = spacing * 0.4  # 英文字母/数字→英文字母/数字:使用英文间距
                else:
                    char_spacing = spacing  # 其他情况:使用标准中文间距
                
                # 如果当前是英文,下一个是中文,额外添加0.8倍空格宽度
                if is_current_alnum and is_next_chinese:
                    space_bbox = temp_draw.textbbox((0, 0), " ", font=font)
                    space_width = space_bbox[2] - space_bbox[0]
                    char_spacing += space_width * 0.9
            else:
                char_spacing = 0  # 最后一个字符不需要间距
            
            char_positions.append({
                'char': char,
                'width': actual_char_width,
                'spacing': char_spacing,
                'offset': current_offset
            })
            
            # 累加偏移(字符宽度+间距)
            current_offset += actual_char_width + char_spacing
        
        # 计算总宽度
        total_width = current_offset - char_positions[-1]['spacing']  # 最后一个字符不需要间距
        
        # 第二遍:根据计算好的位置绘制字符
        for i, pos_info in enumerate(char_positions):
            char = pos_info['char']
            # 计算相对于中心的偏移(从中心向两边展开)
            offset = pos_info['offset'] - total_width / 2
            
            # 沿着倾斜线计算位置
            char_x = center_x + offset * math.cos(math.radians(angle))
            char_y = center_y + offset * math.sin(math.radians(angle))
            
            # 创建带渐变描边的单个字符
            char_img = create_gradient_stroke(char, font, base_color, start_color, end_color, stroke_width)
            
            # 旋转字符图像(沿着中心线倾斜)
            try:
                # 使用新的API
                from PIL.Image import Resampling
                char_img_rotated = char_img.rotate(-angle, expand=True, resample=Resampling.BICUBIC)
            except:
                # 兼容旧版本PIL
                char_img_rotated = char_img.rotate(-angle, expand=True, resample=Image.BICUBIC)
            
            # 获取旋转后字符图像大小
            rotated_width, rotated_height = char_img_rotated.size
            
            # 计算粘贴位置(居中)
            paste_x = int(char_x - rotated_width // 2)
            paste_y = int(char_y - rotated_height // 2)
            
            # 对单个字符应用模糊
            char_img_blurred = char_img_rotated.filter(ImageFilter.GaussianBlur(radius=0.3))
            
            # 将模糊后的字符图像粘贴到文字层
            text_layer.paste(char_img_blurred, (paste_x, paste_y), char_img_blurred)
        
        # 对整个文字层再次应用模糊
        text_layer = text_layer.filter(ImageFilter.GaussianBlur(radius=0.8))
        
        # 合并文字层到底图
        base_img = Image.alpha_composite(base_img, text_layer)
        
        # 生成文件名
        timestamp = str(int(time.time() * 1000))
        text_hash = hashlib.md5(text.encode('utf-8')).hexdigest()[:8]
        filename = f"qianliexian_{timestamp}_{text_hash}.png"
        filepath = os.path.join(TEMP_DIR, filename)
        
        # 保存图片
        base_img.save(filepath, 'PNG')
        
        # 清理旧文件
        clean_temp_folder(Proc)
        
        # 返回CQ码路径
        cq_path = f"qianliexian\\temp\\{filename}"
        return cq_path, None
        
    except Exception as e:
        dictTValue = {'tError': str(e)}
        error_msg = OlivaDiceCore.msgCustomManager.formatReplySTR(dictStrCustom['strQlxError'], dictTValue)
        return None, error_msg

def unity_reply(plugin_event, Proc):
    """消息处理"""
    OlivaDiceCore.userConfig.setMsgCount()
    dictTValue = OlivaDiceCore.msgCustom.dictTValue.copy()
    dictTValue['tUserName'] = plugin_event.data.sender['name']
    dictTValue['tName'] = plugin_event.data.sender['name']
    dictStrCustom = OlivaDiceCore.msgCustom.dictStrCustomDict[plugin_event.bot_info.hash]
    dictGValue = OlivaDiceCore.msgCustom.dictGValue
    dictTValue.update(dictGValue)
    dictTValue = OlivaDiceCore.msgCustomManager.dictTValueInit(plugin_event, dictTValue)

    valDict = {}
    valDict['dictTValue'] = dictTValue
    valDict['dictStrCustom'] = dictStrCustom
    valDict['tmp_platform'] = plugin_event.platform['platform']

    replyMsg = OlivaDiceCore.msgReply.replyMsg
    isMatchWordStart = OlivaDiceCore.msgReply.isMatchWordStart
    getMatchWordStartRight = OlivaDiceCore.msgReply.getMatchWordStartRight
    skipSpaceStart = OlivaDiceCore.msgReply.skipSpaceStart
    skipToRight = OlivaDiceCore.msgReply.skipToRight
    msgIsCommand = OlivaDiceCore.msgReply.msgIsCommand

    tmp_at_str = OlivOS.messageAPI.PARA.at(plugin_event.base_info['self_id']).CQ()
    tmp_id_str = str(plugin_event.base_info['self_id'])
    tmp_at_str_sub = None
    tmp_id_str_sub = None
    tmp_id_str_sub_open = None
    if 'sub_self_id' in plugin_event.data.extend:
        if plugin_event.data.extend['sub_self_id'] != None:
            tmp_at_str_sub = OlivOS.messageAPI.PARA.at(plugin_event.data.extend['sub_self_id']).CQ()
            tmp_id_str_sub = str(plugin_event.data.extend['sub_self_id'])
    if 'sub_self_open_id' in plugin_event.data.extend:
        if plugin_event.data.extend['sub_self_open_id'] != None:
            tmp_id_str_sub_open = str(plugin_event.data.extend['sub_self_open_id'])
    tmp_command_str_1 = '.'
    tmp_command_str_2 = '。'
    tmp_command_str_3 = '/'
    tmp_reast_str = plugin_event.data.message
    flag_force_reply = False
    flag_is_command = False
    flag_is_from_host = False
    flag_is_from_group = False
    flag_is_from_group_admin = False
    flag_is_from_group_have_admin = False
    flag_is_from_master = False
    
    if isMatchWordStart(tmp_reast_str, '[CQ:reply,id='):
        tmp_reast_str = skipToRight(tmp_reast_str, ']')
        tmp_reast_str = tmp_reast_str[1:]
    
    if flag_force_reply is False:
        tmp_reast_str_old = tmp_reast_str
        tmp_reast_obj = OlivOS.messageAPI.Message_templet(
            'old_string',
            tmp_reast_str
        )
        tmp_at_list = []
        for tmp_reast_obj_this in tmp_reast_obj.data:
            tmp_para_str_this = tmp_reast_obj_this.CQ()
            if type(tmp_reast_obj_this) is OlivOS.messageAPI.PARA.at:
                tmp_at_list.append(str(tmp_reast_obj_this.data['id']))
                tmp_reast_str = tmp_reast_str.lstrip(tmp_para_str_this)
            elif type(tmp_reast_obj_this) is OlivOS.messageAPI.PARA.text:
                if tmp_para_str_this.strip(' ') == '':
                    tmp_reast_str = tmp_reast_str.lstrip(tmp_para_str_this)
                else:
                    break
            else:
                break
        if tmp_id_str in tmp_at_list:
            flag_force_reply = True
        if tmp_id_str_sub in tmp_at_list:
            flag_force_reply = True
        if tmp_id_str_sub_open in tmp_at_list:
            flag_force_reply = True
        if 'all' in tmp_at_list:
            flag_force_reply = True
        if flag_force_reply is True:
            tmp_reast_str = skipSpaceStart(tmp_reast_str)
        else:
            tmp_reast_str = tmp_reast_str_old
    
    [tmp_reast_str, flag_is_command] = msgIsCommand(
        tmp_reast_str,
        OlivaDiceCore.crossHook.dictHookList['prefix']
    )
    
    if flag_is_command:
        tmp_hostID = None
        tmp_hagID = None
        tmp_userID = plugin_event.data.user_id
        valDict['tmp_userID'] = tmp_userID
        tmp_list_hit = []
        flag_is_from_master = OlivaDiceCore.ordinaryInviteManager.isInMasterList(
            plugin_event.bot_info.hash,
            OlivaDiceCore.userConfig.getUserHash(
                plugin_event.data.user_id,
                'user',
                plugin_event.platform['platform']
            )
        )
        valDict['flag_is_from_master'] = flag_is_from_master
        if plugin_event.plugin_info['func_type'] == 'group_message':
            if plugin_event.data.host_id != None:
                flag_is_from_host = True
            flag_is_from_group = True
        elif plugin_event.plugin_info['func_type'] == 'private_message':
            flag_is_from_group = False
        if flag_is_from_group:
            if 'role' in plugin_event.data.sender:
                flag_is_from_group_have_admin = True
                if plugin_event.data.sender['role'] in ['owner', 'admin']:
                    flag_is_from_group_admin = True
                elif plugin_event.data.sender['role'] in ['sub_admin']:
                    flag_is_from_group_admin = True
                    flag_is_from_group_sub_admin = True
        if flag_is_from_host and flag_is_from_group:
            tmp_hagID = '%s|%s' % (str(plugin_event.data.host_id), str(plugin_event.data.group_id))
        elif flag_is_from_group:
            tmp_hagID = str(plugin_event.data.group_id)
        flag_hostEnable = True
        if flag_is_from_host:
            flag_hostEnable = OlivaDiceCore.userConfig.getUserConfigByKey(
                userId = plugin_event.data.host_id,
                userType = 'host',
                platform = plugin_event.platform['platform'],
                userConfigKey = 'hostEnable',
                botHash = plugin_event.bot_info.hash
            )
        flag_hostLocalEnable = True
        if flag_is_from_host:
            flag_hostLocalEnable = OlivaDiceCore.userConfig.getUserConfigByKey(
                userId = plugin_event.data.host_id,
                userType = 'host',
                platform = plugin_event.platform['platform'],
                userConfigKey = 'hostLocalEnable',
                botHash = plugin_event.bot_info.hash
            )
        flag_groupEnable = True
        if flag_is_from_group:
            if flag_is_from_host:
                if flag_hostEnable:
                    flag_groupEnable = OlivaDiceCore.userConfig.getUserConfigByKey(
                        userId = tmp_hagID,
                        userType = 'group',
                        platform = plugin_event.platform['platform'],
                        userConfigKey = 'groupEnable',
                        botHash = plugin_event.bot_info.hash
                    )
                else:
                    flag_groupEnable = OlivaDiceCore.userConfig.getUserConfigByKey(
                        userId = tmp_hagID,
                        userType = 'group',
                        platform = plugin_event.platform['platform'],
                        userConfigKey = 'groupWithHostEnable',
                        botHash = plugin_event.bot_info.hash
                    )
            else:
                flag_groupEnable = OlivaDiceCore.userConfig.getUserConfigByKey(
                    userId = tmp_hagID,
                    userType = 'group',
                    platform = plugin_event.platform['platform'],
                    userConfigKey = 'groupEnable',
                    botHash = plugin_event.bot_info.hash
                )
        
        # 此频道关闭时中断处理
        if not flag_hostLocalEnable and not flag_force_reply:
            return
        # 此群关闭时中断处理
        if not flag_groupEnable and not flag_force_reply:
            return
        
        # 处理命令
        if isMatchWordStart(tmp_reast_str, ['电'], isCommand = True):
            tmp_reast_str = getMatchWordStartRight(tmp_reast_str, ['电'])
            tmp_reast_str = tmp_reast_str.strip()
            
            # 检查文字是否为空
            if not tmp_reast_str:
                tmp_reply_str = OlivaDiceCore.msgCustomManager.formatReplySTR(dictStrCustom['strQlxEmpty'], dictTValue)
                replyMsg(plugin_event, tmp_reply_str)
                return
            
            # 检查文字长度(按权重计算:中文2,英文/符号1,空格0)
            char_weight = 0
            for char in tmp_reast_str:
                if char == ' ':  # 空格
                    char_weight += 0
                elif ord(char) > 127:  # 中文字符
                    char_weight += 2
                else:  # 英文字母/数字/半角符号
                    char_weight += 1
            
            if char_weight > 20:
                tmp_reply_str = OlivaDiceCore.msgCustomManager.formatReplySTR(dictStrCustom['strQlxTooLong'], dictTValue)
                replyMsg(plugin_event, tmp_reply_str)
                return
            
            # 生成图片
            cq_path, error = generate_image(Proc, tmp_reast_str, dictStrCustom)
            
            if error:
                replyMsg(plugin_event, error)
            else:
                # 发送图片
                image_cq = f"[CQ:image,file={cq_path}]"
                replyMsg(plugin_event, image_cq)
            
            return

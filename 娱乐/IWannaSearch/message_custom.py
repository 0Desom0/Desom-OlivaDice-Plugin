# -*- encoding: utf-8 -*-
"""IWannaSearch 默认回复词与 GUI 说明。"""


default_custom_message_dict = {
    'reply_help': '''【I Wanna Search】
.iw 游戏名
按游戏名称查询 I Wanna。

.iw search 游戏名
按游戏名称查询 I Wanna。

.iw id 游戏ID
按游戏 ID 精确查询 I Wanna。

.iw random [个数] [--tag=标签]
.iw rand [个数] [--tag=标签]
随机查询 I Wanna。个数默认 1，最多 10；标签可省略且至多一个。
示例：.iwrandom5--tag=needle

.iw today
获取今日 I Wanna。每个用户每天固定一次，会缓存当天结果。

.iwbot merge on/off
开启或关闭多个 rand 结果的合并转发（仅骰主/配置主人可用）。

.iw help
查看本帮助。''',
    'reply_help_hint': '可使用 {prefix}iw help 查看 I Wanna 查询帮助。',
    'reply_empty_query': '请输入要查询的 I Wanna 名称或 ID。',
    'reply_not_found': '没有查询到符合条件的 I Wanna。',
    'reply_api_error': '查询失败：{error}',
    'reply_search_result_prefix': '查询到了以下 I Wanna',
    'reply_random_result_prefix': '随机到了以下 I Wanna',
    'reply_game_metadata': '''· ID：{id}
· 标题：{title}
· 作者：{creator}
· 评分：{rating}    难度：{difficulty}
· 评分人数：{rating_count}
· 标签：{tags}
· 游戏引擎：{engine}
· 下载链接：{url}
· 文件大小：{file_size}''',
    'reply_multiple_header': '查询到了{count}个 I Wanna',
    'reply_multiple_item': '{index}. [{id}] {title}',
    'reply_multiple_footer': '请输入对应序号查询对应的 I Wanna，或输入 end/结束 退出选择。',
    'reply_page_info': '当前页数：{current_page}/{total_page}',
    'reply_result_limited_note': '找到{count}个 I Wanna，当前显示{available_count}个，可浏览{total_page}页。',
    'reply_paged_footer': '请输入对应序号查询对应的 I Wanna，或输入下一页/上一页/跳页[页数]进行翻页，或输入 end/结束 退出选择。',
    'reply_input_invalid': '请输入严格的数字序号，或输入 end/结束 退出选择。',
    'reply_paged_input_invalid': '请输入严格的数字序号，或者输入下一页/上一页/跳页[页数]进行翻页，或输入 end/结束 退出选择。',
    'reply_jump_page_empty': '请输入要跳转的页数，例如：跳页3。',
    'reply_jump_page_invalid': '页数必须是严格数字，例如：跳页3。',
    'reply_jump_page_out_of_range': '页数超出可浏览范围，当前可浏览页数：1-{total_page}。',
    'reply_random_count_invalid': '随机数量必须是 1-10 的整数。',
    'reply_random_count_too_large': '随机数量最多只能是 10。',
    'reply_today_title': '今日 I Wanna：',
    'reply_index_out_of_range': '序号超出当前可选范围，请重新输入。',
    'reply_selection_ended': '已结束本次 I Wanna 选择。',
    'reply_session_expired': '当前没有等待选择的 I Wanna 查询结果，请重新查询。',
    'reply_first_page': '当前是首页。',
    'reply_last_page': '当前是末尾页。',
    'reply_permission_denied': '权限不足：只有 OlivaDiceCore 骰主或本插件配置骰主可以执行该操作。',
    'reply_global_status': '全局启用：{global_enable}，调试模式：{global_debug}。',
    'reply_bot_status': '当前 Bot：{bot_id}，Bot 开关：{bot_enable}，合并转发：{merge_forward}。',
}


default_custom_variable_dict = {
    'iwanna_plugin_name': 'IWannaSearch',
    'iwanna_prefix_example': '.iw search Needle Space',
}


custom_message_note_dict = {
    'reply_help': '【iw help】帮助文本。',
    'reply_help_hint': '【未命中命令提示】用于提醒用户查看帮助。',
    'reply_empty_query': '【空查询】用户没有输入名称或 ID 时回复。',
    'reply_not_found': '【无结果】API 成功但没有结果时回复。',
    'reply_api_error': '【查询失败】API 或网络异常时回复。可用变量：{error}',
    'reply_search_result_prefix': '【search/id 结果前缀】用于搜索或 ID 查询命中单个游戏时的前缀。',
    'reply_random_result_prefix': '【random/rand 结果前缀】用于随机游戏详情前缀。',
    'reply_game_metadata': '【游戏元数据】可用变量：{id} {title} {creator} {rating} {difficulty} {rating_count} {tags} {engine} {url} {file_size}',
    'reply_multiple_header': '【多个结果头部】可用变量：{count}',
    'reply_multiple_item': '【多个结果列表项】可用变量：{index} {id} {title} {creator} {tags} {url}',
    'reply_multiple_footer': '【多个结果页脚】结果不超过一页时的输入提示。可提示 end/结束 退出。',
    'reply_page_info': '【分页页码】可用变量：{current_page} {total_page}',
    'reply_result_limited_note': '【API 返回限制提示】当 count 大于实际 results 数量时显示。可用变量：{count} {available_count} {total_page}',
    'reply_paged_footer': '【分页页脚】结果多于一页时的输入提示。可提示 end/结束 退出。',
    'reply_input_invalid': '【选择输入错误】非分页列表中输入非数字时回复。可提示 end/结束 退出。',
    'reply_paged_input_invalid': '【分页输入错误】分页列表中输入非数字且不是翻页词时回复。可提示 end/结束 退出。',
    'reply_jump_page_empty': '【跳页缺少页数】用户只输入跳页命令但没有页数时回复。',
    'reply_jump_page_invalid': '【跳页页数错误】跳页参数不是严格数字时回复。',
    'reply_jump_page_out_of_range': '【跳页越界】跳转页数不在可浏览范围时回复。可用变量：{total_page}',
    'reply_random_count_invalid': '【随机数量错误】random/rand 的数量不是 1-10 整数时回复。',
    'reply_random_count_too_large': '【随机数量过大】random/rand 数量超过 10 时回复。',
    'reply_today_title': '【today 标题】今日 I Wanna 详情前缀。',
    'reply_index_out_of_range': '【序号越界】用户输入的序号不在可选范围时回复。',
    'reply_selection_ended': '【主动结束选择】用户输入 end/结束 时回复。',
    'reply_session_expired': '【选择过期】没有可用查询结果上下文时回复。',
    'reply_first_page': '【上一页到头】已经位于首页时回复。',
    'reply_last_page': '【下一页到头】已经位于末尾页时回复。',
    'reply_permission_denied': '【权限不足】管理命令权限不足时回复。',
    'reply_global_status': '【全局状态】可用变量：{global_enable} {global_debug}',
    'reply_bot_status': '【Bot 状态】可用变量：{bot_id} {bot_enable} {merge_forward}',
}


help_document_dict = {
    'iwanna_help': default_custom_message_dict['reply_help'],
}


gui_description_text = '''IWannaSearch 的 GUI 用于编辑开关、骰主列表与全部回复词。
所有面向用户发送的文本都在“编辑回复词”窗口中维护。'''

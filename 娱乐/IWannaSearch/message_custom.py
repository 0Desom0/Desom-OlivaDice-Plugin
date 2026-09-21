# -*- encoding: utf-8 -*-
"""IWannaSearch 默认回复词与 GUI 说明。"""


default_custom_message_dict = {
    'reply_help': '''【I Wanna Search】
.iw 游戏名 [--tag=标签] [--not-tag=标签] [--engine=引擎] [--year=年份] [--source=wiki/df]
按名称与条件多维筛选 I Wanna。

.iw search 游戏名 [筛选参数]
同上，支持名称模糊查询与自由组合过滤器。

.iw id 游戏ID
按游戏 ID 精确查询 I Wanna。

.iw download 游戏ID
检查 API 文件大小后下载并发送到当前会话（限 200 MB）。

.iw random [个数] [筛选参数]
.iw rand [个数] [筛选参数]
范围随机查询 I Wanna。个数默认 1，最多 10。
支持所有筛选参数（--tag, --not-tag, --engine, --not-engine, --year, --source 等）。
示例：.iw rand 3 --engine=Godot --year=2021

.iw year 年份 [游戏名]
查询指定年份发布的 I Wanna。
示例：.iw year 2021 needle

.iw tag [标签名]
.iw tags
查看热门标签分布；加标签名可直接按标签搜索。

.iw engine [引擎名]
.iw engines
查看支持的游戏引擎统计；加引擎名可直接按引擎搜索。

.iw date / .iw releasedate
查看发行日期覆盖统计及近年代收录情况。

.iw all / .iw catalog
查看全库概况与收录数据统计。

.iw today
获取今日 I Wanna。每个用户每天固定一次，会缓存当天结果。

.iwbot merge on/off
开启或关闭多个 rand 结果的合并转发（仅骰主/配置主人可用）。

.iwglobal concurrency 数量
设置同时下载的最大并发数，范围 1-100（仅骰主/配置主人可用）。
.iwbot concurrency 数量
同样可以设置全局下载并发数（仅骰主/配置主人可用）。

.iw help
查看本帮助。''',
    'reply_help_hint': '可使用 {prefix}iw help 查看 I Wanna 查询帮助。',
    'reply_empty_query': '请输入要查询的 I Wanna 名称或筛选参数。',
    'reply_not_found': '没有查询到符合条件的 I Wanna。',
    'reply_api_error': '查询失败：{error}',
    'reply_global_usage': '用法：.iwglobal status/on/off/debug on/debug off 或 .iwglobal concurrency [1-100]。',
    'reply_global_usage_concurrency': '用法：.iwglobal concurrency [1-100]。',
    'reply_download_id_invalid': '下载用法：.iw download [数字ID]。',
    'reply_download_url_missing': '该 I Wanna 没有可用的下载链接，已取消下载。',
    'reply_download_size_unknown': 'API 没有返回有效的文件大小，无法安全下载。',
    'reply_download_too_large': '该文件大小为 {file_size}，必须严格小于 200 MB，已取消下载。',
    'reply_download_started': '开始下载：[{id}] {title}（{file_size}）。',
    'reply_download_uploading': '下载完成，正在上传：{file_name}。',
    'reply_download_complete': '上传完成：{file_name}。',
    'reply_download_complete_cleanup_failed': '上传完成：{file_name}。但本地临时文件清理失败，请联系管理员检查日志。',
    'reply_download_queued': '当前下载数已达上限，已加入队列（排队序号 {queue_position}）。',
    'reply_download_failed': '下载或上传失败：{error}',
    'reply_search_result_prefix': '查询到了以下 I Wanna',
    'reply_random_result_prefix': '随机到了以下 I Wanna',
    'reply_game_metadata': '''· ID：{id}
· 标题：{title}
· 作者：{creator}
· 发布日期：{release_date}
· 评分：{rating}    难度：{difficulty}
· 评分人数：{rating_count}
· 标签：{tags}
· 游戏引擎：{engine}
· 文档来源：{sources}
· 外部页面：{external_urls}
· 档案页面：{page_url}
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
    'reply_global_status': '全局启用：{global_enable}，调试模式：{global_debug}，最大下载并发：{download_concurrency}。',
    'reply_bot_status': '当前 Bot：{bot_id}，Bot 开关：{bot_enable}，合并转发：{merge_forward}。',
    'reply_tag_list': '''【I Wanna 热门标签】
共统计到 {count} 个标签。热门标签：
{tag_items}
提示：输入 .iw tag <标签名> 或 .iw search --tag=<标签名> 筛选。''',
    'reply_engine_list': '''【I Wanna 游戏引擎分布】
共统计到 {count} 种引擎：
{engine_items}
提示：输入 .iw engine <引擎名> 或 .iw search --engine=<引擎名> 筛选。''',
    'reply_date_summary': '''【I Wanna 发行日期统计】
· 已知日期：{dated} 部
· 未知日期：{undated} 部
· 最早记录：{earliest}
· 最近记录：{latest}
近年收录概况：
{year_items}
提示：使用 .iw year <年份> 查询指定年份游戏。''',
    'reply_catalog_summary': '''【I Wanna Archive 全库概况】
· 总收录游戏：{catalog_size} 部
· 已标注发行日期：{dated} 部
· 统计引擎数：{engine_count} 种
· 标签库数量：{tag_count} 个
· 外部互通：Delicious Fruit、IWanna Wiki
提示：使用 .iw help 查看全功能查询指令。''',
    'reply_year_empty': '请输入要查询的 4 位年份，例如：.iw year 2021。',
    'reply_year_invalid': '年份格式不正确，请输入 4 位数字年份（例如：2021）。',
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
    'reply_global_usage': '【iwglobal 总用法】可用变量：{prefix}',
    'reply_global_usage_concurrency': '【下载并发设置用法】范围 1-100。',
    'reply_download_id_invalid': '【下载 ID 格式错误】要求严格数字 ID。',
    'reply_download_url_missing': '【下载链接缺失】API 未返回 http/https 下载链接。',
    'reply_download_size_unknown': '【文件大小缺失】API 未返回可验证的字节数。',
    'reply_download_too_large': '【文件过大】可用变量：{file_size}；限制为严格小于 200 MB。',
    'reply_download_started': '【开始下载】可用变量：{id} {title} {file_size}。',
    'reply_download_uploading': '【下载完成并开始上传】可用变量：{id} {title} {file_name} {file_size}。',
    'reply_download_complete': '【上传完成】可用变量：{file_name}。',
    'reply_download_complete_cleanup_failed': '【上传完成但清理失败】可用变量：{file_name}。',
    'reply_download_queued': '【下载排队】可用变量：{queue_position}。',
    'reply_download_failed': '【下载/上传失败】可用变量：{error}。',
    'reply_search_result_prefix': '【search/id 结果前缀】用于搜索或 ID 查询命中单个游戏时的前缀。',
    'reply_random_result_prefix': '【random/rand 结果前缀】用于随机游戏详情前缀。',
    'reply_game_metadata': '【游戏元数据】可用变量：{id} {title} {creator} {release_date} {rating} {difficulty} {rating_count} {tags} {engine} {sources} {external_urls} {page_url} {url} {file_size}',
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
    'reply_global_status': '【全局状态】可用变量：{global_enable} {global_debug} {download_concurrency}',
    'reply_bot_status': '【Bot 状态】可用变量：{bot_id} {bot_enable} {merge_forward}',
    'reply_tag_list': '【热门标签列表】可用变量：{count} {tag_items}',
    'reply_engine_list': '【引擎分布列表】可用变量：{count} {engine_items}',
    'reply_date_summary': '【发行日期概况】可用变量：{dated} {undated} {earliest} {latest} {year_items}',
    'reply_catalog_summary': '【全库概况】可用变量：{catalog_size} {dated} {engine_count} {tag_count}',
    'reply_year_empty': '【年份查询为空】用户未输入年份时回复。',
    'reply_year_invalid': '【年份格式错误】用户输入非 4 位年份时回复。',
}


help_document_dict = {
    'iwanna_help': default_custom_message_dict['reply_help'],
}


gui_description_text = '''IWannaSearch 的 GUI 用于编辑开关、骰主列表与全部回复词。
所有面向用户发送的文本都在“编辑回复词”窗口中维护。'''

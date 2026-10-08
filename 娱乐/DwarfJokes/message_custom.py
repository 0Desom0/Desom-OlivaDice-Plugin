# -*- encoding: utf-8 -*-
"""DwarfJokes 默认回复词与帮助文档。"""

default_custom_message_dict = {
    'reply_permission_denied': '权限不足：只有 OlivaDiceCore 骰主、本插件骰主或本插件管理员可以执行该操作。',
    'reply_permission_denied_admin': '权限不足：只有 OlivaDiceCore 骰主或本插件骰主可以管理插件管理员。',
    'reply_help_hint': '可使用 {prefix}矮人 帮助 查看矮人笑话命令。',
    'reply_draw_empty': '当前没有可抽取的矮人笑话。',
    'reply_add_success': '添加成功。这条矮人笑话的序号是 {joke_id}，当前共有 {joke_count} 条。',
    'reply_add_empty': '添加失败：笑话内容不能为空。',
    'reply_add_too_long': '添加失败：笑话内容不能超过 {max_length} 字。',
    'reply_add_duplicate': '添加失败：与序号 {joke_id} 的笑话重复（参考度 {rank}，低于 {rank_gate} 判定为重复）。',
    'reply_add_save_failed': '添加失败：写入合集文件时出错。',
    'reply_add_usage': '用法：{prefix}矮人 add/添加 笑话内容',
    'reply_delete_success': '已删除序号 {joke_id} 的矮人笑话。当前共有 {joke_count} 条。',
    'reply_delete_missing': '删除失败：序号 {joke_id} 不存在。',
    'reply_delete_invalid': '删除失败：请提供有效的正整数序号。',
    'reply_delete_save_failed': '删除失败：写入合集文件时出错。',
    'reply_delete_usage': '用法：{prefix}矮人 del/rm/删除 序号',
    'reply_list': '当前共有 {joke_count} 条矮人笑话。下一个填补序号是 {next_id}。',
    'reply_list_item': '【矮人笑话 #{joke_id}】\n{joke_text}',
    'reply_list_missing': '展示失败：序号 {joke_id} 不存在。',
    'reply_list_invalid': '展示失败：请提供有效的正整数序号。',
    'reply_admin_usage': '用法：{prefix}矮人 admin add/del 用户ID',
    'reply_admin_add_empty': '添加管理员失败：请提供数字用户 ID。',
    'reply_admin_add_success': '已添加插件管理员：{admin_ids}。当前管理员：{admin_list}。',
    'reply_admin_del_empty': '删除管理员失败：请提供数字用户 ID。',
    'reply_admin_del_success': '已删除插件管理员：{admin_ids}。当前管理员：{admin_list}。',
    'reply_admin_list_empty': '无',
}


default_custom_variable_dict = {
    'plugin_display_name': '矮人笑话',
}


custom_message_note_dict = {
    'reply_permission_denied': '【add / del】\n新增或删除笑话时权限不足的提示。',
    'reply_permission_denied_admin': '【admin】\n管理插件管理员时权限不足的提示。',
    'reply_help_hint': '【未命中具体子命令时不使用】\n保留给 GUI 说明。',
    'reply_draw_empty': '【抽选】\n合集为空时的提示。',
    'reply_add_success': '【add 成功】\n需要 {joke_id} 与 {joke_count}。',
    'reply_add_empty': '【add 内容为空】',
    'reply_add_too_long': '【add 超长】\n需要 {max_length}。',
    'reply_add_duplicate': '【add 重复】\n需要 {joke_id}、{rank}、{rank_gate}。',
    'reply_add_save_failed': '【add 写文件失败】',
    'reply_add_usage': '【add 用法】',
    'reply_delete_success': '【del 成功】\n需要 {joke_id} 与 {joke_count}。',
    'reply_delete_missing': '【del 序号不存在】',
    'reply_delete_invalid': '【del 序号非法】',
    'reply_delete_save_failed': '【del 写文件失败】',
    'reply_delete_usage': '【del 用法】',
    'reply_list': '【list/show/展示】无序号时查看合集数量。\n需要 {joke_count} 与 {next_id}。',
    'reply_list_item': '【list/show/展示 序号】展示指定笑话。\n需要 {joke_id} 与 {joke_text}。',
    'reply_list_missing': '【list/show/展示 序号不存在】',
    'reply_list_invalid': '【list/show/展示 序号非法】',
    'reply_admin_usage': '【admin 用法】',
    'reply_admin_add_empty': '【admin add 缺少 ID】',
    'reply_admin_add_success': '【admin add 成功】',
    'reply_admin_del_empty': '【admin del 缺少 ID】',
    'reply_admin_del_success': '【admin del 成功】',
    'reply_admin_list_empty': '【管理员列表为空时的占位文本】',
}


help_document_dict = {
    'dwarf_help': '''【矮人笑话 DwarfJokes】
命令前缀：.  。  /  ／
主命令（贪婪匹配，可省略空格）：矮人笑话 / dwarfjokes / 矮人 / dwarf

1. {prefix}矮人
随机抽 1 条矮人笑话。

2. {prefix}矮人10  或  {prefix}矮人 10
随机抽指定条数。范围 1-10，超过 10 按 10，小于 1 按 1。
不是数字也不是子命令时不回复。

3. {prefix}矮人add 笑话内容  或  {prefix}矮人 添加 笑话内容
新增一条笑话。序号优先填补空缺，再继续自增。
category / platform / source_url / note / original_en 留空，正文写入 text。
权限：OlivaDiceCore 骰主 / 本插件骰主 / 本插件管理员。
若与已有笑话重复（OlivaDiceCore 帮助文档参考度低于 50），会提示与哪个序号重复。

4. {prefix}矮人del 序号  或  {prefix}矮人 删除 序号
删除指定序号。也可用 rm。
权限同上。删除后该序号会成为下次新增的填补目标。

5. {prefix}矮人list  或  {prefix}矮人 展示
查看当前共有多少条。也可用 show。
带序号则展示指定笑话，例如 {prefix}矮人list5、{prefix}矮人show 5、{prefix}矮人 展示 5。

6. {prefix}矮人帮助  或  {prefix}矮人 help
查看本帮助。

7. {prefix}矮人admin add 用户ID
{prefix}矮人admin del 用户ID
添加或删除本插件管理员。
权限：OlivaDiceCore 骰主 / 本插件骰主。

GUI 菜单和 WebUI 可管理开关、骰主、管理员与笑话合集。
合集文件：plugin/data/DwarfJokes/DwarfJokesPack.json''',
}


gui_description_text = '''矮人笑话插件配置：
1. 全局页控制启用开关，并显示笑话合集摘要。
2. Bot 页可切换账号，管理本插件骰主和管理员。
3. 笑话合集页可浏览、新增、删除全局 DwarfJokesPack.json。
4. 新增笑话会按 OlivaDiceCore 帮助文档参考度打分，低于 50 视为重复。
5. 全局配置、Bot 配置和回复词都支持 JSON 导入导出。
6. 回复词窗口可按“已修改 / 未修改”筛选，比较对象是模板默认文本。
7. bot_config、骰主和管理员列表不跟随 link；storage、回复词与变量会切到 linked_bot_hash 对应文件夹。'''

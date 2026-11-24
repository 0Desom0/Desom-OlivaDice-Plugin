# -*- encoding: utf-8 -*-
'''
@File      :   msgReply.py
@Author    :   lunzhiPenxil仑质
@Contact   :   lunzhipenxil@gmail.com
@License   :   AGPL
@Copyright :   (C) 2020-2021, OlivOS-Team
@Desc      :   收到恰好两个受支持的 emoji 时，回一张 Emoji Kitchen 合成图。
               数据来自 plugin/data/OlivaEmojiKitchen/emojiData.json（每日更新）。
'''

import OlivOS
import OlivaEmojiKitchen

import time

import requests as req

REQUEST_TIMEOUT = (3, 5)
PROBE_ATTEMPTS = 2

# 数据表由上游 metadata 的 gStaticUrl 全量核对生成，链接基本不会失效，
# 默认不再逐张预检（预检会让每条回复多等 2~4 秒）。
# 万一以后出现脏链接，把这里改成 True 即可恢复预检。
VERIFY_IMAGE = False


def _probe_image(url):
    '''确认图片真实可访问，避免把 404 链接丢进群。

    gstatic 偶尔握手抖动，失败时重试一次再放弃。
    '''
    for attempt in range(PROBE_ATTEMPTS):
        try:
            res = req.get(url, timeout=REQUEST_TIMEOUT, stream=True)
            try:
                if res.status_code == 200:
                    return True
            finally:
                res.close()
        except Exception:
            pass
        if attempt + 1 < PROBE_ATTEMPTS:
            time.sleep(0.25)
    return False


def unity_reply(plugin_event, Proc):
    try:
        message = plugin_event.data.message
    except AttributeError:
        return
    if not isinstance(message, str) or not message:
        return

    emojis = OlivaEmojiKitchen.emojiData.find_emojis(message)
    if len(emojis) != 2:
        return

    start_left, end_left, codepoint_left = emojis[0]
    start_right, end_right, codepoint_right = emojis[1]
    # emoji 之外只允许空白，避免把普通聊天误当成合成请求
    if message[:start_left].strip():
        return
    if message[end_left:start_right].strip():
        return
    if message[end_right:].strip():
        return

    reply_url = OlivaEmojiKitchen.emojiData.resolve_url(codepoint_left, codepoint_right)
    if reply_url is None:
        return
    if VERIFY_IMAGE and not _probe_image(reply_url):
        return

    plugin_event.reply(
        OlivOS.messageAPI.Message_templet(
            'olivos_para',
            [
                OlivOS.messageAPI.PARA.image(
                    reply_url
                )
            ]
        )
    )

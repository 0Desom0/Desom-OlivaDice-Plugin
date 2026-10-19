"""QQ 音乐语音：下载到临时文件，再交给 OlivOS 上传并发送。"""

import hashlib
import json
import sqlite3
import tempfile
import time
import urllib.parse
import urllib.request
import uuid
from contextlib import closing
from pathlib import Path
from threading import Lock

from . import load

BUTTON_ID = 'MusicSearch_voice'
BUTTON_PREFIX = 'MusicSearch:voice:'
MAX_AUDIO_BYTES = 20 * 1024 * 1024
_running_buttons = set()
_successful_buttons = set()
_button_lock = Lock()


class VoiceError(ValueError):
    """可直接展示的插件错误，不包含网络响应或下载签名。"""


def callback_data(song_id):
    """每条歌曲消息有独立按钮标识，同一首歌再次点歌仍可点击新按钮。"""
    return f'{BUTTON_PREFIX}{song_id}:{uuid.uuid4().hex}'


def claim_button(event, payload, token=None):
    """临时占用按钮，忽略运行中或已经成功发送的重复点击。"""
    chat_type, chat_id = chat_context(event, True)
    if chat_type not in ('qq_group', 'qq_private') or not chat_id:
        return None
    # 兼容旧卡片，但不能用每次点击都不同的 interaction_id 代替按钮标识。
    identity = token or getattr(event.data, 'message_id', None)
    if not identity:
        return None
    button_key = hashlib.sha256(json.dumps(
        [str(event.bot_info.hash), chat_type, str(chat_id), payload, str(identity)],
        ensure_ascii=False,
    ).encode('utf-8')).hexdigest()
    with _button_lock:
        if button_key in _running_buttons or button_key in _successful_buttons:
            return None
        _running_buttons.add(button_key)
    try:
        directory = Path(load.data_dir)
        directory.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(directory / 'voice_buttons.sqlite3', timeout=5)) as connection:
            connection.execute('CREATE TABLE IF NOT EXISTS used_buttons (button_key TEXT PRIMARY KEY)')
            consumed = connection.execute(
                'SELECT 1 FROM used_buttons WHERE button_key = ?', (button_key,),
            ).fetchone()
        if consumed:
            with _button_lock:
                _successful_buttons.add(button_key)
                _running_buttons.discard(button_key)
            return None
        return button_key
    except Exception:
        with _button_lock:
            _running_buttons.discard(button_key)
        raise


def finish_button(button_key, success):
    """成功后持久化完成状态；失败或异常只释放运行锁，允许再次点击。"""
    try:
        if success:
            # 落盘失败也不允许在当前进程重复发送已经成功的语音。
            with _button_lock:
                _successful_buttons.add(button_key)
            directory = Path(load.data_dir)
            with closing(sqlite3.connect(directory / 'voice_buttons.sqlite3', timeout=5)) as connection:
                with connection:
                    connection.execute('INSERT OR IGNORE INTO used_buttons VALUES (?)', (button_key,))
    finally:
        with _button_lock:
            _running_buttons.discard(button_key)


def chat_context(event, is_group):
    extend = getattr(event.data, 'extend', {}) or {}
    direct = bool(extend.get('flag_from_direct', not is_group))
    host_id = extend.get('host_group_id') or getattr(event.data, 'host_id', None)
    flag_qq = bool(extend.get('flag_from_qq', not host_id))
    if flag_qq:
        return ('qq_private', event.data.user_id) if direct else ('qq_group', event.data.group_id)
    if direct:
        return 'guild_private', host_id or getattr(event.data, 'group_id', None)
    return 'guild_channel', event.data.group_id


def send(event, chat_type, chat_id, message):
    """按钮使用互动 event_id，指令使用本次用户消息，不引用旧卡片的消息 ID。"""
    kwargs = {'chat_type': chat_type, 'chat_id': chat_id, 'message': message, 'flag_log': False}
    if event.plugin_info.get('func_type') == 'button_click':
        extend = getattr(event.data, 'extend', {}) or {}
        event_id = extend.get('event_id')
        if not event_id:
            raise VoiceError('按钮事件缺少被动回复标识')
        kwargs['event_id'] = event_id
    else:
        kwargs['reply_msg_id'] = getattr(event.data, 'message_id', None)
    return event.indeAPI.send_message(**kwargs)


def audio_extension(header):
    if header.startswith(b'ID3') or (len(header) > 1 and header[0] == 0xff and header[1] & 0xe0 == 0xe0):
        return '.mp3'
    if header.startswith(b'RIFF') and header[8:12] == b'WAVE':
        return '.wav'
    if header.startswith(b'OggS'):
        return '.ogg'
    if header.startswith((b'#!SILK_V3', b'\x02#!SILK_V3')):
        return '.silk'
    raise VoiceError('下载结果不是受支持的音频，可能歌曲无播放权限')


def download_audio(url, directory, headers):
    """有界流式下载，拒绝错误页面和超出语音软限制的文件。"""
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme not in ('http', 'https') or not parsed.netloc:
        raise VoiceError('歌曲没有可下载的音频链接')
    request = urllib.request.Request(url, headers={**headers, 'Referer': 'https://music.163.com/'})
    deadline = time.monotonic() + 60
    with urllib.request.urlopen(request, timeout=15) as response:
        length = response.headers.get('Content-Length')
        if length and int(length) > MAX_AUDIO_BYTES:
            raise VoiceError('歌曲文件超过 20 MiB，无法作为语音发送')
        head = response.read(4096)
        extension = audio_extension(head)
        destination = Path(directory) / ('music' + extension)
        total = len(head)
        with destination.open('wb') as output:
            output.write(head)
            while True:
                if time.monotonic() > deadline:
                    raise TimeoutError('下载歌曲超时')
                chunk = response.read(64 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > MAX_AUDIO_BYTES:
                    raise VoiceError('歌曲文件超过 20 MiB，无法作为语音发送')
                output.write(chunk)
        if length and total != int(length):
            raise VoiceError('歌曲下载不完整，请重试')
        return destination


def send_song(processor, event, proc, song_id, is_group):
    chat_type, chat_id = chat_context(event, is_group)
    if chat_type not in ('qq_group', 'qq_private') or not chat_id:
        event.reply('音乐语音目前仅支持 QQ 群和 QQ 私聊。')
        return False
    sent = False
    try:
        if not event.indeAPI.hasAPI('send_message'):
            raise VoiceError('当前 OlivOS 不支持音乐语音发送接口')
        result = processor.search_music(song_id=int(song_id), Proc=proc)
        songs = processor.normalize_song_list(result) if isinstance(result, dict) and result.get('code') == 0 else []
        song = next((s for s in songs if isinstance(s, dict) and str(s.get('id')) == str(int(song_id))), None)
        if song is None:
            raise VoiceError('未查询到对应歌曲，请重新点歌')
        url = song.get('url')
        if not isinstance(url, str) or not url.strip():
            raise VoiceError('这首歌没有可下载的音频，可能需要付费或暂不可用')
        # SDK 按本地文件内容上传 file_type=3，并通过 media.file_info 发语音。
        with tempfile.TemporaryDirectory(prefix='MusicSearch-voice-') as temp_dir:
            audio_path = download_audio(url.strip(), temp_dir, processor.DEFAULT_HEADERS)
            result = send(event, chat_type, chat_id, f'[OP:record,file={audio_path.as_uri()}]')
            if not isinstance(result, dict) or not result.get('active'):
                raise VoiceError('音乐语音上传或发送失败，请稍后重试')
            sent = True
        proc.log(2, f'>>> 成功发送音乐语音，歌曲 ID: {int(song_id)}', [])
        return True
    except Exception as error:
        # 不输出下载 URL（可能带时效签名）或 SDK 的原始认证响应。
        proc.log(3, f'>>> 音乐语音处理失败: {type(error).__name__}', [])
        if sent:
            # 语音已成功时，临时文件清理等后续异常不能让按钮变回可重试。
            return True
        message = str(error) if isinstance(error, VoiceError) else '下载或发送音乐失败，请稍后重试'
        try:
            send(event, chat_type, chat_id, message)
        except Exception:
            proc.log(3, '>>> 音乐语音错误提示发送失败', [])
        return False

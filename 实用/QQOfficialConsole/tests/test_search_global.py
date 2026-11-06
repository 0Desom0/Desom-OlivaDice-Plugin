"""全局搜索的消息结果要带会话显示名，前端才能省略一长串 openid。"""
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from QQOfficialConsole import store


@pytest.fixture
def database(tmp_path):
    db = store.Store(tmp_path / 'data')
    yield db
    db.close()


def test_search_global_messages_carry_chat_name(database):
    now = int(time.time())
    openid = 'ACA04D389BED903BBDAD85EDFDAFBCA'
    database.upsert_chat('bot', 'qq_group', openid, display_name='跑团日常', last_message_at=now)
    database.add_message(
        'bot', 'qq_group', openid,
        {'direction': 'in', 'msg_kind': 'text', 'content_text': '什么意思', 'created_at': now},
    )
    result = database.search_global('bot', '什么意思')
    assert len(result['messages']) == 1
    row = result['messages'][0]
    assert row['chat_name'] == '跑团日常'
    # 定位会话还是要靠 openid，只是不该拿它当显示标题。
    assert row['chat_id'] == openid


def test_search_global_prefers_remark(database):
    now = int(time.time())
    openid = 'FEDCBA0987654321'
    database.upsert_chat(
        'bot', 'qq_group', openid,
        display_name='原名', remark='开团群', last_message_at=now,
    )
    database.add_message(
        'bot', 'qq_group', openid,
        {'direction': 'in', 'msg_kind': 'text', 'content_text': '今晚八点', 'created_at': now},
    )
    rows = database.search_global('bot', '今晚八点')['messages']
    assert rows and rows[0]['chat_name'] == '开团群'

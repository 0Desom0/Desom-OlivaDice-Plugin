"""手动回收磁盘空间：真实 SQLite 行为、容错与消息桥入口。"""
import sys
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from QQOfficialConsole import store, webui


@pytest.fixture
def database(tmp_path):
    db = store.Store(tmp_path / 'data')
    yield db
    db.close()


def seed(db, bot, chat_type, chat_id, count=3000):
    """塞一批消息制造真实体积；返回该会话的库文件路径。"""
    now = int(time.time())
    rows = [('in', 'text', 'x' * 500, now - i) for i in range(count)]
    with db.session(bot, chat_type, chat_id) as conn:
        conn.executemany(
            'INSERT INTO messages (direction,msg_kind,content_text,created_at) VALUES (?,?,?,?)', rows
        )
    return db._chat_path(bot, chat_type, chat_id)


def test_vacuum_reclaims_deleted_rows_and_keeps_data(database):
    path = seed(database, 'bot', 'qq_group', 'g1')
    with database.session('bot', 'qq_group', 'g1') as conn:
        conn.execute('DELETE FROM messages')
    # 删除本身不缩文件：关闭常驻连接后 WAL 已 checkpoint，此时体积仍是高水位。
    result = database.vacuum_databases()
    assert result['files'] == 1 and result['vacuumed'] == 1 and result['failed'] == 0
    assert result['before'] > result['after'] > 0
    assert result['reclaimed'] == result['before'] - result['after']
    assert path.stat().st_size == result['after']
    # LRU 里的连接关掉后应能自动重开，WAL 模式和写入都保持正常。
    with database.session('bot', 'qq_group', 'g1') as conn:
        conn.execute(
            "INSERT INTO messages (direction,msg_kind,content_text,created_at) VALUES ('in','text','ok',?)",
            (int(time.time()),),
        )
        assert conn.execute('SELECT COUNT(*) FROM messages').fetchone()[0] == 1
        assert conn.execute('PRAGMA journal_mode').fetchone()[0] == 'wal'


def test_vacuum_skips_global_and_tolerates_broken_file(database):
    seed(database, 'bot', 'qq_group', 'g1')
    broken = database.root / 'bot' / 'msg' / 'qq_group' / 'broken.sqlite3'
    broken.write_bytes(b'not a sqlite database')
    result = database.vacuum_databases()
    # global.sqlite3 由常驻连接持有且只有设置表，不该被算进来。
    assert result['files'] == 2
    assert result['vacuumed'] == 1 and result['failed'] == 1
    assert (database.root / 'global.sqlite3').exists()
    assert isinstance(database.get_settings(), dict)


def test_vacuum_without_deletions_is_harmless(database):
    seed(database, 'bot', 'qq_group', 'g1', count=20)
    result = database.vacuum_databases()
    assert result['failed'] == 0 and result['vacuumed'] == 1
    assert result['reclaimed'] >= 0 and result['after'] > 0
    with database.session('bot', 'qq_group', 'g1') as conn:
        assert conn.execute('SELECT COUNT(*) FROM messages').fetchone()[0] == 20


@pytest.fixture
def bridge(database):
    proc = SimpleNamespace(
        Proc_data={'bot_info_dict': {}}, log=lambda *args, **kwargs: None
    )
    instance = webui.Bridge(database, None, None, None, proc)
    yield instance
    instance.close()


def test_vacuum_action_needs_no_bot_and_is_single_flight(bridge, database):
    # 全局维护动作排在 bot_hash 校验之前，没选机器人也能执行。
    reply = bridge.handle('QQOfficialConsole_Vacuum', {})
    assert reply['ok'] is True and 'vacuum' in reply
    assert reply['vacuum']['failed'] == 0

    entered, release = threading.Event(), threading.Event()
    original = database.vacuum_databases

    def slow():
        entered.set()
        release.wait(5)
        return original()

    database.vacuum_databases = slow
    outcomes = []

    def first():
        outcomes.append(bridge.handle('QQOfficialConsole_Vacuum', {}))

    worker = threading.Thread(target=first)
    try:
        worker.start()
        assert entered.wait(2)
        busy = bridge.handle('QQOfficialConsole_Vacuum', {})
        assert busy['ok'] is False and busy['keyword'] == '回收正在进行中'
    finally:
        release.set()
        worker.join(5)
        database.vacuum_databases = original
    assert outcomes and outcomes[0]['ok'] is True

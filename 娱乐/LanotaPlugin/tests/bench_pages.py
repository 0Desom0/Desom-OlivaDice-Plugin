"""py -3.12 tests/bench_pages.py [--samples DIR] [--require-sdk]，不访问在线曲库或发送消息。"""
import argparse
import json
import os
import shutil
import sys
import tempfile
from contextlib import chdir
from pathlib import Path
from time import perf_counter
from types import SimpleNamespace
from unittest.mock import Mock

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]


def measure(call):
    start = perf_counter()
    result = call()
    return result, (perf_counter() - start) * 1000


def run(tmp, samples, require_sdk):
    # 模拟 OPK：先加载插件并释放种子资源，再移除自己的解包副本。
    package = tmp / 'unpacked' / ROOT.name
    package.mkdir(parents=True)
    for source in ROOT.glob('*.py'):
        shutil.copyfile(source, package / source.name)
    shutil.copytree(ROOT / 'Data', package / 'Data')
    sys.path.insert(0, str(package.parent))
    from LanotaPlugin import config, crawler, function, message, pages, portal, utils
    utils.initialize_plugin()
    songs = function.load_song_data()
    groups = pages.table_groups(songs, function.load_table_data())
    shutil.rmtree(package)
    print('OPK unpacked directory removed; catalog:', len(songs), 'songs')
    cases = {'time': pages.time_page(songs)[0], 'table': pages.table_page('15', groups['15'])[0],
             'notes': pages.notes_page(songs)[0], 'report': {
                 'title': '曲库全量检测报告', 'elapsed': '2.8 s', 'errors': 1, 'total': 42,
                 'rows': [f'检测到变化 · {s["chapter"]} {s["title"]}：官方定数' for s in songs[:40]],
             }}
    print('table 15:', len(groups['15']), 'charts')
    for kind, data in cases.items():
        cold, hits = [], []
        for _ in range(1 if kind == 'report' else 3):
            # 更新临时曲库 mtime，内容不变；验证版本参与 key 而不清空磁盘缓存。
            source = Path(utils.get_song_list_path())
            stamp = source.stat().st_mtime_ns + 2_000_000_000
            os.utime(source, ns=(stamp, stamp))
            version = pages.version(kind)
            path, ms = measure(lambda: portal.render_page(kind, data, version))
            if not path:
                raise RuntimeError(f'{kind} cold {ms:.1f}ms: {portal.render_status_text()}')
            cold.append(ms)
            same, ms = measure(lambda: portal.render_page(kind, data, version))
            assert same == path
            hits.append(ms)
        print(f'{kind} cold_ms={[round(n, 2) for n in cold]} hit_ms={[round(n, 2) for n in hits]}')
        assert max(cold) <= 4000 and max(hits) <= 50
        if samples:
            shutil.copyfile(path, samples / f'{kind}.png')
            (samples / f'{kind}.html').write_text(portal._template_html(data, kind), encoding='utf-8')

    import OlivOS
    validate = getattr(OlivOS.qqGuildv2SDK.event_action, '_validate_keyboard_permissions', None)
    if not validate:
        print('SDK validator unavailable in this OlivOS installation')
        if require_sdk:
            raise RuntimeError('Use an OlivOS SDK with Markdown keyboard support.')
    received = []

    def receive(**payload):
        received.append((perf_counter(), payload))
        return {'active': True}

    e = SimpleNamespace(data=SimpleNamespace(user_id='reader', group_id='group', message_id='msg', message='',
                                             extend={'chat_type': 'qq_group', 'chat_id': 'group'}),
                        bot_info=SimpleNamespace(hash='bot'), platform={'sdk': 'qqGuildv2_link'},
                        plugin_info={'func_type': 'group_message'}, reply=Mock(),
                        indeAPI=SimpleNamespace(create_markdown_message=receive))
    utils.save_global_config({'download_cover_on_demand': False})
    utils.save_bot_config('bot', {'song_card_html_enable': False})
    song = songs[0]
    cover = Path(utils.get_cover_art_dir()) / 'bench.png'
    Image.new('RGB', (512, 256), '#6084aa').save(cover)
    crawler.save_cover_index({crawler.get_cover_cache_key(song): {'file_name': cover.name}})
    assert crawler.ensure_song_covers(song)

    message.save_search_session(e, songs[:30], None)
    calls = {'search': lambda: message.handle_message(e, None), 'info': lambda: message.reply_song_card(e, song),
             'today': lambda: message.handle_today(e), 'random': lambda: message.handle_random(e, '')}
    e.data.message = '.la 跳页 2'
    for name, call in calls.items():
        elapsed = []
        for _ in range(3 if name in ('search', 'info') else 1):
            received.clear()
            start = perf_counter()
            call()
            assert len(received) == 1
            instant, payload = received[0]
            elapsed.append(round((instant - start) * 1000, 2))
        if name == 'search':
            assert payload['markdown']['content'].count('**\n**') >= config.result_page_size - 1
            print('search 10 items, command -> SDK ms:', elapsed)
            assert max(elapsed) <= 120
        elif name == 'info':
            assert payload['local_images']
            print('info cached cover, composition -> SDK ms (legacy HTML card off):', elapsed)
            assert max(elapsed) <= 400
        kb = payload['keyboard']
        if validate:
            error = validate(kb, 'qq_group')
            print(f'{name} SDK permission: {error}')
            assert error is None
        print(name, json.dumps(kb, ensure_ascii=False, separators=(',', ':')))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--samples', type=Path)
    parser.add_argument('--require-sdk', action='store_true')
    args = parser.parse_args()
    # pywebview 随 OlivOS 导入时会解析入口目录，切换到临时实例前固定绝对路径。
    sys.argv[0] = str(Path(__file__).resolve())
    output_dir = args.samples.resolve() if args.samples else None
    if output_dir:
        output_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp, chdir(temp):
        run(Path(temp), output_dir, args.require_sdk)

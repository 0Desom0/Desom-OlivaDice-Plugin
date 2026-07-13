#!/usr/bin/env python3
"""Lanota Wiki Songs 页面同步模块，同时保留独立 CLI 入口。"""

from __future__ import annotations

import argparse
import difflib
import html
import json
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

try:
    import mwparserfromhell
    import requests
except ImportError as exc:  # pragma: no cover - 仅用于给最终用户更友好的报错
    raise SystemExit('缺少依赖。请先运行：python -m pip install requests mwparserfromhell') from exc


API_URL = 'https://lanota.fandom.com/api.php'
SONGS_PAGE = 'Songs'
SONG_TEMPLATE = 'Template:Song'
SONGS_CATEGORY = 'Category:Songs'
USER_AGENT = 'LanotaSongsApiSync/1.0 (manual wiki maintenance script)'
REQUIRED_FIELDS = (
    'Song',
    'Artist',
    'Chapter',
    'Id',
    'DiffWhisper',
    'DiffAcoustic',
    'DiffUltra',
    'DiffMaster',
    'Time',
    'BPM',
    'Version',
)
DIFFICULTY_FIELDS = ('DiffWhisper', 'DiffAcoustic', 'DiffUltra', 'DiffMaster')
TABLE_START = '{|class="wikitable sortable"'


class WikiApiError(RuntimeError):
    """MediaWiki API 返回错误。"""


@dataclass(frozen=True)
class WikiPage:
    pageid: int
    title: str
    display_title: str
    wikitext: str


@dataclass(frozen=True)
class SongRecord:
    pageid: int
    page_title: str
    display_title: str
    song: str
    artist: str
    chapter: str
    song_id: int
    whisper: str
    acoustic: str
    ultra: str
    master: str
    duration: str
    bpm: str
    version: str

    @property
    def group(self) -> str:
        if self.chapter.casefold() == 'time limited':
            return 'event'
        if self.chapter == '∞':
            return 'infinity'
        return 'normal'


@dataclass(frozen=True)
class ExistingRow:
    raw: str
    link_title: str
    title_cell: str
    chapter: str
    song_id: int


@dataclass(frozen=True)
class ChangedRow:
    record: SongRecord
    old_raw: str
    new_raw: str


@dataclass
class BuildResult:
    wikitext: str
    added: list[SongRecord]
    changed: list[ChangedRow]
    unchanged_count: int
    retained_rows: list[ExistingRow]


class MediaWikiClient:
    def __init__(self, api_url: str = API_URL, timeout: float = 30.0) -> None:
        self.api_url = api_url
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({'User-Agent': USER_AGENT, 'Accept': 'application/json'})

    def request(self, method: str = 'GET', **params: Any) -> dict[str, Any]:
        payload = {
            'format': 'json',
            'formatversion': 2,
            'maxlag': 5,
            **params,
        }
        for attempt in range(4):
            response = self.session.request(
                method,
                self.api_url,
                params=payload if method == 'GET' else None,
                data=payload if method != 'GET' else None,
                timeout=self.timeout,
            )
            response.raise_for_status()
            data = response.json()
            error = data.get('error')
            if not error:
                return data
            if error.get('code') == 'maxlag' and attempt < 3:
                wait_seconds = min(float(response.headers.get('Retry-After', 2)), 10.0)
                time.sleep(wait_seconds)
                continue
            raise WikiApiError(f"API 错误 {error.get('code')}: {error.get('info')}")
        raise WikiApiError('MediaWiki API 在多次重试后仍然繁忙')

    def paginated_list(self, list_name: str, **params: Any) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        continuation: dict[str, Any] = {}
        while True:
            data = self.request(action='query', list=list_name, **params, **continuation)
            result.extend(data.get('query', {}).get(list_name, []))
            if 'continue' not in data:
                return result
            continuation = data['continue']

    def discover_song_titles(self) -> list[str]:
        embedded = self.paginated_list(
            'embeddedin',
            eititle=SONG_TEMPLATE,
            einamespace=0,
            eilimit='max',
        )
        category = self.paginated_list(
            'categorymembers',
            cmtitle=SONGS_CATEGORY,
            cmnamespace=0,
            cmtype='page',
            cmlimit='max',
        )
        # 取并集后再严格检查 Song 模板及必填字段；这样分类或模板一边漏加时也不会漏歌。
        titles = {str(item['title']) for item in embedded}
        titles.update(str(item['title']) for item in category)
        print(
            f'  Template:Song 引用页：{len(embedded)}，Category:Songs 页面：{len(category)}，'
            f'合并后：{len(titles)}'
        )
        return sorted(titles, key=str.casefold)

    def fetch_pages(self, titles: Iterable[str]) -> list[WikiPage]:
        pages: list[WikiPage] = []
        title_list = list(titles)
        total_batches = (len(title_list) + 49) // 50
        for offset in range(0, len(title_list), 50):
            batch = title_list[offset : offset + 50]
            batch_number = offset // 50 + 1
            print(f'  获取歌曲详情批次：{batch_number}/{total_batches}', end='\r', flush=True)
            data = self.request(
                action='query',
                prop='revisions|pageprops',
                titles='|'.join(batch),
                rvprop='content',
                rvslots='main',
                ppprop='displaytitle',
            )
            for page in data.get('query', {}).get('pages', []):
                if page.get('missing') or not page.get('revisions'):
                    continue
                revision = page['revisions'][0]
                content = revision.get('slots', {}).get('main', {}).get('content', '')
                pages.append(
                    WikiPage(
                        pageid=int(page['pageid']),
                        title=str(page['title']),
                        display_title=str(page.get('pageprops', {}).get('displaytitle', '')),
                        wikitext=str(content),
                    )
                )
        if title_list:
            print(f'  获取歌曲详情批次：{total_batches}/{total_batches}')
        return pages

    def fetch_songs_page(self) -> tuple[str, int, str, str]:
        data = self.request(
            action='query',
            prop='revisions',
            titles=SONGS_PAGE,
            rvprop='ids|timestamp|content',
            rvslots='main',
            curtimestamp=1,
        )
        page = data.get('query', {}).get('pages', [])[0]
        revision = page['revisions'][0]
        wikitext = revision.get('slots', {}).get('main', {}).get('content', '')
        return (
            str(wikitext),
            int(revision['revid']),
            str(revision['timestamp']),
            str(data['curtimestamp']),
        )

    def resolve_page_ids(self, titles: Iterable[str]) -> dict[str, int]:
        result: dict[str, int] = {}
        title_list = list(dict.fromkeys(titles))
        total_batches = (len(title_list) + 49) // 50
        for offset in range(0, len(title_list), 50):
            batch = title_list[offset : offset + 50]
            batch_number = offset // 50 + 1
            print(f'  解析链接重定向批次：{batch_number}/{total_batches}', end='\r', flush=True)
            data = self.request(
                action='query',
                prop='info',
                titles='|'.join(batch),
                redirects=1,
            )
            query = data.get('query', {})
            edges: dict[str, str] = {}
            for item in query.get('normalized', []):
                edges[str(item['from'])] = str(item['to'])
            for item in query.get('redirects', []):
                edges[str(item['from'])] = str(item['to'])
            page_ids = {
                str(page['title']): int(page['pageid'])
                for page in query.get('pages', [])
                if not page.get('missing') and 'pageid' in page
            }
            for original in batch:
                target = original
                visited: set[str] = set()
                while target in edges and target not in visited:
                    visited.add(target)
                    target = edges[target]
                if target in page_ids:
                    result[original] = page_ids[target]
                    continue
                # API 可能只做了首字母规范化而未返回 normalized 映射。
                matching = next(
                    (pageid for title, pageid in page_ids.items() if title.casefold() == target.casefold()),
                    None,
                )
                if matching is not None:
                    result[original] = matching
        if title_list:
            print(f'  解析链接重定向批次：{total_batches}/{total_batches}')
        return result

    def login(self, username: str, password: str) -> None:
        token_data = self.request(action='query', meta='tokens', type='login')
        login_token = token_data['query']['tokens']['logintoken']
        result = self.request(
            'POST',
            action='login',
            lgname=username,
            lgpassword=password,
            lgtoken=login_token,
        ).get('login', {})
        if result.get('result') != 'Success':
            raise WikiApiError(
                f"登录失败：{result.get('result', 'Unknown')} {result.get('reason', '')}".strip()
            )
        userinfo = self.request(action='query', meta='userinfo')['query']['userinfo']
        if userinfo.get('anon') or not userinfo.get('name'):
            raise WikiApiError('登录接口返回成功，但当前会话仍是匿名状态')
        print(f"已登录为：{userinfo['name']}")

    def edit_songs_page(
        self,
        text: str,
        summary: str,
        base_timestamp: str,
        start_timestamp: str,
    ) -> int:
        token_data = self.request(action='query', meta='tokens', type='csrf')
        csrf_token = token_data['query']['tokens']['csrftoken']
        data = self.request(
            'POST',
            **{
                'action': 'edit',
                'title': SONGS_PAGE,
                'text': text,
                'summary': summary,
                'token': csrf_token,
                'basetimestamp': base_timestamp,
                'starttimestamp': start_timestamp,
                'assert': 'user',
                'nocreate': 1,
            },
        )
        edit = data.get('edit', {})
        if edit.get('result') != 'Success':
            raise WikiApiError(f'编辑失败：{edit}')
        return int(edit['newrevid'])


def clean_inline_wikitext(value: str) -> str:
    value = re.sub(r'<ref\b[^>]*>.*?</ref\s*>|<ref\b[^>]*/\s*>', '', value, flags=re.I | re.S)
    value = re.sub(r'<br\s*/?>', ' ', value, flags=re.I)
    code = mwparserfromhell.parse(value)
    for link in reversed(code.filter_wikilinks(recursive=True)):
        code.replace(link, str(link.text if link.text is not None else link.title))
    # 不使用 strip_code：当可见文字以 # 或 : 开头时，它会误当成列表/缩进语法而吞掉字符。
    text = str(code)
    text = re.sub(r'\[(?:https?:)?//\S+\s+([^\]]+)\]', r'\1', text)
    text = re.sub(r"'{2,}", '', text)
    text = html.unescape(re.sub(r'<[^>]+>', '', text))
    return re.sub(r'\s+', ' ', text).strip()


def clean_display_title(value: str) -> str:
    return re.sub(r'\s+', ' ', html.unescape(re.sub(r'<[^>]+>', '', value))).strip()


def extract_version(value: str) -> str:
    plain = clean_inline_wikitext(value)
    mobile = re.search(r'\bMobile\s*:\s*(\d+(?:\.\d+){1,3})', plain, flags=re.I)
    match = mobile or re.search(r'\d+(?:\.\d+){1,3}', plain)
    if not match:
        raise ValueError(f'无法从 Version 字段提取移动版版本号：{value!r}')
    return match.group(0) if mobile is None else mobile.group(1)


def parse_song_page(page: WikiPage) -> tuple[SongRecord | None, str | None]:
    code = mwparserfromhell.parse(page.wikitext)
    template = next(
        (
            item
            for item in code.filter_templates(recursive=True)
            if str(item.name).strip().casefold() == 'song'
        ),
        None,
    )
    if template is None:
        return None, '没有 {{Song}} 模板'

    values: dict[str, str] = {}
    missing: list[str] = []
    for field in REQUIRED_FIELDS:
        raw = str(template.get(field).value).strip() if template.has(field) else ''
        values[field] = raw
        if not raw:
            missing.append(field)
    if missing:
        return None, f"缺少必填字段：{', '.join(missing)}"

    raw_id = clean_inline_wikitext(values['Id'])
    if not raw_id.isdigit():
        return None, f'Id 不是整数：{raw_id!r}'
    try:
        difficulties = [clean_inline_wikitext(values[field]) for field in DIFFICULTY_FIELDS]
        for difficulty in difficulties:
            if not re.fullmatch(r'\d+\+?', difficulty):
                raise ValueError(f'不支持的难度格式：{difficulty!r}')
        song = clean_inline_wikitext(values['Song'])
        display_title = clean_display_title(page.display_title) or song
        record = SongRecord(
            pageid=page.pageid,
            page_title=page.title,
            display_title=display_title,
            song=song,
            artist=clean_inline_wikitext(values['Artist']),
            chapter=clean_inline_wikitext(values['Chapter']),
            song_id=int(raw_id),
            whisper=difficulties[0],
            acoustic=difficulties[1],
            ultra=difficulties[2],
            master=difficulties[3],
            duration=clean_inline_wikitext(values['Time']),
            bpm=clean_inline_wikitext(values['BPM']),
            version=extract_version(values['Version']),
        )
        for cell in (
            record.page_title,
            record.display_title,
            record.artist,
            record.chapter,
            record.duration,
            record.bpm,
            record.version,
        ):
            if not cell or '\n' in cell or '\r' in cell or '||' in cell:
                raise ValueError(f'字段无法安全写入单行表格：{cell!r}')
        return record, None
    except ValueError as exc:
        return None, str(exc)


def split_songs_table(wikitext: str) -> tuple[str, list[str], str]:
    start = wikitext.find(TABLE_START)
    if start < 0:
        raise ValueError('找不到 Songs 页的 wikitable 起点，页面结构可能已变化')
    close = wikitext.find('\n|}', start)
    if close < 0:
        raise ValueError('找不到 Songs 页的 wikitable 终点，页面结构可能已变化')
    table_end = close + len('\n|}')
    table = wikitext[start:table_end]
    lines = table.splitlines()
    first_data = next((i for i, line in enumerate(lines) if line.startswith('|[[')), None)
    if first_data is None:
        raise ValueError('Songs 表格内没有识别到歌曲数据行')
    header = '\n'.join(lines[:first_data])
    data_lines = [line for line in lines[first_data:] if line.startswith('|[[')]
    return wikitext[:start] + header, data_lines, wikitext[table_end:]


def parse_existing_row(raw: str) -> ExistingRow:
    cells = raw[1:].split('||')
    if len(cells) != 10:
        raise ValueError(f'Songs 表格行不是预期的 10 列：{raw}')
    code = mwparserfromhell.parse(cells[0])
    links = code.filter_wikilinks(recursive=True)
    if len(links) != 1:
        raise ValueError(f'标题单元格不含唯一 wikilink：{cells[0]}')
    link_title = str(links[0].title).strip()
    chapter_label = cells[2].rsplit('|', 1)[-1].strip()
    chapter_match = re.fullmatch(r'(.+)-(\d+)', chapter_label)
    if not chapter_match:
        raise ValueError(f'无法识别章节字段：{cells[2]}')
    chapter = chapter_match.group(1)
    if chapter == 'Event':
        chapter = 'Time Limited'
    return ExistingRow(
        raw=raw,
        link_title=link_title,
        title_cell=cells[0],
        chapter=chapter,
        song_id=int(chapter_match.group(2)),
    )


def escape_link_label(value: str) -> str:
    return value.replace('|', '&#124;').replace('[', '&#91;').replace(']', '&#93;')


def render_title(record: SongRecord) -> str:
    target = record.page_title.replace('_', ' ')
    label = record.display_title or record.song
    if target == label:
        return f'[[{target}]]'
    return f'[[{target}|{escape_link_label(label)}]]'


def render_difficulty(value: str) -> str:
    match = re.fullmatch(r'(\d+)(\+?)', value)
    if not match:
        raise ValueError(f'不支持的难度格式：{value!r}')
    level = int(match.group(1))
    plus = bool(match.group(2))
    display = f"'''{value}'''" if level >= 16 else value
    if plus:
        return f'data-sort-value="{level}.5"|{display}'
    return display


def render_chapter(record: SongRecord) -> str:
    if record.group == 'event':
        return f'data-sort-value="ZZZ{record.song_id}"|Event-{record.song_id}'
    if record.group == 'infinity':
        return f'data-sort-value="ZZ{record.song_id}"|∞-{record.song_id}'
    return f'{record.chapter}-{record.song_id}'


def render_chapter_label(record: SongRecord) -> str:
    """用于日志/预览的纯章节编号，不包含表格排序代码。"""
    if record.group == 'event':
        return f'Event-{record.song_id}'
    if record.group == 'infinity':
        return f'∞-{record.song_id}'
    return f'{record.chapter}-{record.song_id}'


def render_row(record: SongRecord, title_cell: str | None = None) -> str:
    cells = (
        title_cell or render_title(record),
        record.artist,
        render_chapter(record),
        render_difficulty(record.whisper),
        render_difficulty(record.acoustic),
        render_difficulty(record.ultra),
        render_difficulty(record.master),
        record.duration,
        record.bpm,
        record.version,
    )
    return '|' + '||'.join(cells)


def version_key(version: str) -> tuple[int, ...]:
    return tuple(int(part) for part in version.split('.'))


def update_version_note(wikitext: str, records: Iterable[SongRecord]) -> str:
    latest = max((record.version for record in records), key=version_key)
    pattern = r'(this table is currently updated to mobile version )[^.]+(?:\.[^.]+)*?(\. All versions)'
    updated, count = re.subn(pattern, rf'\g<1>{latest}\g<2>', wikitext, count=1, flags=re.I)
    if count != 1:
        print('警告：未能自动更新页面说明中的 mobile version，表格同步不受影响。')
        return wikitext
    return updated


def build_synced_page(
    old_wikitext: str,
    records: list[SongRecord],
    page_ids_by_link: dict[str, int],
    add_only: bool,
) -> BuildResult:
    prefix, raw_rows, suffix = split_songs_table(old_wikitext)
    existing_rows = [parse_existing_row(row) for row in raw_rows]
    records_by_pageid = {record.pageid: record for record in records}
    if len(records_by_pageid) != len(records):
        raise ValueError('API 返回了重复 pageid 的歌曲页')

    output_rows: list[str] = []
    used_pageids: set[int] = set()
    changed: list[ChangedRow] = []
    retained: list[ExistingRow] = []
    unchanged_count = 0

    for row in existing_rows:
        pageid = page_ids_by_link.get(row.link_title)
        record = records_by_pageid.get(pageid) if pageid is not None else None
        if record is None:
            output_rows.append(row.raw)
            retained.append(row)
            continue
        used_pageids.add(record.pageid)
        # 既有标题单元格可能特意使用简称、别名或特殊显示文字；同步字段时原样保留它。
        new_row = row.raw if add_only else render_row(record, title_cell=row.title_cell)
        output_rows.append(new_row)
        if new_row == row.raw:
            unchanged_count += 1
        else:
            changed.append(ChangedRow(record=record, old_raw=row.raw, new_raw=new_row))

    added = [record for record in records if record.pageid not in used_pageids]
    new_normal = sorted(
        (record for record in added if record.group == 'normal'),
        key=lambda item: (item.pageid, item.chapter.casefold(), item.song_id),
    )
    new_event = sorted(
        (record for record in added if record.group == 'event'), key=lambda item: item.song_id
    )
    new_infinity = sorted(
        (record for record in added if record.group == 'infinity'), key=lambda item: item.song_id
    )

    def first_index(group: str) -> int:
        for index, row_text in enumerate(output_rows):
            parsed = parse_existing_row(row_text)
            if group == 'event' and parsed.chapter == 'Time Limited':
                return index
            if group == 'infinity' and parsed.chapter == '∞':
                return index
        return len(output_rows)

    event_index = first_index('event')
    output_rows[event_index:event_index] = [render_row(record) for record in new_normal]
    infinity_index = first_index('infinity')
    output_rows[infinity_index:infinity_index] = [render_row(record) for record in new_event]
    output_rows.extend(render_row(record) for record in new_infinity)

    table_text = prefix + '\n' + '\n|-\n'.join(output_rows) + '\n|}' + suffix
    if not add_only:
        table_text = update_version_note(table_text, records)
    return BuildResult(
        wikitext=table_text,
        added=added,
        changed=changed,
        unchanged_count=unchanged_count,
        retained_rows=retained,
    )


def write_preview(output_dir: Path, old_text: str, new_text: str) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    preview_path = output_dir / 'lanota_songs_preview.wikitext'
    diff_path = output_dir / 'lanota_songs_preview.diff'
    preview_path.write_text(new_text, encoding='utf-8', newline='\n')
    diff = ''.join(
        difflib.unified_diff(
            old_text.splitlines(keepends=True),
            new_text.splitlines(keepends=True),
            fromfile='Songs（当前）',
            tofile='Songs（同步后）',
        )
    )
    diff_path.write_text(diff, encoding='utf-8', newline='\n')
    return preview_path, diff_path


def describe_changed_row(change: ChangedRow) -> str:
    column_names = ('标题', '艺术家', '章节', 'Whisper', 'Acoustic', 'Ultra', 'Master', '时长', 'BPM', '版本')
    old_cells = change.old_raw[1:].split('||')
    new_cells = change.new_raw[1:].split('||')
    differences = [
        f'{name}: {old} -> {new}'
        for name, old, new in zip(column_names, old_cells, new_cells)
        if old != new
    ]
    return '；'.join(differences)


def print_summary(
    result: BuildResult,
    invalid_pages: list[tuple[str, str]],
    show_details: bool,
) -> None:
    print('\n同步检查完成：')
    print(f'  新增歌曲：{len(result.added)}')
    for record in result.added:
        print(f'    + {render_chapter_label(record)}  {record.display_title}')
    print(f'  已有歌曲字段变化：{len(result.changed)}')
    if show_details:
        for change in result.changed:
            print(f'    * {render_chapter_label(change.record)}  {change.record.display_title}')
            print(f'      {describe_changed_row(change)}')
    print(f'  已有歌曲无变化：{result.unchanged_count}')
    print(f'  无法匹配、因此原样保留的旧行：{len(result.retained_rows)}')
    for row in result.retained_rows:
        print(f'    ! {row.link_title}')
    print(f'  字段不完整、已跳过的候选页面：{len(invalid_pages)}')
    for title, reason in invalid_pages:
        print(f'    ! {title}: {reason}')


def build_difference_text(result: BuildResult, invalid_pages: list[tuple[str, str]]) -> str:
    """生成只包含差异项的简明预览，供机器人命令直接回复。"""
    lines = []
    for record in result.added:
        lines.append(f'+ {render_chapter_label(record)} {record.display_title}')
    for change in result.changed:
        lines.append(f'* {render_chapter_label(change.record)} {change.record.display_title}')
        lines.append(f'  {describe_changed_row(change)}')
    for title, reason in invalid_pages:
        lines.append(f'! {title}: {reason}')
    return '\n'.join(lines) if lines else '没有差异。'


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description='只通过 MediaWiki API 将歌曲详情页同步到 Lanota Wiki 的 Songs 页面。'
    )
    parser.add_argument('--preview', action='store_true', help='只生成预览，不编辑 Wiki（默认行为）')
    parser.add_argument('--apply', action='store_true', help='登录并实际编辑 Songs；默认只预览')
    parser.add_argument('--yes', action='store_true', help='配合 --apply 跳过最后一次交互确认')
    parser.add_argument('--menu', action='store_true', help='显示交互式命令行菜单')
    parser.add_argument('--details', action='store_true', help='在终端列出每一项已有字段变化')
    parser.add_argument(
        '--add-only',
        action='store_true',
        help='只添加缺失歌曲，不刷新已有歌曲的字段和页面版本说明',
    )
    parser.add_argument(
        '--summary',
        default='Sync song list from individual song pages via MediaWiki API',
        help='Wiki 编辑摘要',
    )
    parser.add_argument('--timeout', type=float, default=30.0, help='单次 API 请求超时秒数')
    args = parser.parse_args()
    if args.menu or (len(sys.argv) == 1 and sys.stdin.isatty()):
        print('\n=== Lanota Songs API 同步器 ===')
        print('编辑账号：从 plugin/data/LanotaPlugin/global_config.json 读取')
        print('1. 完整同步预览（显示详细变化）')
        print('2. 只添加缺失歌曲预览')
        print('3. 完整同步并编辑 Wiki')
        print('4. 只添加缺失歌曲并编辑 Wiki')
        print('0. 退出')
        try:
            choice = input('请选择操作 [0-4]：').replace('\x00', '').strip().lstrip('\ufeff')
        except EOFError:
            print('\n未检测到交互式输入，自动切换为完整同步预览。')
            return args
        if choice == '0':
            raise SystemExit(0)
        if choice not in {'1', '2', '3', '4'}:
            raise SystemExit('无效选项，已退出。')
        args.add_only = choice in {'2', '4'}
        args.apply = choice in {'3', '4'}
        args.details = choice in {'1', '3'}
    return args


def run_sync(
    username: str = '',
    password: str = '',
    apply: bool = False,
    add_only: bool = False,
    summary: str = 'Sync song list from individual song pages via MediaWiki API',
    timeout: float = 30.0,
    show_details: bool = False,
    output_dir: str | Path | None = None,
    confirm_callback=None,
) -> dict[str, Any]:
    """执行一次 Songs 同步，可供 CLI 和 LanotaPlugin 骰主命令共同调用。"""
    preview_dir = Path(output_dir) if output_dir else Path(__file__).resolve().parent
    client = MediaWikiClient(timeout=timeout)

    print('正在通过 API 读取 Songs 页面……')
    old_text, old_revid, base_timestamp, start_timestamp = client.fetch_songs_page()
    print(f'当前 Songs 修订版本：{old_revid}')

    print('正在通过 embeddedin 与 categorymembers API 发现歌曲页……')
    candidate_titles = client.discover_song_titles()
    print(f'候选页面：{len(candidate_titles)}')

    print('正在批量读取并校验 {{Song}} 模板……')
    records: list[SongRecord] = []
    invalid_pages: list[tuple[str, str]] = []
    for page in client.fetch_pages(candidate_titles):
        record, error = parse_song_page(page)
        if record is None:
            invalid_pages.append((page.title, error or '未知原因'))
        else:
            records.append(record)
    print(f'字段完整的歌曲页：{len(records)}')

    _, raw_rows, _ = split_songs_table(old_text)
    existing_rows = [parse_existing_row(row) for row in raw_rows]
    print('正在通过 API 解析 Songs 现有链接及重定向……')
    page_ids_by_link = client.resolve_page_ids(row.link_title for row in existing_rows)

    result = build_synced_page(old_text, records, page_ids_by_link, add_only)
    difference_text = build_difference_text(result, invalid_pages)
    print_summary(result, invalid_pages, show_details)
    preview_path, diff_path = write_preview(preview_dir, old_text, result.wikitext)
    print(f'\n完整预览：{preview_path}')
    print(f'差异预览：{diff_path}')

    if result.wikitext == old_text:
        print('Songs 页面已经与歌曲详情同步，无需编辑。')
        return {
            'changed': 0,
            'added': 0,
            'invalid': len(invalid_pages),
            'edited': False,
            'old_revid': old_revid,
            'new_revid': old_revid,
            'preview_path': str(preview_path),
            'diff_path': str(diff_path),
            'difference_text': difference_text,
        }
    if not apply:
        print('\n当前是预览模式，没有修改 Wiki。确认差异后使用 --apply。')
        return {
            'changed': len(result.changed),
            'added': len(result.added),
            'invalid': len(invalid_pages),
            'edited': False,
            'old_revid': old_revid,
            'new_revid': None,
            'preview_path': str(preview_path),
            'diff_path': str(diff_path),
            'difference_text': difference_text,
        }

    if not username.strip() or not password.strip():
        raise ValueError('未配置 wiki_sync_username 或 wiki_sync_bot_password')
    if callable(confirm_callback) and not confirm_callback():
        print('已取消，没有修改 Wiki。')
        return {
            'changed': len(result.changed),
            'added': len(result.added),
            'invalid': len(invalid_pages),
            'edited': False,
            'cancelled': True,
            'old_revid': old_revid,
            'new_revid': None,
            'preview_path': str(preview_path),
            'diff_path': str(diff_path),
            'difference_text': difference_text,
        }

    client.login(username, password)
    new_revid = client.edit_songs_page(
        result.wikitext,
        summary,
        base_timestamp,
        start_timestamp,
    )
    print(f'编辑成功，新修订版本：{new_revid}')
    return {
        'changed': len(result.changed),
        'added': len(result.added),
        'invalid': len(invalid_pages),
        'edited': True,
        'old_revid': old_revid,
        'new_revid': new_revid,
        'preview_path': str(preview_path),
        'diff_path': str(diff_path),
        'difference_text': difference_text,
    }


def load_cli_wiki_config() -> dict[str, Any]:
    """独立运行时读取 LanotaPlugin 的运行期全局配置。"""
    config_path = Path.cwd() / 'plugin' / 'data' / 'LanotaPlugin' / 'global_config.json'
    try:
        data = json.loads(config_path.read_text(encoding='utf-8'))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def main() -> int:
    args = parse_args()
    global_config = load_cli_wiki_config()

    def confirm_edit() -> bool:
        if args.yes:
            return True
        answer = input('\n确认要用上述内容编辑 Lanota Wiki 的 Songs 页面吗？[y/N] ').strip().casefold()
        return answer in {'y', 'yes'}

    run_sync(
        username=str(global_config.get('wiki_sync_username', '')),
        password=str(global_config.get('wiki_sync_bot_password', '')),
        apply=args.apply,
        add_only=args.add_only,
        summary=str(global_config.get('wiki_sync_edit_summary', args.summary)) or args.summary,
        timeout=args.timeout,
        show_details=args.details,
        confirm_callback=confirm_edit if args.apply else None,
    )
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (requests.RequestException, WikiApiError, ValueError) as exc:
        print(f'错误：{exc}', file=sys.stderr)
        raise SystemExit(1) from exc

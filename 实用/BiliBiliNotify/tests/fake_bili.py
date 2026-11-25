from contextlib import contextmanager
from copy import deepcopy
from unittest.mock import patch

LIVE_URL = 'https://i0.hdslb.com/bfs/live/cover.jpg'
VIDEO_URL = 'https://i0.hdslb.com/bfs/archive/cover.jpg'
LIVE = {
    'uid': 2, 'room_id': 1024, 'uname': '碧诗', 'live_status': 1, 'live_time': 1764000123,
    'title': '试播', 'area_v2_name': '虚拟主播', 'cover_from_user': LIVE_URL,
}


def dynamic(item_id, stamp, *, pinned=False, video=False):
    return {
        'id_str': str(item_id), 'type': 'DYNAMIC_TYPE_AV' if video else 'DYNAMIC_TYPE_DRAW',
        'modules': {
            'module_tag': {'text': '置顶' if pinned else ''},
            'module_author': {'pub_ts': stamp, 'name': '碧诗'},
            'module_dynamic': {'desc': {'text': '新动态'}},
        },
    }


def video(bvid, stamp):
    return {'bvid': bvid, 'created': stamp, 'title': '新视频', 'pic': VIDEO_URL, 'author': '碧诗'}


@contextmanager
def api_fixtures(api):
    """仅替换上游端点，保留实际的 UID 两级解析、绑定和状态机。"""
    def live_status(uids):
        return {str(uid): deepcopy(LIVE) for uid in uids if str(uid) == '2'}, None

    def master_info(uid):
        return ({'room_id': 0, 'info': {'uname': '未开播的主播'}} if str(uid) == '3' else {}), None

    with patch.multiple(
        api, live_status=live_status, master_info=master_info,
        dynamics=lambda uid: ([dynamic('197', 100)], None),
        videos=lambda uid: ([video('BV1Fixture', 100)], None),
        navnum=lambda uid: ({'video': 1, 'opus': 1}, None),
    ):
        yield

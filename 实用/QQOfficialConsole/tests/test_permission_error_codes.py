"""长错误码（err_code）权限提示回归，全程离线，不访问网络/生产实例。

背景：QQ 群管理接口的错误响应同时带短码 ``code`` 与长码 ``err_code``，例如
``HTTP 403 {"code": 11253, "err_code": 40012010, "message": "..."}``。
OlivOS 的 ``_get_api_error_code`` 优先取 ``err_code``，所以
``universal_result['data']['error_code']`` 是 ``40012010``；旧 ``errors.CODES``
只有 ``11253``，提示落到「未知错误」。

这里的 raw 一律由 SDK 自己的 ``_make_api_result`` 生成，避免手搓字典掩盖
适配器结构变化。长码对应只登记有实证的三对，不按号段猜。
"""
import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import OlivOS  # noqa: E402,F401  确保适配器运行期符号已绑定
from OlivOS.adapter.qqGuild import qqGuildv2SDK as sdk_facade  # noqa: E402
from OlivOS.adapter.qqGuild import qqGuildv2SDKCommon as sdk_common  # noqa: E402,F401


def _load_errors():
    """直接加载 errors.py，避免包 __init__ 把 webui/main 拖进单测。"""
    path = ROOT / 'QQOfficialConsole' / 'errors.py'
    spec = importlib.util.spec_from_file_location('qqconsole_errors_under_test', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


errors = _load_errors()


def universal_result(body, status=403, operation='send'):
    """用 SDK 真实实现构造 universal_result（失败路径，不注册已发消息）。"""
    api_obj = SimpleNamespace(
        res=json.dumps(body, ensure_ascii=False),
        res_code=status,
        data=SimpleNamespace(content=None),
    )
    target_event = SimpleNamespace(bot_info=SimpleNamespace(hash='offline-bot'))
    return sdk_facade.event_action._make_api_result(
        target_event, api_obj, 'qq_group', 'group-openid', operation
    )


def test_live_permission_response_maps_long_err_code():
    """线上真实响应：code=11253 + err_code=40012010 应提示无接口权限。"""
    raw = universal_result({
        'code': 11253,
        'err_code': 40012010,
        'message': '应用无接口访问权限',
        'trace_id': 'trace-offline',
    })
    assert raw['active'] is False
    assert raw['data']['error_code'] == 40012010  # SDK 优先 err_code 的前提

    out = errors.result(raw)
    assert out['ok'] is False
    assert out['keyword'] == '无接口权限'
    assert out['error_code'] == 40012010
    assert 'message' not in out
    assert '应用无接口访问权限' not in str(out)


def test_short_permission_code_still_maps():
    """短码回归：SDK 只拿到 code=11253 时行为不变。"""
    out = errors.result(universal_result({'code': 11253, 'message': 'denied'}))
    assert out['ok'] is False
    assert out['keyword'] == '无接口权限'
    assert out['error_code'] == 11253


@pytest.mark.parametrize('body, expected', [
    ({'code': 11255, 'message': '请求的资源不存在(用户/群已注销)'}, 11255),
    ({'code': 11255, 'err_code': 40011028,
      'message': '请求的资源不存在(用户/群已注销)'}, 40011028),
])
def test_resource_missing_short_and_long_agree(body, expected):
    """OlivOS 日志中 11255 与 40011028 成对出现（26 行成对、0 行落单），长短码提示应一致。"""
    out = errors.result(universal_result(body, status=400))
    assert out['ok'] is False
    assert out['keyword'] == '资源不存在'
    assert out['error_code'] == expected


@pytest.mark.parametrize('body', [
    {'code': 11703, 'message': '机器人不是群管理员'},
    {'code': 11703, 'err_code': 40011030, 'message': '机器人不是群管理员'},
])
def test_group_admin_error_uses_readable_message(body):
    out = errors.result(universal_result(body, status=400))
    assert out['keyword'] == '机器人不是群管理员'


def test_alias_table_only_holds_verified_pairs():
    """长码表必须可追溯到实证，且与短码共用关键词。"""
    assert errors.LONG_CODE_ALIASES == {40012010: 11253, 40011028: 11255, 40011030: 11703}
    for long_code, short_code in errors.LONG_CODE_ALIASES.items():
        assert errors.CODES[long_code] == errors.CODES[short_code]
        assert errors.CODES[short_code] in ('无接口权限', '资源不存在', '机器人不是群管理员')


def test_only_verified_group_api_long_codes_are_registered():
    """4001xxxx 号段只登记已确证的群接口长码，避免按邻居号臆造。"""
    registered = {code for code in errors.CODES if 40010000 <= code < 40020000}
    assert registered == set(errors.LONG_CODE_ALIASES)


def test_unknown_long_code_stays_unknown_with_message():
    """不在表里的码仍报未知错误，并保留平台原文便于排查。"""
    out = errors.result(universal_result({
        'code': 49999999, 'err_code': 49999998, 'message': 'unmapped detail',
    }))
    assert out['keyword'] == '未知错误'
    assert out['message'] == 'unmapped detail'

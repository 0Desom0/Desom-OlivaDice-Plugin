"""真实 OlivOS 消息解析和 SDK 封装，网络边界全部替换。"""

import copy
import importlib.util
import json
import sys
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import OlivOS
import pytest
from OlivOS.adapter.qqGuild import qqGuildv2SDKCommon as common
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from QQGroupAuthorize import config, main, renderer, resources, transport  # noqa: E402

SDK = OlivOS.qqGuildv2SDK


@pytest.fixture(autouse=True)
def isolated_plugin_data(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)


@pytest.fixture
def context(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    bot = OlivOS.API.bot_info_T(
        id=23001,
        platform_sdk='qqGuildv2_link',
        platform_platform='qqGuild',
        platform_model='public',
    )
    for name in (
        'qqEventDedupeCache',
        'sdkUserInfo',
        'sdkSubSelfInfo',
        'sdkRxMessageInfo',
        'sdkMsgIdxInfo',
        'sdkMsgidinfo',
        'sdkEventidinfo',
        'sdkUnhandledEventInfo',
    ):
        monkeypatch.setattr(common, name, {})
    monkeypatch.setattr(common, 'sdkSelfInfo', {bot.hash: {'id': 'bot', 'username': '橘波特'}})
    monkeypatch.setattr(common, '_get_qq_group_self_open_id', lambda *args: 'bot')
    monkeypatch.setattr(common.req, 'request', Mock(side_effect=AssertionError('Unexpected network')))
    main.Event.save(None, None)
    proc = Mock()
    proc.Proc_data = {'bot_info_dict': {bot.hash: bot}}
    resources._avatar_cache.clear()
    monkeypatch.setattr(resources.requests, 'get', Mock(side_effect=AssertionError('Unexpected avatar network')))
    monkeypatch.setitem(sys.modules, 'OlivaDiceCore', None)
    sent = []

    def do_api(api, *args, **kwargs):
        # 所有命令回复引用触发消息、不 @；入群事件保持无引用。
        if api.data.msg_id:
            assert api.data.message_reference == {'message_id': 'REFIDX_original'}
        else:
            assert api.data.message_reference is None
        assert '<qqbot-at-' not in (api.data.content or '')
        sent.append(copy.deepcopy(api.data.__dict__))
        api.res = '{"id":"sent","timestamp":"2026-10-09T12:00:00+08:00"}'
        api.res_code = 200

    monkeypatch.setattr(SDK.API.sendQQMessage, 'do_api', do_api)
    monkeypatch.setattr(SDK.event_action, 'setResourceUploadFast', Mock(return_value='uploaded-image'))
    monkeypatch.setattr(renderer, 'guide_image', Mock(return_value=renderer.ImageResult(b'image')))
    monkeypatch.setattr(
        transport.GroupReply,
        'authorization',
        Mock(side_effect=AssertionError('Authorization entry is disabled')),
    )
    return bot, proc, sent


def group_event(bot, content='.授权全消息', message_id='original-message', group_id='current-group'):
    payload = SDK.PAYLOAD.rxPacket(
        {
            'op': 0,
            's': 1,
            't': 'GROUP_AT_MESSAGE_CREATE',
            'd': {
                'id': message_id,
                'author': {'member_openid': 'member', 'username': '测试用户'},
                'group_openid': group_id,
                'content': content,
                'message_scene': {'ext': ['msg_idx=REFIDX_original']},
                'timestamp': '2026-10-09T12:00:00+08:00',
            },
        }
    )
    event = OlivOS.API.Event(SDK.event(payload, bot))
    event.bot_info = bot
    event.data.message = event.data.message_sdk
    return event


def join_event(bot, event_id='GROUP_ADD_ROBOT:original-join', group_id='new-group'):
    payload = SDK.PAYLOAD.rxPacket(
        {
            'op': 0,
            's': 2,
            't': 'GROUP_ADD_ROBOT',
            'id': event_id,
            'd': {'group_openid': group_id, 'op_member_openid': 'owner', 'timestamp': '2026-10-09T12:00:00+08:00'},
        }
    )
    event = OlivOS.API.Event(SDK.event(payload, bot))
    event.bot_info = bot
    return event


def grant_plugin_master(user_id='member'):
    value = config.load()
    value['masters'] = [user_id]
    config.save(value)


@pytest.mark.parametrize('prefix', ['.', '/', '。'])
@pytest.mark.parametrize('root,subcommand', [('授权', '入群'), ('auth', 'join')])
@pytest.mark.parametrize('spacing', ['', ' ', '\t'])
def test_join_actions_work_without_token_splitting(context, prefix, root, subcommand, spacing):
    bot, proc, sent = context
    grant_plugin_master()
    for index, (argument, enabled) in enumerate([('on', True), ('off', False), ('状态', False)]):
        command = prefix + spacing.join((root, subcommand, argument))
        main.Event.group_message(group_event(bot, command, message_id=f'action-{index}'), proc)
        assert config.auto_join_enabled(bot.hash) is enabled
    assert len(sent) == 3 and all(item['msg_type'] == 0 for item in sent)


@pytest.mark.parametrize(
    'command',
    [
        '.授权入群开多余',
        '/authjoinonward',
        '。authjoinon off',
        '.authjoinstat us',
        '.授权入群状态 123',
    ],
)
def test_invalid_join_tail_never_changes_setting(context, command):
    bot, proc, sent = context
    grant_plugin_master()
    previous = (config.ROOT / 'config.json').read_bytes()
    main.Event.group_message(group_event(bot, command), proc)
    assert len(sent) == 1 and '用法' in sent[0]['content']
    assert (config.ROOT / 'config.json').read_bytes() == previous


def test_longest_keyword_wins_and_retains_remaining_argument():
    assert main.match_keyword(' ALLMSGon ', ('all', 'allmsg')) == ('allmsg', 'on')
    assert main.match_keyword('入群状态', ('入', '入群')) == ('入群', '状态')
    assert main.match_keyword('auth join on', ('auth', '授权')) == ('auth', 'join on')


@pytest.mark.parametrize(
    'command', ['.授权帮助', '/authhelp', '。AUTHHELP', '.授权 帮助', '/auth help', '.授权', '。auth']
)
def test_help_is_public_and_never_changes_configuration(context, command):
    bot, proc, sent = context
    main.Event.group_message(group_event(bot, command), proc)
    assert [payload['msg_type'] for payload in sent] == [0]
    for example in (
        '.授权 全消息',
        '.auth allmsg',
        '.授权 帮助',
        '.auth help',
        '.授权 入群 开',
        '.auth join on',
        '.授权 入群 关',
        '.auth join off',
        '.授权 入群 状态',
        '.auth join status',
    ):
        assert example in sent[0]['content']
    assert 'Spaces are optional.' in sent[0]['content']
    assert 'Permission:' in sent[0]['content']
    assert 'Saved per bot hash' in sent[0]['content']
    assert '需要手机 QQ 9.2.90 及以上。' in sent[0]['content']
    assert 'Requires mobile QQ 9.2.90 or later.' in sent[0]['content']
    assert '仅限手机 QQ，电脑端目前不可用；低于该版本，请群主先更新 QQ。' in sent[0]['content']
    assert 'Mobile QQ only; desktop QQ is currently unsupported.' in sent[0]['content']
    assert 'User ID：member' in sent[0]['content']
    assert not config.auto_join_enabled(bot.hash)
    assert not (config.ROOT / 'config.json').exists()


@pytest.mark.parametrize(
    'command,enabled',
    [
        ('.授权入群开', True),
        ('/authjoin on', True),
        ('。authjoinON', True),
        ('.授权入群关', False),
        ('/authjoinoff', False),
        ('。授权 入群 关', False),
    ],
)
def test_plugin_master_can_switch_current_bot_and_preserve_other_config(context, command, enabled):
    bot, proc, sent = context
    value = {'masters': ['member'], 'bots': {'another-bot': {'auto_join': True, 'custom': 123}}, 'unrelated': 'keep'}
    config.save(value)
    main.Event.group_message(group_event(bot, command), proc)
    assert [payload['msg_type'] for payload in sent] == [0]
    assert config.auto_join_enabled(bot.hash) is enabled
    saved = config.load()
    assert saved['bots']['another-bot'] == value['bots']['another-bot']
    assert saved['masters'] == ['member'] and saved['unrelated'] == 'keep'


@pytest.mark.parametrize(
    'command', ['.授权入群状态', '/authjoinstatus', '。authjoin', '.auth join status', '.授权 入群 状态']
)
def test_status_is_default_off_and_does_not_write(context, command):
    bot, proc, sent = context
    grant_plugin_master()
    previous = (config.ROOT / 'config.json').read_bytes()
    main.Event.group_message(group_event(bot, command), proc)
    assert '当前关闭' in sent[0]['content']
    assert (config.ROOT / 'config.json').read_bytes() == previous


@pytest.mark.parametrize('role', ['member', 'owner', 'admin'])
def test_group_roles_are_not_plugin_masters(context, role):
    bot, proc, sent = context
    event = group_event(bot, '.authjoin on')
    event.data.sender['role'] = role
    main.Event.group_message(event, proc)
    assert '仅骰主' in sent[0]['content']
    assert not config.auto_join_enabled(bot.hash)


@pytest.mark.parametrize(
    'core_master,plugin_master,allowed', [(True, False, True), (False, True, True), (False, False, False)]
)
def test_core_and_global_plugin_master_union(context, monkeypatch, core_master, plugin_master, allowed):
    bot, proc, sent = context
    core = SimpleNamespace(
        userConfig=SimpleNamespace(getUserHash=Mock(return_value='user-hash')),
        ordinaryInviteManager=SimpleNamespace(isInMasterList=Mock(return_value=core_master)),
    )
    monkeypatch.setitem(sys.modules, 'OlivaDiceCore', core)
    if plugin_master:
        grant_plugin_master()
    event = group_event(bot, '.authjoin on')
    main.Event.group_message(event, proc)
    assert config.auto_join_enabled(bot.hash) is allowed
    assert len(sent) == 1
    if not plugin_master:
        core.userConfig.getUserHash.assert_called_once_with('member', 'user', 'qqGuild')
        core.ordinaryInviteManager.isInMasterList.assert_called_once_with(bot.hash, 'user-hash')


def test_configuration_corruption_fails_closed_without_overwrite(context):
    bot, proc, sent = context
    resources.prepare_resources()
    path = config.ROOT / 'config.json'
    path.write_bytes(b'{bad json')
    main.Event.group_message(group_event(bot, '.authjoin on'), proc)
    assert 'JSON' in sent[0]['content']
    assert path.read_bytes() == b'{bad json'
    sent.clear()
    main.Event.group_member_increase(join_event(bot), proc)
    assert sent == []
    assert path.read_bytes() == b'{bad json'


def test_failed_config_write_keeps_old_switch(context, monkeypatch):
    bot, proc, sent = context
    grant_plugin_master()
    previous = (config.ROOT / 'config.json').read_bytes()
    monkeypatch.setattr(config.Path, 'replace', Mock(side_effect=OSError))
    main.Event.group_message(group_event(bot, '.authjoin on'), proc)
    assert '开关未改变' in sent[0]['content']
    assert (config.ROOT / 'config.json').read_bytes() == previous


def test_init_creates_default_off_for_each_bot_without_resetting_existing(context):
    bot, proc, _ = context
    another = copy.copy(bot)
    another.hash = 'another-bot'
    proc.Proc_data['bot_info_dict'][another.hash] = another
    main.Event.init_after(None, proc)
    saved = json.loads((config.ROOT / 'config.json').read_text(encoding='utf-8'))
    assert saved['browser_path'] == '' and saved['masters'] == []
    assert 'bot_name' not in saved
    assert not (config.ROOT / 'settings.json').exists()
    assert config.load()['bots'] == {
        bot.hash: {'name': '', 'auto_join': False},
        'another-bot': {'name': '', 'auto_join': False},
    }
    config.set_auto_join(bot.hash, True)
    main.Event.init_after(None, proc)
    assert config.auto_join_enabled(bot.hash) and not config.auto_join_enabled(another.hash)


def test_auto_join_default_off_does_not_render_or_send(context):
    bot, proc, sent = context
    event = join_event(bot)
    main.Event.group_member_increase(event, proc)
    assert sent == []
    renderer.guide_image.assert_not_called()
    assert not event.blocked


def test_bot_join_sends_one_event_reply_without_quote_and_keeps_core_welcome(context):
    bot, proc, sent = context
    config.set_auto_join(bot.hash, True)
    event = join_event(bot)
    assert event.plugin_info['func_type'] == 'group_member_increase'
    main.Event.group_member_increase(event, proc)
    assert [payload['msg_type'] for payload in sent] == [7]
    assert sent[0]['event_id'] == 'GROUP_ADD_ROBOT:original-join'
    assert sent[0]['msg_id'] is None and sent[0]['message_reference'] is None
    assert sent[0]['content'] == ''
    assert sent[0]['keyboard'] is None
    assert not event.blocked
    main.Event.group_member_increase(event, proc)
    main.Event.group_member_increase(join_event(bot, event_id='GROUP_ADD_ROBOT:duplicate-join'), proc)
    assert len(sent) == 1


@pytest.mark.parametrize('scenario', ['member', 'guild', 'other-sdk', 'no-event-id', 'different-bot-off'])
def test_join_only_targets_self_in_qq_group_with_enabled_bot(context, scenario):
    bot, proc, sent = context
    config.set_auto_join(bot.hash, True)
    event = join_event(bot)
    if scenario == 'member':
        event.data.user_id = 'new-member'
        event.data.extend['qq_event_type'] = 'GROUP_MEMBER_ADD'
    elif scenario == 'guild':
        event.data.host_id = 'guild-id'
        event.data.extend['flag_from_qq'] = False
    elif scenario == 'other-sdk':
        event.platform['sdk'] = 'onebot'
    elif scenario == 'no-event-id':
        event.data.extend.pop('event_id')
    else:
        another = copy.copy(bot)
        another.hash = 'other-bot'
        event.bot_info = another
    main.Event.group_member_increase(event, proc)
    assert sent == []
    assert not event.blocked


@pytest.mark.parametrize('failure', ['render', 'upload'])
def test_join_image_failures_use_same_event_reply(context, monkeypatch, failure):
    bot, proc, sent = context
    config.set_auto_join(bot.hash, True)
    if failure == 'render':
        monkeypatch.setattr(renderer, 'guide_image', Mock(return_value=renderer.ImageResult()))
    else:
        monkeypatch.setattr(SDK.event_action, 'setResourceUploadFast', Mock(return_value=None))
    main.Event.group_member_increase(join_event(bot), proc)
    assert [payload['msg_type'] for payload in sent] == [0]
    assert sent[0]['event_id'] == 'GROUP_ADD_ROBOT:original-join'
    assert sent[0]['message_reference'] is None
    assert '群成员列表' in sent[0]['content'] and '群机器人' in sent[0]['content']


@pytest.mark.parametrize(
    'command',
    [
        '.授权全消息',
        '/授权全消息',
        '。授权全消息',
        '.authallmsg',
        '/authallmsg',
        '。authallmsg',
        '/AUTHALLMSG',
        '.授权 全消息',
        '/auth allmsg',
    ],
)
def test_commands_send_only_one_quoted_image_without_at(context, command):
    bot, proc, sent = context
    event = group_event(bot, command)
    main.Event.group_message(event, proc)
    assert [payload['msg_type'] for payload in sent] == [7]
    assert all(payload['msg_id'] == 'original-message' for payload in sent)
    assert sent[0]['message_reference'] == {'message_id': 'REFIDX_original'}
    assert sent[0]['content'] == ''
    assert '\n' not in sent[0]['content']
    assert sent[0]['markdown'] is None and sent[0]['keyboard'] is None
    transport.GroupReply.authorization.assert_not_called()
    assert event.blocked


@pytest.mark.parametrize(
    'command',
    [
        '.authallmsg 123',
        '.授权全消息123',
        '.授权全消息 群号',
        '/bot',
        '授权全消息',
        '.allmessage',
        '.authallmessage',
        '.授权全消息 帮助',
        '.authallmsghelp',
        '.authhelp extra',
        '.authorizationallmsg',
    ],
)
def test_no_arguments_or_extra_commands(context, command):
    bot, proc, sent = context
    main.Event.group_message(group_event(bot, command), proc)
    assert sent == []


def test_at_self_is_allowed_but_at_other_is_not(context):
    bot, _, _ = context
    event = group_event(bot)
    event.data.message = OlivOS.messageAPI.Message_templet(
        'olivos_para',
        [
            OlivOS.messageAPI.PARA.at(str(bot.id)),
            OlivOS.messageAPI.PARA.text(' /authallmsg'),
        ],
    )
    assert main.is_command(event)
    event.data.extend['sub_self_open_id'] = 'group-bot-openid'
    event.data.message.data[0] = OlivOS.messageAPI.PARA.at('group-bot-openid')
    assert main.is_command(event)
    event.data.message.data[0] = OlivOS.messageAPI.PARA.at('other-user')
    assert not main.is_command(event)


@pytest.mark.parametrize('scenario', ['other_sdk', 'guild', 'private', 'host', 'direct'])
def test_other_scenarios_are_ignored(context, scenario):
    bot, proc, sent = context
    event = group_event(bot)
    if scenario == 'other_sdk':
        event.platform['sdk'] = 'onebot'
    elif scenario == 'guild':
        event.data.extend['flag_from_qq'] = False
    elif scenario == 'private':
        event.plugin_info['func_type'] = 'private_message'
    elif scenario == 'host':
        event.data.host_id = 'guild-id'
    else:
        event.data.extend['flag_from_direct'] = True
    main.Event.group_message(event, proc)
    assert sent == []


def test_duplicate_delivery_does_not_resend(context):
    bot, proc, sent = context
    event = group_event(bot)
    main.Event.group_message(event, proc)
    main.Event.group_message(event, proc)
    assert len(sent) == 1


@pytest.mark.parametrize('failure', ['render', 'exception', 'upload'])
def test_image_failures_send_only_manual_text(context, monkeypatch, failure):
    bot, proc, sent = context
    if failure == 'render':
        monkeypatch.setattr(renderer, 'guide_image', Mock(return_value=renderer.ImageResult()))
    elif failure == 'exception':
        monkeypatch.setattr(renderer, 'guide_image', Mock(side_effect=OSError))
    else:
        monkeypatch.setattr(SDK.event_action, 'setResourceUploadFast', Mock(return_value=None))
    main.Event.group_message(group_event(bot), proc)
    assert [item['msg_type'] for item in sent] == [0]
    assert sent[0]['message_reference'] == {'message_id': 'REFIDX_original'}
    assert '群成员列表' in sent[0]['content']
    assert '电脑端目前不可用' in sent[0]['content'] and '请群主先更新 QQ' in sent[0]['content']
    transport.GroupReply.authorization.assert_not_called()


def test_failed_image_send_uses_one_passive_text_fallback(context, monkeypatch):
    bot, proc, sent = context
    original = SDK.API.sendQQMessage.do_api

    def send(api, *args, **kwargs):
        original(api, *args, **kwargs)
        if api.data.msg_type == 7:
            api.res_code, api.res = 400, '{"code":400,"message":"image unavailable"}'

    monkeypatch.setattr(SDK.API.sendQQMessage, 'do_api', send)
    main.Event.group_message(group_event(bot), proc)
    assert [item['msg_type'] for item in sent] == [7, 0]
    assert all(item['msg_id'] == 'original-message' for item in sent)
    assert all(item['keyboard'] is None for item in sent)
    transport.GroupReply.authorization.assert_not_called()


def test_incoming_reply_segment_is_ignored_and_not_returned(context):
    bot, proc, sent = context
    event = group_event(bot)
    event.data.message = OlivOS.messageAPI.Message_templet(
        'olivos_para',
        [
            OlivOS.messageAPI.PARA.reply('another-message'),
            OlivOS.messageAPI.PARA.at(str(bot.id)),
            OlivOS.messageAPI.PARA.text(' .auth help'),
        ],
    )
    main.Event.group_message(event, proc)
    assert len(sent) == 1
    assert sent[0]['msg_id'] == 'original-message'
    assert sent[0]['message_reference'] == {'message_id': 'REFIDX_original'}
    assert sent[0]['content'].startswith('获取主动授权')
    assert '[OP:reply' not in sent[0]['content'] and '[CQ:reply' not in sent[0]['content']


@pytest.mark.parametrize('user_id', ['recipient-a', 'recipient-b', '', 'all'])
def test_command_replies_never_prepend_sender_or_everyone_at(context, monkeypatch, user_id):
    bot, _, sent = context
    event = group_event(bot)
    event.data.user_id = user_id

    def capture(api, *args, **kwargs):
        sent.append(copy.deepcopy(api.data.__dict__))
        api.res, api.res_code = '{"id":"sent"}', 200

    monkeypatch.setattr(SDK.API.sendQQMessage, 'do_api', capture)
    bridge = transport.GroupReply(event, 'current-group', 'original-message')
    assert bridge.text('操作完成')
    assert bridge.image(b'image')
    assert sent[0]['content'] == '操作完成'
    assert sent[1]['content'] == ''
    assert all(item['message_reference'] == {'message_id': 'REFIDX_original'} for item in sent)
    assert all(item['msg_id'] == 'original-message' for item in sent)
    assert not any('<qqbot-at-' in item['content'] for item in sent)


def test_manual_page_omits_automatic_authorization(tmp_path):
    profile = resources.BotProfile('bot', '橘波特', '23001', tmp_path)
    document = renderer.page_html(profile)
    assert '找到群里的机器人' in document
    assert '打开机器人设置' in document
    assert '修改两项设置' in document
    assert '群主点此授权' not in document
    assert '通过授权按钮' not in document
    assert '同意授权' not in document
    assert '--mark: #ff2238' in document
    assert '手机 QQ 9.2.90 及以上' in document
    assert '<strong>仅限手机 QQ 9.2.90 及以上</strong>' in document
    assert '<span class="device-note">电脑端目前不可用</span>' in document
    assert '<span class="update-note">低于该版本，请群主先更新 QQ</span>' in document
    assert 'data:image/png;base64,' in document
    assert '添加到群聊' in document and '机器人管理' in document
    assert '聊天信息' in document and '群机器人' in document
    assert document.count('class="robot-card robot-target"') == 1
    assert '其他机器人' not in document
    assert '如果群成员列表不好找，也可以从群机器人页面进入。' in document
    assert '群主点击「群机器人」' in document
    assert 'class="robot-scopes"' not in document


def test_old_webp_cache_is_not_reused(monkeypatch, tmp_path):
    profile = resources.BotProfile('bot', '橘波特', '23001', tmp_path)
    old = tmp_path / 'authorization.webp'
    old.write_bytes(b'old cached resource')
    draw = Mock(return_value=png())
    monkeypatch.setattr(renderer, 'render_png', draw)
    result = renderer.guide_image(profile)
    assert result.path == tmp_path / 'auth_bot.png'
    assert result.data.startswith(renderer.PNG_SIGNATURE)
    assert draw.call_count == 1
    assert old.read_bytes() == b'old cached resource'


def test_passive_limit_never_retries_actively(context, monkeypatch):
    bot, proc, sent = context
    monkeypatch.setattr(common, 'get_msgid', lambda *args, **kwargs: None)
    retry = Mock(side_effect=AssertionError('Active fallback is forbidden'))
    monkeypatch.setattr(SDK.event_action, '_retry_qq_message_as_active', retry)
    main.Event.group_message(group_event(bot), proc)
    assert sent == []
    retry.assert_not_called()


def image_bytes(color='#c05040'):
    output = BytesIO()
    Image.new('RGB', (64, 64), color).save(output, format='PNG')
    return output.getvalue()


def avatar_response(data):
    response = Mock()
    response.status_code = 200
    response.headers = {'Content-Length': str(len(data))}
    response.iter_content.return_value = [data]
    response.__enter__ = Mock(return_value=response)
    response.__exit__ = Mock(return_value=False)
    return response


def test_qq_avatar_precedes_local_and_appid_comes_from_proc(context, monkeypatch):
    bot, proc, _ = context
    shared = resources.prepare_resources()
    Image.new('RGB', (64, 64), '#4060c0').save(shared / 'avatar.png')
    registered = copy.copy(bot)
    registered.id = 98765
    proc.Proc_data['bot_info_dict'][bot.hash] = registered
    download = Mock(return_value=avatar_response(image_bytes()))
    monkeypatch.setattr(resources.requests, 'get', download)
    event = group_event(bot)
    event.data.extend['sub_self_open_id'] = 'BOT_OPENID'
    profile = resources.bot_profile(event, proc)
    assert profile.appid == '98765'
    assert profile.openid == 'BOT_OPENID'
    assert profile.folder == shared
    download.assert_called_once_with(
        'https://q.qlogo.cn/qqapp/98765/BOT_OPENID/0',
        timeout=(3, 5),
        stream=True,
        allow_redirects=False,
    )
    with Image.open(BytesIO(profile.avatar)) as image:
        assert image.getpixel((0, 0))[:3] == (192, 80, 64)
    assert profile.color not in resources.PALETTE
    assert (shared / (bot.hash + '.png')).read_bytes() == profile.avatar
    assert not (shared / bot.hash).exists()
    assert not (shared / 'unity').exists()
    with Image.open(shared / 'avatar.png') as local:
        assert local.getpixel((0, 0)) == (64, 96, 192)


def test_missing_openid_uses_shared_local_avatar_without_http(context, monkeypatch):
    bot, proc, _ = context
    shared = resources.prepare_resources()
    options = config.load()
    options['bots'][bot.hash] = {'name': '共用名字', 'auto_join': False}
    config.save(options)
    Image.new('RGB', (64, 64), '#4060c0').save(shared / 'AVATAR.JPG')
    event = group_event(bot)
    monkeypatch.setattr(event, 'get_login_info', Mock(return_value={'active': False}))
    event.data.extend.pop('sub_self_open_id', None)
    profile = resources.bot_profile(event, proc)
    assert profile.name == '共用名字'
    assert profile.avatar
    assert not profile.openid
    resources.requests.get.assert_not_called()


def test_one_config_drives_profile_and_switch_and_keeps_browser_options(context):
    bot, proc, _ = context
    value = config.load()
    value.update(browser_path='/custom/browser/chrome', masters=['member'])
    config.save(value)
    config.set_auto_join(bot.hash, True)
    profile = resources.bot_profile(group_event(bot), proc)
    assert profile.name == '橘波特'
    assert profile.browser_path == '/custom/browser/chrome'
    assert config.auto_join_enabled(bot.hash)
    saved = json.loads((config.ROOT / 'config.json').read_text(encoding='utf-8'))
    assert saved['bots'][bot.hash]['name'] == profile.name
    assert saved['browser_path'] == value['browser_path']
    assert saved['masters'] == ['member']
    assert not (config.ROOT / 'settings.json').exists()


def test_separate_settings_file_is_never_read_or_migrated(context):
    bot, proc, _ = context
    resources.prepare_resources()
    old = config.ROOT / 'settings.json'
    old.write_text('{"bot_name":"旧显示名","browser_path":"/old/browser"}', encoding='utf-8')
    previous = old.read_bytes()
    profile = resources.bot_profile(group_event(bot), proc)
    assert profile.name == '橘波特' and profile.browser_path == ''
    assert old.read_bytes() == previous
    assert config.load()['bots'][bot.hash]['name'] == '橘波特'
    assert 'bot_name' not in config.load() and config.load()['browser_path'] == ''


@pytest.mark.parametrize('field', ['name', 'browser_path'])
def test_invalid_display_options_fail_closed_and_leave_config_intact(context, field):
    bot, proc, sent = context
    value = config.load()
    if field == 'name':
        value['bots'][bot.hash] = {'name': ['invalid string field'], 'auto_join': False}
    else:
        value[field] = ['invalid string field']
    config.save(value)
    previous = (config.ROOT / 'config.json').read_bytes()
    event = group_event(bot)
    with pytest.raises(config.ConfigError, match='必须为字符串'):
        resources.bot_profile(event, proc)
    main.Event.group_message(event, proc)
    assert [message['msg_type'] for message in sent] == [0]
    assert (config.ROOT / 'config.json').read_bytes() == previous


def test_name_fetch_updates_per_hash_then_falls_back_to_saved_name(context, monkeypatch):
    bot, proc, _ = context
    value = config.load()
    value['bots'][bot.hash] = {'name': '原兜底', 'auto_join': True}
    value['bots']['other-bot'] = {'name': '别的机器人', 'auto_join': False}
    config.save(value)
    event = group_event(bot)
    monkeypatch.setattr(event, 'get_login_info', Mock(return_value={'active': True, 'data': {'name': '实时名字'}}))
    first = resources.bot_profile(event, proc)
    assert first.name == '实时名字'
    assert config.load()['bots'][bot.hash] == {'name': '实时名字', 'auto_join': True}
    assert config.load()['bots']['other-bot']['name'] == '别的机器人'
    monkeypatch.setattr(event, 'get_login_info', Mock(side_effect=OSError))
    assert resources.bot_profile(event, proc).name == '实时名字'


def test_distinct_bot_names_remain_isolated_in_the_unified_config(context, monkeypatch):
    bot, proc, _ = context
    first = group_event(bot)
    another = copy.copy(bot)
    another.hash = 'another-bot'
    another.id = 33001
    proc.Proc_data['bot_info_dict'][another.hash] = another
    second = copy.copy(first)
    second.bot_info = another
    monkeypatch.setattr(first, 'get_login_info', Mock(return_value={'active': True, 'data': {'name': '甲机器人'}}))
    monkeypatch.setattr(second, 'get_login_info', Mock(return_value={'active': True, 'data': {'name': '乙机器人'}}))
    resources.bot_profile(first, proc)
    resources.bot_profile(second, proc)
    monkeypatch.setattr(first, 'get_login_info', Mock(return_value={'active': False}))
    monkeypatch.setattr(second, 'get_login_info', Mock(return_value={'active': False}))
    assert resources.bot_profile(first, proc).name == '甲机器人'
    assert resources.bot_profile(second, proc).name == '乙机器人'
    assert config.load()['bots'][bot.hash]['name'] == '甲机器人'
    assert config.load()['bots'][another.hash]['name'] == '乙机器人'


def test_name_missing_without_saved_value_uses_appid_without_caching_fake_name(context, monkeypatch):
    bot, proc, _ = context
    event = group_event(bot)
    monkeypatch.setattr(event, 'get_login_info', Mock(return_value={'active': False}))
    profile = resources.bot_profile(event, proc)
    assert profile.name == 'QQ 机器人 23001'
    assert bot.hash not in config.load()['bots']


def test_core_current_bot_name_is_persisted_before_qq_name(context, monkeypatch):
    bot, proc, _ = context
    core = SimpleNamespace(msgCustom=SimpleNamespace(dictStrCustomDict={bot.hash: {'strBotName': 'Core 骰娘'}}))
    monkeypatch.setitem(sys.modules, 'OlivaDiceCore', core)
    event = group_event(bot)
    login = Mock(side_effect=AssertionError('Core already provided the name'))
    monkeypatch.setattr(event, 'get_login_info', login)
    assert resources.bot_profile(event, proc).name == 'Core 骰娘'
    assert config.load()['bots'][bot.hash]['name'] == 'Core 骰娘'
    login.assert_not_called()


def test_downloaded_avatar_has_two_disk_fallback_layers_without_overwriting_user(context, monkeypatch):
    bot, proc, _ = context
    folder = resources.prepare_resources()
    user_avatar = folder / 'avatar.png'
    user_avatar.write_bytes(image_bytes('#4060c0'))
    previous = user_avatar.read_bytes()
    download = Mock(return_value=avatar_response(image_bytes('#c05040')))
    monkeypatch.setattr(resources.requests, 'get', download)
    event = group_event(bot)
    online = resources.bot_profile(event, proc)
    bot_avatar = folder / (bot.hash + '.png')
    assert bot_avatar.read_bytes() == online.avatar
    assert user_avatar.read_bytes() == previous
    resources._avatar_cache.clear()
    download.side_effect = resources.requests.Timeout
    cached = resources.bot_profile(event, proc)
    assert cached.avatar == online.avatar
    assert user_avatar.read_bytes() == previous
    # 损坏的 bot 缓存继续回退到用户提供的共用 avatar。
    bot_avatar.write_bytes(b'broken cached avatar')
    user_fallback = resources.bot_profile(event, proc)
    assert user_fallback.avatar == resources.normalize_avatar(previous)
    user_avatar.write_bytes(b'broken user avatar')
    assert not resources.bot_profile(event, proc).avatar


def test_bot_avatar_cache_never_reads_another_bot_file(context, monkeypatch):
    bot, proc, _ = context
    folder = resources.prepare_resources()
    (folder / 'other-bot.png').write_bytes(image_bytes())
    event = group_event(bot)
    event.data.extend.pop('sub_self_open_id', None)
    assert not resources.bot_profile(event, proc).avatar
    resources.requests.get.assert_not_called()
    assert (folder / resources.avatar_basename('../outside')).parent == folder


@pytest.mark.parametrize(
    'suffix,format_name',
    [
        ('.png', 'PNG'),
        ('.JPG', 'JPEG'),
        ('.jpeg', 'JPEG'),
        ('.WEBP', 'WEBP'),
        ('.gif', 'GIF'),
        ('.BMP', 'BMP'),
    ],
)
def test_bot_hash_and_user_avatar_support_same_extensions(context, suffix, format_name):
    bot, proc, _ = context
    folder = resources.prepare_resources()
    image = BytesIO()
    Image.new('RGB', (32, 32), '#c05040').save(image, format=format_name)
    cache = folder / (bot.hash + suffix)
    cache.write_bytes(image.getvalue())
    event = group_event(bot)
    event.data.extend.pop('sub_self_open_id', None)
    profile = resources.bot_profile(event, proc)
    assert profile.avatar == resources.normalize_avatar(image.getvalue())
    cache.write_bytes(b'broken bot cache')
    (folder / ('avatar' + suffix)).write_bytes(image.getvalue())
    assert resources.bot_profile(event, proc).avatar == profile.avatar
    assert not (folder / bot.hash).exists()
    resources.requests.get.assert_not_called()


def test_name_and_avatar_write_failures_keep_fetched_profile_in_memory(context, monkeypatch):
    bot, proc, _ = context
    folder = resources.prepare_resources()
    value = config.load()
    value['bots'][bot.hash] = {'name': '旧兜底', 'auto_join': True}
    config.save(value)
    previous = (folder / 'config.json').read_bytes()
    user_avatar = folder / 'avatar.png'
    user_avatar.write_bytes(image_bytes('#4060c0'))
    old_avatar = user_avatar.read_bytes()
    event = group_event(bot)
    monkeypatch.setattr(
        event, 'get_login_info', Mock(return_value={'active': True, 'data': {'name': '获取到的新名字'}})
    )
    monkeypatch.setattr(resources.requests, 'get', Mock(return_value=avatar_response(image_bytes())))
    monkeypatch.setattr(config.Path, 'replace', Mock(side_effect=OSError))
    profile = resources.bot_profile(event, proc)
    assert profile.name == '获取到的新名字' and profile.avatar
    assert (folder / 'config.json').read_bytes() == previous
    assert user_avatar.read_bytes() == old_avatar


def test_fetched_name_and_avatar_unchanged_do_not_rewrite_disk(context, monkeypatch):
    bot, proc, _ = context
    event = group_event(bot)
    monkeypatch.setattr(resources.requests, 'get', Mock(return_value=avatar_response(image_bytes())))
    resources.bot_profile(event, proc)
    save = Mock(wraps=config.save)
    monkeypatch.setattr(config, 'save', save)
    replace = Mock(side_effect=AssertionError('Unchanged avatar should not be rewritten'))
    monkeypatch.setattr(resources.Path, 'replace', replace)
    resources.bot_profile(event, proc)
    save.assert_not_called()
    replace.assert_not_called()


@pytest.mark.parametrize(
    'failure', ['timeout', 'invalid_image', 'too_large', 'oversized_stream', 'http_error', 'redirect']
)
def test_remote_avatar_failures_use_local(context, monkeypatch, failure):
    bot, proc, _ = context
    shared = resources.prepare_resources()
    Image.new('RGB', (64, 64), '#4060c0').save(shared / 'avatar.png')
    response = avatar_response(image_bytes())
    download = Mock(return_value=response)
    if failure == 'timeout':
        download.side_effect = resources.requests.Timeout
    elif failure == 'invalid_image':
        response.iter_content.return_value = [b'HTML error page']
    elif failure == 'too_large':
        response.headers['Content-Length'] = str(resources.MAX_AVATAR_BYTES + 1)
    elif failure == 'oversized_stream':
        response.headers = {}
        response.iter_content.return_value = [b'x' * (resources.MAX_AVATAR_BYTES + 1)]
    elif failure == 'http_error':
        response.raise_for_status.side_effect = resources.requests.HTTPError
    else:
        response.status_code = 302
    monkeypatch.setattr(resources.requests, 'get', download)
    event = group_event(bot)
    profile = resources.bot_profile(event, proc)
    with Image.open(BytesIO(profile.avatar)) as image:
        assert image.getpixel((0, 0))[:3] == (64, 96, 192)
    # 重复命令在失败冷却期内直接使用本地头像。
    resources.bot_profile(event, proc)
    assert download.call_count == 1


def test_remote_avatar_memory_cache_is_keyed_by_proc_appid_and_openid(context, monkeypatch):
    bot, proc, _ = context
    download = Mock(return_value=avatar_response(image_bytes()))
    monkeypatch.setattr(resources.requests, 'get', download)
    event = group_event(bot)
    resources.bot_profile(event, proc)
    resources.bot_profile(event, proc)
    assert download.call_count == 1
    event.data.extend['sub_self_open_id'] = 'another-openid'
    resources.bot_profile(event, proc)
    assert download.call_count == 2
    registered = copy.copy(bot)
    registered.id = 98765
    proc.Proc_data['bot_info_dict'][bot.hash] = registered
    resources.bot_profile(event, proc)
    assert download.call_count == 3


def test_online_avatar_cache_expires(context, monkeypatch):
    bot, proc, _ = context
    now = [100.0]
    monkeypatch.setattr(resources.time, 'monotonic', lambda: now[0])
    download = Mock(return_value=avatar_response(image_bytes()))
    monkeypatch.setattr(resources.requests, 'get', download)
    event = group_event(bot)
    resources.bot_profile(event, proc)
    now[0] += 3601
    resources.bot_profile(event, proc)
    assert download.call_count == 2


def test_proc_missing_bot_never_uses_event_appid(context):
    bot, proc, _ = context
    proc.Proc_data['bot_info_dict'] = {}
    with pytest.raises(ValueError, match='Bot not registered'):
        resources.bot_profile(group_event(bot), proc)


def test_broken_avatar_uses_initial_and_persistent_random_theme(context):
    bot, proc, _ = context
    folder = resources.prepare_resources()
    (folder / 'avatar.png').write_bytes(b'not an image')
    event = group_event(bot)
    first = resources.bot_profile(event, proc)
    second = resources.bot_profile(event, proc)
    assert not first.avatar
    assert first.color == second.color
    assert first.color in resources.PALETTE
    assert 'placeholder' in renderer.page_html(first)


def png():
    stream = BytesIO()
    Image.new('RGB', renderer.IMAGE_SIZE, '#ffffff').save(stream, format='PNG')
    return stream.getvalue()


def test_each_bot_keeps_its_own_authorization_image(monkeypatch, tmp_path):
    draw = Mock(return_value=png())
    monkeypatch.setattr(renderer, 'render_png', draw)
    first = resources.BotProfile('bot1', '橘波特', '23001', tmp_path)
    second = resources.BotProfile('bot2', '青苹果', '23002', tmp_path)
    left = renderer.guide_image(first)
    right = renderer.guide_image(second)
    assert left.path == tmp_path / 'auth_bot1.png'
    assert right.path == tmp_path / 'auth_bot2.png'
    assert left.path.read_bytes() and right.path.read_bytes()
    assert draw.call_count == 2
    assert renderer.guide_image(first).cached
    assert renderer.guide_image(second).cached
    assert draw.call_count == 2
    first.name = '新名字'
    assert not renderer.guide_image(first).cached
    assert renderer.guide_image(second).cached
    assert draw.call_count == 3
    assert (tmp_path / 'authorization.png').exists() is False


def test_plugin_upgrade_regenerates_each_bot_image(monkeypatch, tmp_path):
    draw = Mock(return_value=png())
    monkeypatch.setattr(renderer, 'render_png', draw)
    first = resources.BotProfile('bot1', '橘波特', '23001', tmp_path)
    second = resources.BotProfile('bot2', '青苹果', '23002', tmp_path)
    renderer.guide_image(first)
    renderer.guide_image(second)
    assert draw.call_count == 2
    monkeypatch.setattr(config, 'PLUGIN_SVN', config.PLUGIN_SVN + 1)
    assert not renderer.guide_image(first).cached
    assert not renderer.guide_image(second).cached
    assert draw.call_count == 4
    assert renderer.guide_image(first).cached
    assert renderer.guide_image(second).cached
    assert draw.call_count == 4


def test_unsafe_bot_hash_authorization_filename_is_sanitized(monkeypatch, tmp_path):
    draw = Mock(return_value=png())
    monkeypatch.setattr(renderer, 'render_png', draw)
    profile = resources.BotProfile('../outside', '橘波特', '23001', tmp_path)
    result = renderer.guide_image(profile)
    stem = 'auth_' + resources.avatar_basename('../outside')
    assert result.path == tmp_path / (stem + '.png')
    assert result.path.is_file()
    assert '..' not in result.path.name


def test_single_image_cache_reused_and_bot_changes_rebuild(monkeypatch, tmp_path):
    profile = resources.BotProfile('bot1', '橘波特', '23001', tmp_path)
    draw = Mock(return_value=png())
    monkeypatch.setattr(renderer, 'render_png', draw)
    first = renderer.guide_image(profile)
    second = renderer.guide_image(profile)
    assert first.path.is_file() and second.cached
    assert draw.call_count == 1
    first.path.write_bytes(b'broken')
    assert renderer.guide_image(profile).data
    assert draw.call_count == 2
    profile.appid = 'another-bot'
    third = renderer.guide_image(profile)
    assert third.path == first.path == tmp_path / 'auth_bot1.png'
    assert draw.call_count == 3
    assert len(list(tmp_path.glob('auth_*.png'))) == 1
    assert renderer.guide_image(profile).cached
    profile.appid = '23001'
    assert not renderer.guide_image(profile).cached
    assert draw.call_count == 4


def test_single_cache_wrong_image_or_metadata_never_reused(monkeypatch, tmp_path):
    profile = resources.BotProfile('bot', '橘波特', '23001', tmp_path)
    draw = Mock(return_value=png())
    monkeypatch.setattr(renderer, 'render_png', draw)
    result = renderer.guide_image(profile)
    other = BytesIO()
    Image.new('RGB', renderer.IMAGE_SIZE, '#ff0000').save(other, format='PNG')
    result.path.write_bytes(other.getvalue())
    assert not renderer.guide_image(profile).cached
    assert draw.call_count == 2
    (tmp_path / 'auth_bot.cache.json').write_text('broken JSON', encoding='utf-8')
    assert not renderer.guide_image(profile).cached
    assert draw.call_count == 3


def test_cache_write_failure_retains_generated_image(monkeypatch, tmp_path):
    blocked = tmp_path / 'blocked'
    blocked.write_bytes(b'file instead of directory')
    profile = resources.BotProfile('bot', '橘波特', '23001', blocked)
    monkeypatch.setattr(renderer, 'render_png', Mock(return_value=png()))
    result = renderer.guide_image(profile)
    assert result.data and result.path is None
    assert '缓存写入失败' in result.warning


@pytest.mark.parametrize('stored_svn', [None, 0, 1])
def test_newer_plugin_forces_regeneration_even_with_valid_image_cache(monkeypatch, tmp_path, stored_svn):
    profile = resources.BotProfile('bot', '橘波特', '23001', tmp_path)
    draw = Mock(return_value=png())
    monkeypatch.setattr(renderer, 'render_png', draw)
    config.save(
        {'svn': config.PLUGIN_SVN, 'masters': ['owner'], 'bots': {'bot': {'name': '橘波特', 'auto_join': True}}}
    )
    renderer.guide_image(profile)
    assert renderer.guide_image(profile).cached
    value = config.load()
    if stored_svn is None:
        value.pop('svn')
    else:
        value['svn'] = stored_svn
    config.save(value)
    result = renderer.guide_image(profile)
    assert not result.cached and result.data
    assert draw.call_count == 2
    saved = json.loads((config.ROOT / 'config.json').read_text(encoding='utf-8'))
    assert saved['svn'] == config.PLUGIN_SVN
    assert saved['masters'] == ['owner'] and saved['bots']['bot']['auto_join']
    assert renderer.guide_image(profile).cached and draw.call_count == 2


def test_manifest_svn_increase_rebuilds_and_same_or_lower_version_reuses(monkeypatch, tmp_path):
    profile = resources.BotProfile('bot', '橘波特', '23001', tmp_path)
    draw = Mock(return_value=png())
    monkeypatch.setattr(renderer, 'render_png', draw)
    initial_svn = config.PLUGIN_SVN
    renderer.guide_image(profile)
    assert config.load()['svn'] == initial_svn
    monkeypatch.setattr(config, 'PLUGIN_SVN', initial_svn + 1)
    assert not renderer.guide_image(profile).cached
    assert config.load()['svn'] == initial_svn + 1 and draw.call_count == 2
    assert renderer.guide_image(profile).cached
    monkeypatch.setattr(config, 'PLUGIN_SVN', initial_svn)
    assert renderer.guide_image(profile).cached
    assert config.load()['svn'] == initial_svn + 1 and draw.call_count == 2


def test_upgrade_render_failure_keeps_old_svn_and_retries(monkeypatch, tmp_path):
    profile = resources.BotProfile('bot', '橘波特', '23001', tmp_path)
    config.save({'svn': config.PLUGIN_SVN - 1, 'masters': ['owner'], 'bots': {}})
    previous = (config.ROOT / 'config.json').read_bytes()
    draw = Mock(side_effect=RuntimeError('Screenshot unavailable'))
    monkeypatch.setattr(renderer, 'render_png', draw)
    assert not renderer.guide_image(profile).data
    assert (config.ROOT / 'config.json').read_bytes() == previous
    draw.side_effect = None
    draw.return_value = png()
    assert renderer.guide_image(profile).data
    assert config.load()['svn'] == config.PLUGIN_SVN and draw.call_count == 2


def test_upgrade_cache_write_failure_keeps_svn(monkeypatch, tmp_path):
    config.save({'svn': 0, 'masters': [], 'bots': {}})
    blocked = tmp_path / 'blocked'
    blocked.write_bytes(b'file rather than directory')
    profile = resources.BotProfile('bot', '橘波特', '23001', blocked)
    monkeypatch.setattr(renderer, 'render_png', Mock(return_value=png()))
    result = renderer.guide_image(profile)
    assert result.data and result.path is None
    assert config.load()['svn'] == 0


def test_upgrade_svn_write_failure_returns_image_and_regenerates_next_time(monkeypatch, tmp_path):
    profile = resources.BotProfile('bot', '橘波特', '23001', tmp_path)
    config.save({'svn': 0, 'masters': ['owner'], 'bots': {}})
    draw = Mock(return_value=png())
    monkeypatch.setattr(renderer, 'render_png', draw)
    real_save = config.save
    monkeypatch.setattr(config, 'save', Mock(side_effect=config.ConfigError('Disk unavailable')))
    result = renderer.guide_image(profile)
    assert result.data and result.path.is_file() and 'svn 写入失败' in result.warning
    assert config.load()['svn'] == 0
    monkeypatch.setattr(config, 'save', real_save)
    assert not renderer.guide_image(profile).cached
    assert config.load()['svn'] == config.PLUGIN_SVN and draw.call_count == 2


@pytest.mark.parametrize('invalid_svn', [-1, True, '10', None])
def test_invalid_saved_svn_fails_without_overwriting_config(invalid_svn):
    config.save({'svn': invalid_svn, 'masters': [], 'bots': {}})
    previous = (config.ROOT / 'config.json').read_bytes()
    with pytest.raises(config.ConfigError, match='svn 必须为非负整数'):
        config.load()
    assert (config.ROOT / 'config.json').read_bytes() == previous


def test_escaping_and_platform_fonts(tmp_path):
    profile = resources.BotProfile('bot', '<script>{{APPID}}</script>', '23001', tmp_path)
    document = renderer.page_html(profile)
    assert '<script>' not in document
    assert '&lt;script&gt;{{APPID}}&lt;/script&gt;' in document
    assert 'Microsoft YaHei' in renderer.font_stack('win32')
    assert 'PingFang SC' in renderer.font_stack('darwin')
    assert 'Noto Sans CJK SC' in renderer.font_stack('linux')


@pytest.mark.parametrize('platform', ['win32', 'darwin', 'linux'])
def test_browser_discovery_on_each_platform(monkeypatch, tmp_path, platform):
    monkeypatch.setattr(renderer.sys, 'platform', platform)
    monkeypatch.setattr(renderer.shutil, 'which', lambda name: None)
    if platform == 'win32':
        monkeypatch.setenv('PROGRAMFILES', str(tmp_path))
        binary = tmp_path / 'Microsoft/Edge/Application/msedge.exe'
    elif platform == 'darwin':
        monkeypatch.setattr(Path, 'home', lambda: tmp_path)
        binary = tmp_path / 'Applications/Chromium.app/Contents/MacOS/Chromium'
    else:
        binary = tmp_path / 'bin/chromium'
        monkeypatch.setattr(renderer.shutil, 'which', lambda name: str(binary) if name == 'chromium' else None)
    binary.parent.mkdir(parents=True)
    binary.write_bytes(b'local browser placeholder')
    assert renderer.find_browser() == str(binary.resolve())


def test_missing_browser_returns_text_fallback(monkeypatch, tmp_path):
    profile = resources.BotProfile('bot', '橘波特', '23001', tmp_path)
    monkeypatch.setattr(renderer, 'find_browser', Mock(side_effect=FileNotFoundError))
    result = renderer.guide_image(profile)
    assert not result.data and '文字指引' in result.warning


def test_gray_avatar_keeps_gray_theme():
    stream = BytesIO()
    Image.new('RGB', (64, 64), '#888888').save(stream, format='PNG')
    color = resources.theme_color(stream.getvalue(), '#2864b4')
    assert color[1:3] == color[3:5] == color[5:7]


def test_html_retained_after_opk_asset_is_deleted(tmp_path, monkeypatch):
    source = Path(renderer.__file__)
    copied = tmp_path / 'renderer.py'
    copied.write_text(source.read_text(encoding='utf-8'), encoding='utf-8')
    template = tmp_path / 'authorization.html'
    template.write_text(renderer.TEMPLATE, encoding='utf-8')
    spec = importlib.util.spec_from_file_location('QQGroupAuthorize.loaded_from_opk', copied)
    loaded = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, spec.name, loaded)
    spec.loader.exec_module(loaded)
    template.unlink()
    profile = resources.BotProfile('bot', '加载后仍可渲染', '23001', tmp_path)
    assert '加载后仍可渲染' in loaded.page_html(profile)


def test_manifest_encoding_and_platform_scope():
    data = (Path(main.__file__).parent / 'app.json').read_bytes()
    assert not data.startswith(b'\xef\xbb\xbf')
    manifest = json.loads(data.decode('utf-8'))
    assert manifest['namespace'] == 'QQGroupAuthorize'
    assert config.PLUGIN_SVN == manifest['svn']
    assert manifest['support'] == [{'sdk': 'qqGuildv2_link', 'platform': 'qqGuild', 'model': 'all'}]

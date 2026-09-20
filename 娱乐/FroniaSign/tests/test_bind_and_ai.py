# -*- coding: utf-8 -*-
'''FroniaSign 改动验证：.qdbind/.qdunbind 与「AI 人设改读 OlivaAIAgent」。'''
import importlib.util
import json
import os
import shutil
import sys
import tempfile
import types

# 本文件位于 娱乐/FroniaSign/tests/，据此定位插件目录（可直接脱离仓库路径运行）
FRONIA = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO = os.path.dirname(os.path.dirname(FRONIA))

WORK = tempfile.mkdtemp(prefix='fronia_test_')
os.chdir(WORK)
sys.path.insert(0, FRONIA)

REPLIES = []
FAILED = []


def check(name, cond, detail=''):
    print('%s %s%s' % ('PASS' if cond else 'FAIL', name, ('  | ' + detail) if detail else ''))
    if not cond:
        FAILED.append(name)


# ---------------- OlivOS / OlivaDiceCore stubs ----------------
class _Para:
    def __init__(self, data):
        self.data = data

    def CQ(self):
        return '[CQ:at,qq=%s]' % self.data.get('id')


olivos = types.ModuleType('OlivOS')
msgapi = types.ModuleType('OlivOS.messageAPI')
msgapi.PARA = types.SimpleNamespace(at=lambda i: _Para({'id': i}))


class _Templet:
    def __init__(self, mode, data):
        self.data = []


msgapi.Message_templet = _Templet
olivos.messageAPI = msgapi
sys.modules['OlivOS'] = olivos
sys.modules['OlivOS.messageAPI'] = msgapi

dice = types.ModuleType('OlivaDiceCore')


class _UserConfig:
    @staticmethod
    def setMsgCount():
        return None

    @staticmethod
    def getUserHash(userId=None, userType='user', platform=None, **kw):
        # 平台感知：与真实 OlivOS 一致（md5 里含 platform），
        # 这样「绑定时用错平台」才能被测出来。OneBot 平台保持 'H<id>' 以免动到既有断言。
        if platform in (None, 'qq'):
            return 'H%s' % userId
        return 'H%s@%s' % (userId, platform)

    @staticmethod
    def getUserConfigByKey(**kw):
        return True


class _Console:
    @staticmethod
    def getMasterBotHash(bh):
        return None

    @staticmethod
    def getConsoleSwitchByHash(key, bh):
        if key == 'differentJrrpMode':
            return 0
        if key == 'masterList':
            return []
        return None


class _Invite:
    @staticmethod
    def isInMasterList(bh, uh):
        return False


class _PcCard:
    @staticmethod
    def getPcHash(*a, **k):
        return None

    @staticmethod
    def pcCardDataGetSelectionKey(*a, **k):
        return None


class _MsgCustomManager:
    @staticmethod
    def dictTValueInit(ev, d):
        return d

    @staticmethod
    def formatReplySTR(template, tv):
        s = str(template)
        for k, v in (tv or {}).items():
            s = s.replace('{%s}' % k, str(v))
        return s


class _MsgCustom:
    dictTValue = {}
    dictGValue = {}
    dictStrCustomDict = {}


def _isMatchWordStart(text, words, isCommand=False):
    if isinstance(words, str):
        words = [words]
    t = str(text)
    for w in words:
        if t.startswith(w):
            return True
    return False


def _getMatchWordStartRight(text, words):
    if isinstance(words, str):
        words = [words]
    t = str(text)
    best = ''
    for w in words:
        if t.startswith(w) and len(w) > len(best):
            best = w
    return t[len(best):] if best else t


def _replyMsg(ev, text):
    REPLIES.append(str(text))


def _msgIsCommand(text, prefixes):
    t = str(text)
    for p in prefixes:
        if t.startswith(p):
            return t[len(p):], True
    return t, False


dice.userConfig = _UserConfig
dice.console = _Console
dice.ordinaryInviteManager = _Invite
dice.pcCard = _PcCard
dice.msgCustomManager = _MsgCustomManager
dice.msgCustom = _MsgCustom
dice.crossHook = types.SimpleNamespace(dictHookList={'prefix': ['.', '。', '/']})
dice.msgReply = types.SimpleNamespace(
    replyMsg=_replyMsg,
    isMatchWordStart=_isMatchWordStart,
    getMatchWordStartRight=_getMatchWordStartRight,
    skipSpaceStart=lambda s: str(s).lstrip(' '),
    skipToRight=lambda s, ch: str(s).split(ch, 1)[1] if ch in str(s) else str(s),
    msgIsCommand=_msgIsCommand,
)
sys.modules['OlivaDiceCore'] = dice

fronia_pkg = types.ModuleType('FroniaSign')
sys.modules['FroniaSign'] = fronia_pkg

spec = importlib.util.spec_from_file_location('FroniaSign.msgCustom', os.path.join(FRONIA, 'msgCustom.py'))
mc = importlib.util.module_from_spec(spec)
sys.modules['FroniaSign.msgCustom'] = mc
spec.loader.exec_module(mc)
fronia_pkg.msgCustom = mc

dice.msgCustom.dictStrCustomDict['BOT1'] = dict(mc.dictStrCustom)


def load_msgreply(tag):
    spec = importlib.util.spec_from_file_location('FroniaSign.msgReply_' + tag, os.path.join(FRONIA, 'msgReply.py'))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def make_event(user_id, text, group_id='90001', platform='qq', sdk='onebot', model='all'):
    ev = types.SimpleNamespace()
    ev.bot_info = types.SimpleNamespace(hash='BOT1')
    ev.platform = {'platform': platform, 'sdk': sdk, 'model': model}
    ev.plugin_info = {'func_type': 'group_message', 'namespace': 'FroniaSign'}
    ev.base_info = {'self_id': '100000'}
    ev.data = types.SimpleNamespace(
        user_id=str(user_id),
        message=text,
        sender={'name': 'User%s' % user_id, 'role': 'member'},
        group_id=group_id,
        host_id=None,
        extend={},
    )
    ev.get_group_member_list = lambda gid: {
        'active': True,
        'data': [{'user_id': '1001'}, {'user_id': '1002'}, {'user_id': '1004'}, {'user_id': '1005'}],
    }
    ev.get_stranger_info = lambda uid: {'active': False}
    return ev


def data_dir():
    return os.path.join(WORK, 'plugin', 'data', 'FroniaSign', 'BOT1')


def user_file(uh):
    return os.path.join(data_dir(), uh, 'user.json')


def read_user(uh):
    p = user_file(uh)
    if not os.path.exists(p):
        return None
    with open(p, 'r', encoding='utf-8') as f:
        return json.load(f)


def write_user(uh, data):
    os.makedirs(os.path.dirname(user_file(uh)), exist_ok=True)
    with open(user_file(uh), 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False)


def read_binds():
    p = os.path.join(data_dir(), 'binds.json')
    if not os.path.exists(p):
        return {}
    with open(p, 'r', encoding='utf-8') as f:
        return json.load(f).get('binds', {})


def say(mod, uid, text):
    REPLIES.clear()
    mod.unity_reply(make_event(uid, text), None)
    return REPLIES[-1] if REPLIES else ''


def say_on(mod, uid, text, platform, sdk):
    REPLIES.clear()
    mod.unity_reply(make_event(uid, text, platform=platform, sdk=sdk), None)
    return REPLIES[-1] if REPLIES else ''


# ================= 阶段 A：无 OlivaAIAgent（回退路径 + 绑定） =================
print('--- 阶段 A：未安装 OlivaAIAgent ---')
mrA = load_msgreply('A')
check('未安装 OlivaAIAgent 时 has_OlivaAIAgent=False', mrA.has_OlivaAIAgent is False)
check('旧依赖已移除（模块里不再引用 ChatGPT）', not hasattr(mrA, 'has_ChatGPT'))

# A(1001) 签到
r = say(mrA, 1001, '.签到')
check('签到回复包含【签到】', '【签到】' in r, r.replace('\n', ' / ')[:90])
a1 = read_user('H1001')
check('A 用户数据已落盘', a1 is not None and a1.get('anima_coin', 0) >= 10, str(a1.get('anima_coin') if a1 else None))
a_coin_1 = a1['anima_coin']

# B(1002) 预置 100 灵币
write_user('H1002', {'anima_coin': 100, 'groups': ['90001'], 'user_ids': ['1002'], 'last_user_id': '1002', 'last_name': 'User1002'})

# 用法提示
r = say(mrA, 1001, '.qdbind')
check('.qdbind 无参给出用法', '用法' in r, r.replace('\n', ' / ')[:80])
r = say(mrA, 1001, '.qdunbind')
check('.qdunbind 无参给出用法', '用法' in r)

# 不能绑自己
r = say(mrA, 1001, '.qdbind 1001')
check('不能绑定自己', '不能把自己' in r, r.replace('\n', ' / ')[:80])

# 正常绑定 1002
r = say(mrA, 1001, '.qdbind 1002')
check('绑定成功并提示转入灵币', '已经并进你的账号' in r and '100' in r, r.replace('\n', ' / ')[:110])
a2 = read_user('H1001')
check('发起者灵币 = 原灵币 + 100', a2['anima_coin'] == a_coin_1 + 100, '%s vs %s' % (a2['anima_coin'], a_coin_1 + 100))
b2 = read_user('H1002')
check('被绑账号灵币清零', b2['anima_coin'] == 0, str(b2['anima_coin']))
check('被绑账号标记 merged_into', b2.get('merged_into') == 'H1001', str(b2.get('merged_into')))
check('绑定表写入 owner', read_binds().get('H1002', {}).get('owner') == 'H1001', json.dumps(read_binds(), ensure_ascii=False))

# 唯一性：C(1004) 试图绑 1002
r = say(mrA, 1004, '.qdbind 1002')
check('被绑过的 QQ 无法再次绑定', '已经被绑定过了' in r, r.replace('\n', ' / ')[:80])

# 被绑 QQ 自己签到 -> 记到归属账号（先模拟新的一天，清掉归属账号的签到日期）
_d = read_user('H1001')
_d.pop('last_sign_date', None)
write_user('H1001', _d)
before = read_user('H1001')['anima_coin']
r = say(mrA, 1002, '.签到')
after = read_user('H1001')['anima_coin']
check('被绑 QQ 签到记入归属账号', after > before, '%s -> %s' % (before, after))
check('被绑 QQ 自身账号仍为 0', read_user('H1002')['anima_coin'] == 0, str(read_user('H1002')['anima_coin']))
r = say(mrA, 1002, '.灵币查询')
check('被绑 QQ 查询显示归属账号灵币', str(after) in r, r.replace('\n', ' / ')[:80])
r = say(mrA, 1002, '.灵币')
check('.灵币 命令可直接查询（帮助文档写法）', str(after) in r, r.replace('\n', ' / ')[:80])
r = say(mrA, 1001, '.签到')
check('绑定后共享每日一次签到', '已经签到过了' in r, r.replace('\n', ' / ')[:80])
r = say(mrA, 1001, '.灵币排行')
check('.灵币排行 未被查询分支抢走', '本群灵币排行' in r, r.replace('\n', ' / ')[:80])

# 链式绑定：B(1002) 再绑 1003 → 仍落在 H1001
write_user('H1003', {'anima_coin': 30, 'groups': [], 'user_ids': ['1003']})
r = say(mrA, 1002, '.qdbind 1003')
binds_now = read_binds()
check('被绑账号发起绑定仍归到根账号', binds_now.get('H1003', {}).get('owner') == 'H1001', json.dumps(binds_now, ensure_ascii=False))
check('链式合并灵币正确', read_user('H1001')['anima_coin'] == after + 30, str(read_user('H1001')['anima_coin']))

# 目标名下已有绑定 → 拒绝
r = say(mrA, 1004, '.qdbind 1002')
check('目标账号名下已有绑定时拒绝', '已经被绑定过了' in r or '名下还挂着' in r, r.replace('\n', ' / ')[:80])

# 排行榜不重复出现被绑账号（此时 1002/1003 仍被绑）
r = say(mrA, 1001, '.灵币总榜')
check('总榜不重复列出被绑账号', 'User1002' not in r and 'H1002' not in r, r.replace('\n', ' / ')[:140])

# 他人无权解绑
r = say(mrA, 1004, '.qdunbind 1002')
check('非建立者无权解绑', '不是你建的' in r, r.replace('\n', ' / ')[:80])

# 建立者解绑（反向拆账：从归属账号扣回、退还给被解绑号）
owner_before = read_user('H1001')['anima_coin']
r = say(mrA, 1001, '.qdunbind 1002')
check('建立者可解绑', '已解除' in r, r.replace('\n', ' / ')[:80])
check('解绑回复提示退回灵币', '退回灵币' in r and '100' in r, r.replace('\n', ' / ')[:90])
check('绑定表已移除该条', 'H1002' not in read_binds(), json.dumps(read_binds(), ensure_ascii=False))
check('解绑后被绑号取回当初并入的灵币', read_user('H1002')['anima_coin'] == 100, str(read_user('H1002')['anima_coin']))
check('解绑后归属账号扣除等额灵币', read_user('H1001')['anima_coin'] == owner_before - 100,
      '%s -> %s' % (owner_before, read_user('H1001')['anima_coin']))
check('解绑后归属标记被清除', not read_user('H1002').get('merged_into'))

r = say(mrA, 1001, '.qdunbind 1002')
check('重复解绑提示无记录', '没有绑定记录' in r, r.replace('\n', ' / ')[:80])

# 余额不足时按实际余额退回（不产生负数）
write_user('H1010', {'anima_coin': 100, 'groups': [], 'user_ids': ['1010']})
owner_before2 = read_user('H1001')['anima_coin']
say(mrA, 1001, '.qdbind 1010')
check('并入后归属账号增加 100', read_user('H1001')['anima_coin'] == owner_before2 + 100,
      str(read_user('H1001')['anima_coin']))
_d2 = read_user('H1001')
_d2['anima_coin'] = 10  # 模拟灵币已被消耗掉大部分
write_user('H1001', _d2)
r = say(mrA, 1001, '.qdunbind 1010')
check('余额不足时按实际余额退回', read_user('H1010')['anima_coin'] == 10, str(read_user('H1010')['anima_coin']))
check('归属账号扣到 0 且不为负', read_user('H1001')['anima_coin'] == 0, str(read_user('H1001')['anima_coin']))

# 防环：让 1005 绑 1006 之后，再构造回到 1005 的绑定应被拒绝
write_user('H1005', {'anima_coin': 5, 'groups': [], 'user_ids': ['1005']})
write_user('H1006', {'anima_coin': 5, 'groups': [], 'user_ids': ['1006']})
say(mrA, 1005, '.qdbind 1006')
r = say(mrA, 1006, '.qdbind 1005')
check('不会形成绑定环', '不能把自己' in r or '已经被绑定过了' in r, r.replace('\n', ' / ')[:80])
check('防环后 root 仍是 H1005', mrA._resolve_account_hash('BOT1', 'H1006') == 'H1005', mrA._resolve_account_hash('BOT1', 'H1006'))

# ================= 阶段 A2：官方机器人（qqGuildv2）会话里绑定 =================
# 数字 QQ 号只可能来自 OneBot；qqGuildv2 的用户标识是 openid。
# 因此即使在 qqGuild 会话里发起 .qdbind，目标 hash 也必须按 OneBot（platform='qq'）计算。
print('--- 阶段 A2：qqGuildv2 会话里绑定目标 QQ ---')
OPENID = 'OPENID_ABC'
write_user('H1008', {'anima_coin': 40, 'groups': [], 'user_ids': ['1008'], 'last_name': 'User1008'})
r = say_on(mrA, OPENID, '.qdbind 1008', 'qqGuild', 'qqGuildv2_link')
_b = read_binds()
check('qqGuild 会话里绑定成功', '已经并进你的账号' in r, r.replace('\n', ' / ')[:110])
check('目标 key 用 OneBot hash（H1008）', 'H1008' in _b and 'H1008@qqGuild' not in _b,
      json.dumps(_b, ensure_ascii=False))
check('目标 owner 为 qqGuild 侧发起者',
      _b.get('H1008', {}).get('owner') == 'H%s@qqGuild' % OPENID,
      json.dumps(_b.get('H1008', {}), ensure_ascii=False))
check('被绑 OneBot 号灵币已清零', read_user('H1008')['anima_coin'] == 0, str(read_user('H1008')['anima_coin']))
check('归属账号收到 40 灵币', read_user('H%s@qqGuild' % OPENID)['anima_coin'] == 40,
      str(read_user('H%s@qqGuild' % OPENID)['anima_coin']))

# 被绑 QQ 回到 OneBot 侧签到 → 记账仍落到归属账号
_own = read_user('H%s@qqGuild' % OPENID)
_own.pop('last_sign_date', None)
write_user('H%s@qqGuild' % OPENID, _own)
_before3 = read_user('H%s@qqGuild' % OPENID)['anima_coin']
say(mrA, 1008, '.签到')
check('跨平台绑定后 OneBot 签到记入归属账号',
      read_user('H%s@qqGuild' % OPENID)['anima_coin'] > _before3,
      '%s -> %s' % (_before3, read_user('H%s@qqGuild' % OPENID)['anima_coin']))

# ================= 阶段 B：有 OlivaAIAgent（AI 路径） =================
print('--- 阶段 B：模拟已装 OlivaAIAgent ---')
CALLS = []
CALL_KW = []      # 记录每次 chat 的关键字参数，用于验证 response_json 等透传


class _FakeConf:
    PERSONA = '【测试人设】你是芙萝妮娅。'
    BACKEND = {'api_url': 'http://fake', 'api_key': 'x', 'model': 'm', 'wire': 'openai'}

    @staticmethod
    def getPersonaPrompt(group_id=None):
        return _FakeConf.PERSONA + ('\n\n【本群人设】\n群%s专属' % group_id if group_id else '')

    @staticmethod
    def getChatBackend():
        return _FakeConf.BACKEND


class _FakeAiClient:
    @staticmethod
    def chat(messages, tools=None, backend_conf=None, force_no_stream=False,
             response_json=False, thinking_off=False, timeout_override=None, trace_id=None, purpose=None):
        CALLS.append(messages)
        CALL_KW.append({
            'response_json': response_json,
            'force_no_stream': force_no_stream,
            'timeout_override': timeout_override,
            'backend_conf': backend_conf,
        })
        sys_text = messages[0]['content']
        if '只输出 JSON' in sys_text or '只包含 coins' in sys_text:
            # 单次调用：同一次请求同时给出 coins 与 text
            return {'ok': True, 'text': '{"coins": 20, "text": "早安呀，今天也要好好过~"}',
                    'tool_calls': [], 'error': ''}
        return {'ok': True, 'text': '早安呀，今天也要好好过~', 'tool_calls': [], 'error': ''}


fake_aia = types.ModuleType('OlivaAIAgent')
fake_aia.conf = _FakeConf
fake_aia.aiClient = _FakeAiClient
sys.modules['OlivaAIAgent'] = fake_aia

mrB = load_msgreply('B')
check('装有 OlivaAIAgent 时可用', mrB.has_OlivaAIAgent is True)
check('人设读取走 OlivaAIAgent.conf.getPersonaPrompt', mrB._get_ai_persona_prompt('90001').startswith('【测试人设】'), mrB._get_ai_persona_prompt('90001')[:40])
check('后端可用性判定正确', mrB._ai_backend_ready() is True)

CALLS.clear()
CALL_KW.clear()
r = say(mrB, 2001, '.签到')
check('AI 路径：签到只调用主模型一次', len(CALLS) == 1, '调用次数=%d' % len(CALLS))
check('AI 路径：system 里带上 OlivaAIAgent 人设', bool(CALLS) and CALLS[0][0]['content'].startswith('【测试人设】'), CALLS[0][0]['content'][:40] if CALLS else '')
check('AI 路径：群人设被拼入', bool(CALLS) and '群90001专属' in CALLS[0][0]['content'])
check('AI 路径：coins 取自模型 JSON', read_user('H2001')['anima_coin'] == 20, str(read_user('H2001')['anima_coin']))
check('AI 路径：短句来自同一次模型返回', '早安呀' in r, r.replace('\n', ' / ')[:90])
# 单次调用透传：要 JSON 兜底、强制非流式、不覆盖后端、超时 60s
check('单次请求 response_json=True', bool(CALL_KW) and CALL_KW[0]['response_json'] is True,
      str(CALL_KW[0]['response_json']) if CALL_KW else 'no call')
check('签到统一强制非流式', all(kw['force_no_stream'] is True for kw in CALL_KW), str(len(CALL_KW)))
check('签到不覆盖后端配置（跟随 OlivaAIAgent）', all(kw['backend_conf'] is None for kw in CALL_KW))
check('签到超时固定 60s', all(kw['timeout_override'] == 60 for kw in CALL_KW))

# 单次调用：模型只给 coins 不给 text 时，灵币仍用模型值，文案回落本地
_orig_ai = fake_aia.aiClient


class _FakeAiClientNoText:
    @staticmethod
    def chat(messages, **kw):
        return {'ok': True, 'text': '{"coins": 25}', 'tool_calls': [], 'error': ''}


fake_aia.aiClient = _FakeAiClientNoText
mrE = load_msgreply('E')
_r = say(mrE, 2005, '.签到')
check('缺 text 时灵币仍取模型值', read_user('H2005')['anima_coin'] == 25, str(read_user('H2005')['anima_coin']))
check('缺 text 时文案回落本地', '【签到】' in _r and '小芙' in _r, _r.replace('\n', ' / ')[:90])
fake_aia.aiClient = _orig_ai

# 预检短路：后端未配置 api_url/api_key 时不发请求
_saved_backend = _FakeConf.BACKEND
_FakeConf.BACKEND = None
CALLS.clear()
CALL_KW.clear()
_ok, _txt = mrB._call_ai([{'role': 'user', 'content': 'ping'}])
check('后端未配置时 _call_ai 短路且不发请求',
      _ok is False and _txt == '' and len(CALLS) == 0,
      'ok=%s calls=%d' % (_ok, len(CALLS)))
check('短路条件与 _ai_backend_ready 一致', mrB._ai_backend_ready() is False)
_FakeConf.BACKEND = _saved_backend
check('恢复后端配置后 _ai_backend_ready 恢复', mrB._ai_backend_ready() is True)

# 旧版 OlivaAIAgent（conf 没有 getChatBackend 接口）→ 不预判，仍走实际调用
class _LegacyConf:
    @staticmethod
    def getPersonaPrompt(group_id=None):
        return '【旧版人设】'


_saved_conf = fake_aia.conf
_saved_client = fake_aia.aiClient
fake_aia.conf = _LegacyConf
fake_aia.aiClient = _FakeAiClient
mrF = load_msgreply('F')
CALLS.clear()
CALL_KW.clear()
check('旧版缺 getChatBackend 时不做预判（返回 True）', mrF._ai_backend_ready() is True)
_r = say(mrF, 2006, '.签到')
check('旧版包下签到仍实际调用模型', len(CALLS) == 1, '调用次数=%d' % len(CALLS))
check('旧版包下签到仍拿到模型结果', '早安呀' in _r, _r.replace('\n', ' / ')[:90])
fake_aia.conf = _saved_conf
fake_aia.aiClient = _saved_client

CALLS.clear()
CALL_KW.clear()
r = say(mrB, 2002, '.签到 今天很困')
check('AI 路径：带补充文本仍只调用一次', len(CALLS) == 1, '调用次数=%d' % len(CALLS))
check('AI 路径：补充文本进入 user prompt', '今天很困' in CALLS[0][1]['content'])

# AI 失败 → 回退本地文案
class _FakeAiClientDown:
    @staticmethod
    def chat(messages, **kw):
        return {'ok': False, 'text': '', 'tool_calls': [], 'error': 'boom'}


fake_aia.aiClient = _FakeAiClientDown
mrC = load_msgreply('C')
r = say(mrC, 2003, '.签到')
check('AI 失败时回退本地文案', '【签到】' in r and '小芙' in r, r.replace('\n', ' / ')[:90])
check('回退时灵币仍在 10-30 区间', 10 <= read_user('H2003')['anima_coin'] <= 30, str(read_user('H2003')['anima_coin']))

print('--- 清理 ---')
shutil.rmtree(WORK, ignore_errors=True)
print('数据目录已清理: %s' % WORK)

if FAILED:
    print('\nFAILED %d: %s' % (len(FAILED), ', '.join(FAILED)))
    sys.exit(1)
print('\nALL CHECKS PASSED')

# Lanota Portal API 调研记录

> 调研日期：2026-07-30  
> 目标站点：`https://noxygames.com/lanota/portal/`  
> 性质：从当前网页前端及实际请求整理的非官方接口，后续可能随站点更新而变化。

## 1. 结论

- 网页所称的好友码在接口中叫 `nanoId`。本次目标 `W5BWeD7mgpXf` 能正常解析，绑定玩家为 `0Desom0`。
- 好友码不能匿名查询。Portal API 需要有效的 Firebase ID Token：

  ```http
  Authorization: Bearer <FIREBASE_ID_TOKEN>
  ```

- 登录后可用 `GET /api/player/{nanoId}` 查询任意有效 `nanoId` 的玩家公开资料和统计；实测好友、排行榜中的非好友都可查询。
- `GET /api/compare?friendNanoId={nanoId}` 可取得登录者与目标玩家的逐谱面成绩对比。虽然参数名是 `friendNanoId`，当前版本实测对非好友 ID 也有效。
- B30/R15、登录者全谱面分数、单曲详细成绩属于“当前登录账号”数据，不能仅靠目标好友码切换成其他玩家。
- 实测 Portal API 不依赖 Cookie、`Origin`、`Referer` 或特定 `User-Agent`；最小可用请求只有 Bearer Token。建议仍发送 `Accept: application/json`。

## 2. 认证流程

### 2.1 邮箱密码登录 Firebase

Portal 使用 Firebase Authentication。前端公开配置如下：

| 配置 | 值 |
| --- | --- |
| Firebase project | `lanota-67543202` |
| Firebase Web API key | `AIzaSyCIxTfcSRdfzdkCuUe8f0HeJrS8LHUp0Ng` |
| Auth domain | `lanota-67543202.firebaseapp.com` |
| App ID | `1:353199387726:web:984e5c6849c0114bc9ff1f` |

Firebase Web API key 是前端公开标识，不等同于用户 Token；仍不建议无关传播或滥用。

```http
POST https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key=AIzaSyCIxTfcSRdfzdkCuUe8f0HeJrS8LHUp0Ng
Content-Type: application/json
Accept: application/json

{
  "email": "<登录邮箱>",
  "password": "<登录密码>",
  "returnSecureToken": true
}
```

成功响应的关键字段：

| 字段 | 含义 |
| --- | --- |
| `idToken` | Portal API 使用的 Bearer Token |
| `refreshToken` | 换取新 ID Token 的长期凭据 |
| `expiresIn` | ID Token 有效秒数，实测为 `3600` |
| `localId` | Firebase 用户 ID，不是 Lanota 好友码 |
| `email` | 登录邮箱 |

前端登录后还会验证该 Firebase 用户是否绑定了 Portal 玩家：

```http
POST https://noxygames.com/lanota/portal/api/auth/verify-or-reject
Authorization: Bearer <FIREBASE_ID_TOKEN>
```

本次账号实测响应：

```json
{
  "ok": true,
  "uid": "84465"
}
```

其中 `uid` 是站点内部玩家 ID，也不是 `nanoId`。

### 2.2 刷新 ID Token

```http
POST https://securetoken.googleapis.com/v1/token?key=AIzaSyCIxTfcSRdfzdkCuUe8f0HeJrS8LHUp0Ng
Content-Type: application/x-www-form-urlencoded

grant_type=refresh_token&refresh_token=<URL_ENCODED_REFRESH_TOKEN>
```

响应包含 `id_token`、`refresh_token`、`expires_in`、`user_id` 等字段。后续 Portal 请求应改用新的 `id_token`。

### 2.3 Portal API 通用请求头

```http
Authorization: Bearer <FIREBASE_ID_TOKEN>
Accept: application/json
```

发送 JSON 请求时再增加：

```http
Content-Type: application/json
```

当前查到的数据接口均为 `GET`，不需要 `Content-Type`。

## 3. 好友码直接查询

### 3.1 玩家资料和统计

```http
GET https://noxygames.com/lanota/portal/api/player/{nanoId}
Authorization: Bearer <FIREBASE_ID_TOKEN>
Accept: application/json
```

目标码示例：

```http
GET /lanota/portal/api/player/W5BWeD7mgpXf
```

响应顶层结构：

```text
player
stats
recentPlays
subscription       # 不是所有目标都会返回
locked             # 功能被锁定时可能出现
```

`player` 字段：

| 字段 | 含义 |
| --- | --- |
| `nanoId` | 好友码/Portal 玩家 ID |
| `username` | 玩家名，可能为 `null` |
| `rating` | Rating |
| `totalScore` | 总分，JSON 中为字符串 |
| `notalium` | Notalium 数量 |
| `courseLevel` | 课题等级；当前数据常见为 `0` |
| `avatarId` | 头像资源 ID |

`stats` 字段：

| 字段 | 含义 |
| --- | --- |
| `totalSongsPlayed` | 有成绩的谱面数；字段名虽为 Songs，实测语义更接近谱面数量 |
| `totalCharts` | 站点统计的谱面总数 |
| `clearCounts` | 按 Clear 类型汇总 |
| `rankCounts` | 按 `L/S/A/B/C/D` 汇总 |
| `clearByDiff` | 各难度下的 Clear 类型汇总 |
| `rankByDiff` | 各难度下的 Rank 汇总 |
| `difficultyBreakdown` | 各难度已游玩数与总数 |

`recentPlays` 最多在页面展示 20 条，可能为空，也可能因权限返回 `locked.recentPlays`。单条记录由前端预期包含：

```text
songId, title, difficulty, score, clear, playedAt
```

本次 `W5BWeD7mgpXf` 的实测摘要：

| 字段 | 值 |
| --- | --- |
| 玩家名 | `0Desom0` |
| Rating | `17.22` |
| 总分 | `719118054` |
| Notalium | `965` |
| 头像 | `av_absoluteend` |
| 有成绩谱面 | `747` |
| L / S / A / B | `232 / 295 / 209 / 11` |
| Tuned / Purified / All Combo / Perfect Purified | `747 / 723 / 126 / 40` |
| Recent Plays | 本次响应为空数组 |

本次完整实测中的难度统计：

| 难度 | 已游玩 | 总数 |
| --- | ---: | ---: |
| Whisper (`0`) | 0 | 723 |
| Acoustic (`1`) | 2 | 723 |
| Ultra (`2`) | 157 | 723 |
| Master (`3`) | 588 | 723 |

### 3.2 与目标玩家逐谱面对比

```http
GET https://noxygames.com/lanota/portal/api/compare?friendNanoId={nanoId}
Authorization: Bearer <FIREBASE_ID_TOKEN>
Accept: application/json
```

响应结构：

```text
me:      { avatarId }
friend:  { nanoId, username, rating, avatarId }
summary: { wins, losses, draws, bothPlayed, totalSongs }
songs[]: {
  songId, title, difficulty, level,
  myScore, myRank, myClear,
  friendScore, friendRank, friendClear
}
```

说明：

- `myScore` 或 `friendScore` 在未游玩时为 `null`。
- `wins/losses/draws` 是登录者相对目标玩家的比较结果。
- 当前 Premium 账号实测非好友排行榜玩家也可作为 `friendNanoId` 查询。前端当前订阅页面将好友分数比较标为免费功能，但本次没有用非订阅账号复核，不能保证所有账号权限相同。
- 响应很大。本次两个目标分别约 147 KB 和 189 KB，机器人侧应设置超时、大小限制和短期缓存。

## 4. 当前登录账号接口

以下接口都由 Bearer Token 决定查询对象，不能传另一个好友码来切换玩家。

### 4.1 当前玩家简表

```http
GET /lanota/portal/api/me
```

响应：

```json
{
  "nanoId": "W5BWeD7mgpXf",
  "username": "0Desom0",
  "rating": 17.22,
  "notalium": 965,
  "avatarId": "av_absoluteend"
}
```

### 4.2 Rating 明细（B30/R15）

```http
GET /lanota/portal/api/rating
```

响应结构：

```text
player: { uid, nanoId, username, rating, totalScore, notalium, courseLevel, avatarId }
best30: {
  calculatedRating,
  entries[30]
}
recent: {
  calculatedRating,
  entries[15],
  hasData
}
hasRecords
totalSongsPlayed
locked                 # 订阅不足时可能出现
```

`best30.entries[]` 和 `recent.entries[]`：

```text
songId, title, difficulty, level, levelFraction,
harmony, tune, fail, total,
exScore, maxExScore, exScoreRate,
ratingPercent, singleRating, playedAt
```

本次账号实测拿到完整 30 条 Best 和 15 条 Recent，`locked` 不存在。

### 4.3 全谱面个人成绩

```http
GET /lanota/portal/api/scores
```

响应为 `songs[]`。本次共 2892 条，每条代表一个难度谱面：

```text
songId, title, artist, difficulty, level, levelFraction, score, clear
```

未游玩谱面的 `score`、`clear` 为 `null`。本次响应约 417 KB，应缓存而非每条机器人指令都重新拉取。

### 4.4 单曲个人成绩明细

```http
GET /lanota/portal/api/score/song?songId={songId}&difficulty={0..3}
GET /lanota/portal/api/score/song?songId={songId}&difficulty={0..3}&at={playedAt}
```

响应结构：

```text
song: {
  songId, title, artist,
  charts[]: { difficulty, level, levelFraction }
}
scores[]: {
  difficulty, score, clear, playCount, rank, singleRating, ratingRecord
}
focusScore
```

`ratingRecord` 在有详细记录时包含：

```text
harmony, tune, fail, total, exScoreRate, ratingPercent, playedAt
```

`at` 用来聚焦某次游玩记录；不传时 `focusScore` 通常为 `null`。

### 4.5 好友列表

```http
GET /lanota/portal/api/friends
```

响应：

```text
friends[]: { nanoId, username, rating, avatarId }
subscription: { tier }
```

本次账号实测返回 20 名好友。

### 4.6 订阅状态

```http
GET /lanota/portal/api/subscription/status
```

响应：

```text
isSubscribed, tier, expireAt
```

`expireAt` 为 Unix 秒时间戳。

## 5. 公共数据接口（仍需登录）

### 5.1 Rating 总榜

```http
GET /lanota/portal/api/leaderboard
```

响应结构：

```text
entries[]: { rank, nanoId, username, rating, totalScore, notalium, courseLevel }
hasMore
```

本次返回前 100 名，未发现前端使用分页参数。

### 5.2 曲目与谱面定数

```http
GET /lanota/portal/api/songs
```

响应结构：

```text
songs[]: {
  songId, title, artist,
  charts[]: { difficulty, level, levelFraction }
}
```

本次返回 720 首曲目、每首通常 4 个难度，共约 193 KB。

### 5.3 单曲排行榜

```http
GET /lanota/portal/api/leaderboard/song?songId={songId}&difficulty={0..3}
```

响应结构：

```text
song: { songId, title, artist, difficulty, level, levelFraction }
entries[]: { rank, nanoId, username, score, clear, rating }
```

本次单谱面返回前 100 名。部分 `username` 为 `null`。

### 5.4 课题模式接口

当前前端代码引用：

```http
GET /lanota/portal/api/courses
```

但在本次部署上实测返回 `404`，前端也带有功能开关/锁定逻辑，因此暂时不能作为可用接口。

## 6. 值枚举

### 6.1 难度 `difficulty`

| 值 | 名称 |
| ---: | --- |
| `0` | Whisper |
| `1` | Acoustic |
| `2` | Ultra |
| `3` | Master |

### 6.2 Clear 类型 `clear`

| 值 | 前端名称 |
| ---: | --- |
| `0` | No Play |
| `1` | Failed |
| `2` | Tuned |
| `3` | Purified |
| `4` | All Combo |
| `5` | Perfect Purified |

未游玩成绩在部分接口中直接用 `null`，不一定使用 `0`。

### 6.3 Rank

前端按分数使用以下阈值：

| Rank | 分数 |
| --- | ---: |
| `L` | `>= 980000` |
| `S` | `>= 950000` |
| `A` | `>= 900000` |
| `B` | `>= 700000` |
| `C` | `>= 600000` |
| `D` | `< 600000` |

## 7. 状态码与权限实测

| 情况 | 结果 |
| --- | --- |
| 有效 Token + 有效 `nanoId` | `200` + JSON |
| 有效 Token + 不存在的 `nanoId` | `404`，本次为空响应体 |
| 无 Token 查询 `/api/player/{nanoId}` | `401`，本次为空响应体 |
| 无 Token 查询 `/api/me` | `401`，本次为空响应体 |
| `OPTIONS /api/player/{nanoId}` | `204`，`Allow: GET, HEAD, OPTIONS` |
| 已登录 Firebase 但未绑定 Portal 玩家 | `/api/auth/verify-or-reject` 前端按 `404` 处理 |

没有在响应中观察到可依赖的限流配额说明。插件应主动限速、缓存，并对 `401/404/429/5xx` 做容错。

## 8. Python 最小调用示例

依赖：`requests`。密码只从环境变量读取，不应写入插件配置仓库或日志。

```python
import os
from urllib.parse import quote

import requests


FIREBASE_API_KEY = 'AIzaSyCIxTfcSRdfzdkCuUe8f0HeJrS8LHUp0Ng'
PORTAL_API = 'https://noxygames.com/lanota/portal/api'


def login(email: str, password: str) -> dict:
    response = requests.post(
        'https://identitytoolkit.googleapis.com/v1/'
        f'accounts:signInWithPassword?key={FIREBASE_API_KEY}',
        json={
            'email': email,
            'password': password,
            'returnSecureToken': True,
        },
        timeout=15,
    )
    response.raise_for_status()
    return response.json()


def get_player(id_token: str, friend_code: str) -> dict:
    response = requests.get(
        f'{PORTAL_API}/player/{quote(friend_code, safe="")}',
        headers={
            'Authorization': f'Bearer {id_token}',
            'Accept': 'application/json',
        },
        timeout=15,
    )
    response.raise_for_status()
    return response.json()


auth = login(
    os.environ['LANOTA_PORTAL_EMAIL'],
    os.environ['LANOTA_PORTAL_PASSWORD'],
)
player = get_player(auth['idToken'], 'W5BWeD7mgpXf')
print(player['player']['username'], player['player']['rating'])
```

建议生产插件另外实现：

1. 缓存 `idToken` 到过期前，并用 `refreshToken` 刷新；不要每次指令都重新提交密码。
2. 对玩家资料做 1 至 5 分钟缓存，对曲库和个人全谱面数据做更长缓存。
3. 不记录密码、ID Token、Refresh Token 或完整认证响应。
4. 限制好友码格式和长度，并始终进行 URL 编码。
5. 为网络请求设置连接/读取超时，并处理站点改版、字段缺失和非 JSON 响应。

## 9. 国服 Portal 认证与接口

国服入口和 API 根地址：

```text
Portal: https://lanota.gmzon.com/portal
API:    https://lanota.gmzon.com/portal/api
```

国服不使用 Firebase 邮箱密码，而是使用 Lanota App/二维码授权：

```text
POST /portal/api/auth/init-app-login
GET  /portal/api/auth/poll?session_id={session_id}
POST /portal/api/auth/exchange
     JSON: { code, session_id }
```

实际前端生成的二维码内容如下：

```text
lanotagames-cn://portal-auth
  ?session_id={URL 编码后的 session_id}
  &callback={URL 编码后的 https://lanota.gmzon.com/portal/auth/callback?...}
```

授权流程：

1. `init-app-login` 返回短期 `session_id`。
2. 使用上述深链生成二维码，由国服 Lanota App 扫描。
3. 每 2 秒请求一次 `poll`；未授权时返回 `{"status":"pending"}`。
4. 授权后 `poll` 返回 `{"status":"ready","code":"..."}`。
5. 把一次性 `code` 和 `session_id` 提交给 `exchange`。
6. 国服响应 `{"chinaToken":"...","uid":"..."}`。

`chinaToken` 是带 `exp` 的 JWT，通过下列请求头访问国服 `/me`、`/player/{好友码}` 等接口：

```http
Authorization: Bearer <chinaToken>
Accept: application/json
```

前端将它保存到 `localStorage['lanota.portal.chinaToken']`。目前没有发现国服 Token 刷新接口；过期后必须重新扫码授权。插件对应命令为：

```text
.la china login
.la china status
.la bind cn <好友码>
.la user
```

插件把国服 Token 单独保存在运行期 `plugin/data/LanotaPlugin/portal_auth_china.json`，不会与国际服 Firebase Token 混用，也不会写入源码仓库。

### 9.1 国服接口实测结果（2026-07-31）

以下请求均使用有效 `chinaToken`，只记录状态码和结构，不记录 Token、好友码或个人数值：

| 接口 | 状态 | 实测结果 |
| --- | ---: | --- |
| `GET /api/me` | `200` | 返回 `avatarId/nanoId/notalium/rating/username` |
| `GET /api/player/{nanoId}` | `200` | 返回 `player/stats/recentPlays/locked`；排行榜中的非好友也可查询 |
| `GET /api/compare?friendNanoId={nanoId}` | `200` | 非好友目标也可对比，返回 `me/friend/summary/songs` |
| `GET /api/rating` | `200` | 当前账号返回 `locked.best30/recent`，没有 `best30/recent` 明细，属于权限锁定 |
| `GET /api/scores` | `200` | 返回 `songs`，本次共 2920 条谱面成绩 |
| `GET /api/score/song?...` | `200` | 返回 `song/scores/focusScore` |
| `GET /api/friends` | `200` | 返回 `friends/subscription`，本次好友列表为空 |
| `GET /api/subscription/status` | `200` | 返回 `isSubscribed/tier/expireAt` |
| `GET /api/leaderboard` | `200` | 返回 `entries/hasMore`，本次 100 条 |
| `GET /api/songs` | `200` | 返回 `songs`，本次 730 首 |
| `GET /api/leaderboard/song?...` | `200` | 返回 `song/entries`，本次 8 条 |
| `GET /api/courses` | `404` | 国服当前没有这个接口，不能作为可用功能 |

因此国服和国际服的公开玩家、对比、曲库、排行榜接口基本兼容；Rating B30/R15 和全谱面成绩仍受账号订阅权限控制，不能把 `200 + locked` 当成接口错误。

## 10. 安全与使用边界

- 本文没有保存本次调研使用的邮箱、密码、ID Token 或 Refresh Token。
- `idToken` 一般约 1 小时过期，但在有效期内等同登录会话；`refreshToken` 风险更高，应视为密码级秘密。
- 接口没有公开稳定性承诺。部署前应确认符合站点服务条款，并避免高频遍历玩家、排行榜或成绩数据。
- `player` 和 `compare` 会返回其他玩家资料/成绩。机器人展示时应仅响应用户主动提供的好友码，并避免建立无关的批量数据库。

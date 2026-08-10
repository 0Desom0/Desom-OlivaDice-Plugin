# Lanota IPA API 调研记录

> 调研日期：2026-08-11  
> 调研来源：`娱乐/LanotaPlugin/辅助脚本_正常不会调用/国服ipa/调律诗篇-4.0.0.ipa`  
> App 版本：`4.0.0`，Bundle ID：`com.gmzon.lanota`  
> 性质：从 IPA 内 IL2CPP、Protobuf、gRPC 定义还原的非官方接口，后续可能随客户端版本变化。  
> 平行文档：[Lanota_Portal_API_调研.md](./Lanota_Portal_API_调研.md)

## 1. 结论

- 该 IPA 是 Unity IL2CPP 国服客户端，业务代码编入 `Lanota.app/Frameworks/UnityFramework.framework/UnityFramework`。
- 国服正式 gRPC 主机为 `cn01.svr-lanota-prod.gmzon.com`，按端口区分服务，均使用 TLS。
- 好友码在 IPA 的 gRPC 接口中同样是 `nanoId`。
- `SearchPlayer` 和 `GetPlayerSongRecord` 实测无需 Portal/Firebase Token 即可匿名调用。
- 好友码 `8kxJ57srY49WT` 已验证：
  - `SearchPlayer` 查到玩家 `Ritmo95267`；
  - `GetPlayerSongRecord` 查到 `poppy` 两个难度的成绩。

## 2. 还原方法

IPA 使用 Unity 6.x 的 IL2CPP metadata v39，官方 Il2CppDumper 6.7.46 暂不支持 v39，因此使用 `roytu/Il2CppDumper` 的 v39 分支完成还原。

还原产物中与本调研相关的关键文件：

| 文件 | 内容 |
| --- | --- |
| `dump.cs` | 所有 IL2CPP 类型、字段、方法、字符串地址 |
| `DummyDll/` | 还原出的托管程序集骨架，含 `LanotaServices.Grpc.dll` 等 |
| `stringliteral.json` | 二进制内字符串字面量 |
| `script.json` | IL2CPP 方法地址与元数据 |

IPA 内的 gRPC 定义主要来自以下程序集：

| 程序集 | 说明 |
| --- | --- |
| `LanotaServices.Grpc.dll` | 主要业务服务定义 |
| `Services.Grpc.dll` | 国服账号、云存档、远程配置等附加服务定义 |
| `ItemServicesPackage.dll` | 高层服务封装、结果类型、渠道配置 |

## 3. 服务端通道

国服地址常量：

| 用途 | 地址 |
| --- | --- |
| Item / 商城 / 活动服务 | `cn01.svr-lanota-prod.gmzon.com:5000` |
| Community / 好友 / 成绩服务 | `cn01.svr-lanota-prod.gmzon.com:5001` |
| CloudSave / 云存档 | `cn01.svr-lanota-prod.gmzon.com:5002` |
| ChinaAccount | `cn01.svr-lanota-prod.gmzon.com:5003` |
| ChinaRemoteConfig | `cn01.svr-lanota-prod.gmzon.com:5004` |
| CosUrlSigner | `cn01.svr-lanota-prod.gmzon.com:8080` |

IPA 内同时保留了 `cn02.svr-lanota-prod.gmzon.com` 对应端口作为备份，但本次调研时该域名无法解析。

连接要求：

- 所有端口均使用 TLS，证书 CN 为 `svr-lanota-prod.gmzon.com`。
- 协议为 gRPC over HTTP/2。
- 部分查询类 RPC 实测不要求认证 metadata；写操作、购买、好友管理、云存档等通常需要 Firebase token。

## 4. gRPC 服务与方法

### 4.1 端口 5000：Item / 商城 / 活动

服务路径统一为 `/lanota_services.<Service>/<Method>`。

#### TicketEvent

| 方法 | 请求 | 响应 |
| --- | --- | --- |
| `GetCurrentEventAndPlayerProgress` | `GetEventAndPlayerProgressRequest` | `GetEventAndPlayerProgressResponse` |
| `UpdateEventProgress` | `UpdateEventProgressRequest` | `UpdateEventProgressResponse` |
| `UpdateBossProgress` | `UpdateBossProgressRequest` | `UpdateBossProgressResponse` |
| `UpdateBossMissionLevel` | `UpdateBossMissionLevelRequest` | `UpdateBossMissionLevelResponse` |
| `GetTicketEventRelativeItems` | `GetTicketEventRelativeItemsRequest` | `GetTicketEventRelativeItemsResponse` |
| `BuyBossPass` | `BuyBossPassRequest` | `BuyBossPassResponse` |
| `ReceiveMissionReward` | `ReceiveMissionRewardRequest` | `ReceiveMissionRewardResponse` |
| `ReceiveAllMissionReward` | `ReceiveAllMissionRewardRequest` | `ReceiveAllMissionRewardResponse` |
| `BuyBossPassGoogle` | `BuyBossPassGoogleRequest` | `BuyBossPassGoogleResponse` |
| `BuyBossPassApple` | `BuyBossPassAppleRequest` | `BuyBossPassAppleResponse` |
| `BuyBossPassTaptap` | `BuyBossPassTaptapRequest` | `BuyBossPassTaptapResponse` |

#### HardCoin

| 方法 | 请求 | 响应 |
| --- | --- | --- |
| `GetHardCoinRelativeItems` | `GetHardCoinRelativeItemsRequest` | `GetHardCoinRelativeItemsResponse` |
| `BuyHardCoinGoogle` | `BuyHardCoinGoogleRequest` | `BuyHardCoinGoogleResponse` |
| `BuyHardCoinApple` | `BuyHardCoinAppleRequest` | `BuyHardCoinAppleResponse` |
| `BuyHardCoinTaptap` | `BuyHardCoinTaptapRequest` | `BuyHardCoinTaptapResponse` |
| `BuyTicketByHardCoin` | `BuyTicketByHardCoinRequest` | `BuyTicketByHardCoinResponse` |
| `BoostByHardCoin` | `BoostByHardCoinRequest` | `BoostByHardCoinResponse` |
| `BuyCourseTicketExtra` | `BuyCourseTicketExtraRequest` | `BuyCourseTicketExtraResponse` |
| `FreeSoftCoinLevelUp` | `FreeSoftCoinLevelUpRequest` | `FreeSoftCoinLevelUpResponse` |
| `GetFreeCoinLevelUpRelative` | `GetFreeCoinLevelUpRelativeRequest` | `GetFreeCoinLevelUpRelativeResponse` |
| `BuyNonConsumableGoogle` | `BuyNonConsumableGoogleRequest` | `BuyNonConsumableGoogleResponse` |
| `BuyNonConsumableApple` | `BuyNonConsumableAppleRequest` | `BuyNonConsumableAppleResponse` |
| `BuyNonConsumableTaptap` | `BuyNonConsumableTaptapRequest` | `BuyNonConsumableTaptapResponse` |

#### CoinTicket

| 方法 | 请求 | 响应 |
| --- | --- | --- |
| `TriggerReloadMeta` | `ReloadMetaRequest` | `ReloadMetaResponse` |
| `GetPlayerMeta` | `GetPlayerMetaRequest` | `GetPlayMetaResponse` |
| `LevelUpSoftCoin` | `LevelUpSoftCoinRequest` | `LevelUpSoftCoinResponse` |
| `LevelUpVipRoomTicket` | `LevelUpVipRoomTicketRequest` | `LevelUpVipRoomTicketResponse` |
| `BuyVipRoomTicket` | `BuyVipRoomTicketRequest` | `BuyVipRoomTicketResponse` |
| `ConsumeVipRoomTicket` | `ConsumeVipRoomTicketRequest` | `ConsumeVipRoomTicketResponse` |
| `GetPlayToken` | `GetPlayTokenRequest` | `GetPlatTokenResponse` |
| `OnResultPlayed` | `OnResultPlayedRequest` | `OnResultPlayedResponse` |
| `OnResultRewardAdsWatched` | `OnResultRewardAdsWatchedRequest` | `OnResultRewardAdsWatchedResponse` |
| `GetCurrentEventToken` | `GetCurrentEventTokenRequest` | `GetCurrentEventTokenResponse` |
| `RewardFreeSoftCoin` | `RewardFreeSoftCoinRequest` | `RewardFreeSoftCoinResponse` |
| `BuyAndConsumeTicket` | `BuyAndConsumeTicketRequest` | `BuyAndConsumeTicketResponse` |
| `BuyCourseTicketNormal` | `BuyCourseTicketNormalRequest` | `BuyCourseTicketNormalResponse` |
| `ConsumeCourseEnterItem` | `ConsumeCourseEnterItemRequest` | `ConsumeCourseEnterItemResponse` |
| `ReceiveGift` | `ReceiveGiftRequest` | `ReceiveGiftResponse` |
| `OpenRouletteBox` | `OpenRouletteBoxRequest` | `OpenRouletteBoxResponse` |

#### BeginnerEvent

| 方法 | 请求 | 响应 |
| --- | --- | --- |
| `GetBeginnerEventMeta` | `GetBeginnerEventMetaRequest` | `GetBeginnerEventMetaResponse` |
| `ConsumeBeginnerTicket` | `ConsumeBeginnerTicketRequest` | `ConsumeBeginnerTicketResponse` |
| `GetMissionReward` | `GetBeginnerMissionRewardRequest` | `GetBeginnerMissionRewardResponse` |
| `ContinueBeginnerMission` | `ContinueBeginnerMissionRequest` | `ContinueBeginnerMissionResponse` |

#### RewardShop

| 方法 | 请求 | 响应 |
| --- | --- | --- |
| `GetRewardShopRelativeItem` | `GetRewardShopRelativeItemRequest` | `GetRewardShopRelativeItemResponse` |
| `GetProductMetasAndPlayerStatus` | `GetProductMetasAndPlayerStatusRequest` | `GetProductMetasAndPlayerStatusResponse` |
| `UpdateProductSoftCoinProgress` | `UpdateProductSoftCoinProgressRequest` | `UpdateProductSoftCoinProgressResponse` |
| `BuyProduct` | `BuyProductRequest` | `BuyProductResponse` |

#### CustomizeShop

| 方法 | 请求 | 响应 |
| --- | --- | --- |
| `GetCustomizeShopProductsAndPlayerStatus` | `GetCustomizeShopProductsRequest` | `GetCustomizeShopProductsResponse` |
| `BuyCustomizeShopProduct` | `BuyCustomizeShopProductRequest` | `BuyCustomizeShopProductResponse` |
| `GetCustomizeShopRelativeItem` | `GetCustomizeShopRelativeItemRequest` | `GetCustomizeShopRelativeItemResponse` |

### 4.2 端口 5001：Community

服务路径：`/lanota_services.Community/<Method>`

| 方法 | 请求 | 响应 |
| --- | --- | --- |
| `GetCommunityRelativeItem` | `GetCommunityRelativeItemRequest` | `GetCommunityRelativeItemResponse` |
| `GetFriendData` | `GetFriendDataRequest` | `GetFriendDataResponse` |
| `GetFriendScore` | `GetFriendScoreRequest` | `GetFriendScoreResponse` |
| `CreateFriendRequest` | `CreateFriendRequestRequest` | `CreateFriendRequestResponse` |
| `CancelFriendRequest` | `CancelFriendRequestRequest` | `CancelFriendRequestResponse` |
| `RejectFriendRequest` | `RejectFriendRequestRequest` | `RejectFriendRequestResponse` |
| `AcceptFriendRequest` | `AcceptFriendRequestRequest` | `AcceptFriendRequestResponse` |
| `DeleteFriendShip` | `DeleteFriendShipRequest` | `DeleteFriendShipResponse` |
| `SearchPlayer` | `SearchPlayerRequest` | `SearchPlayerResponse` |
| `UpdateSelectedSong` | `UpdateSelectedSongRequest` | `UpdateSelectedSongResponse` |
| `GetPlayerSongRecord` | `GetPlayerSongRecordRequest` | `GetPlayerSongRecordResponse` |
| `AddPlayerLimit` | `AddPlayerLimitRequest` | `AddPlayerLimitResponse` |
| `UpdatePlayerNameAvatar` | `UpdatePlayerNameAvatarRequest` | `UpdatePlayerNameAvatarResponse` |
| `UploadGhost` | `UploadGhostRequest` | `UploadGhostResponse` |
| `ListGhostHeadersForChart` | `ListGhostHeadersForChartRequest` | `ListGhostHeadersForChartResponse` |
| `MintGhostDownloadUrls` | `MintGhostDownloadUrlsRequest` | `MintGhostDownloadUrlsResponse` |
| `UpdateGhostSharing` | `UpdateGhostSharingRequest` | `UpdateGhostSharingResponse` |
| `UploadCourseResult` | `UploadCourseResultRequest` | `UploadCourseResultResponse` |

### 4.3 端口 5002：FirebaseCloudSave

服务路径：`/lanota_services.FirebaseCloudSave/<Method>`

| 方法 | 请求 | 响应 |
| --- | --- | --- |
| `SyncCloudSaveRecords` | `SyncCloudSaveRecordsRequest` | `SyncCloudSaveRecordsResponse` |
| `GetCloudSaveRecords` | `SyncCloudSaveRecordsRequest` | `SyncCloudSaveRecordsResponse` |
| `PutCloudSaveRecords` | `SyncCloudSaveRecordsRequest` | `SyncCloudSaveRecordsResponse` |

### 4.4 端口 5003：ChinaAccounts

服务路径：`/lanota_services.ChinaAccounts/<Method>`

| 方法 | 请求 | 响应 |
| --- | --- | --- |
| `GetChinaUserProfileData` | `GetChinaUserProfileDataRequest` | `ChinaUserProfileDataResponse` |
| `UpdateChinaUserProfileData` | `UpdateChinaUserProfileDataRequest` | `ChinaUserProfileDataResponse` |
| `GetChinaUserNanoId` | `GetChinaUserNanoIdRequest` | `ChinaUserProfileDataResponse` |
| `DeleteChinaUserAccount` | `ChinaDeleteAccountRequest` | `ChinaDeleteAccountResponse` |
| `GetJwtToken` | `GetJwtTokenRequest` | `ChinaUserProfileDataResponse` |
| `ChinaLinkAccount` | `ChinaLinkAccountRequest` | `ChinaUserProfileDataResponse` |
| `ChinaUnlinkAccount` | `ChinaUnlinkAccountRequest` | `ChinaUserProfileDataResponse` |
| `ChinaDownloadResource` | `ChinaDownloadResourceRequest` | `ChinaDownloadResourceResponse` |

### 4.5 端口 5004：RemoteConfigService

服务路径：`/lanota_services.RemoteConfigService/GetRemoteConfig`

| 方法 | 请求 | 响应 |
| --- | --- | --- |
| `GetRemoteConfig` | `GetRemoteConfigRequest` | `GetRemoteConfigResponse` |

### 4.6 端口 8080：CosUrlSigner

服务路径：`/cos_signer.CosUrlSigner/GenerateSignedUrl`

| 方法 | 请求 | 响应 |
| --- | --- | --- |
| `GenerateSignedUrl` | `GenerateSignedUrlRequest` | `GenerateSignedUrlResponse` |

### 4.7 定义存在但当前 CN 端点未观察到挂载

以下服务定义可以从 IPA 中还原，但本次对 `5000-5004/8080` 实测时返回 `UNIMPLEMENTED`，当前国服构建中可能未启用，或挂载在其它环境中：

| 服务 | 说明 |
| --- | --- |
| `lanota_services.Events` | 两套程序集中重复出现 |
| `lanota_services.Subscriptions` | 订阅相关定义 |
| `lanota_services.Accounts` | 与 `AccountServiceUrl = ""` 一致，疑似未启用 |
| `ping.PingService` | 健康检查定义 |

#### Events

| 方法 | 请求 | 响应 |
| --- | --- | --- |
| `GetEventProgress` | `EventProgressRequest` | `EventProgressResponse` |
| `GetEventToken` | `EventTokenRequest` | `EventTokenResponse` |
| `UpdateEventProgress` | `EventUpdateProgressRequest` | `EventUpdateProgressResponse` |
| `GetAllEventProgress` | `AllEventProgressRequest` | `AllEventProgressResponse` |
| `GetEventStamina` | `EventStaminaRequest` | `EventStaminaResponse` |
| `GetHardCoin` | `HardCoinRequest` | `HardCoinResponse` |
| `ExchangeHardCoinToStamina` | `ExchangeHardCoinToStaminaRequest` | `ExchangeHardCoinToStaminaResponse` |
| `BoostEventProgress` | `BoostProgressRequest` | `BoostProgressResponse` |
| `GeneralGetItem` | `GeneralGetItemsRequest` | `GeneralGetItemsResponse` |
| `GeneralConsumeItem` | `GeneralConsumeItemsRequest` | `GeneralConsumeItemsResponse` |
| `GeneralTransaction` | `GeneralTransactionRequest` | `GeneralTransactionResponse` |

#### Subscriptions

| 方法 | 请求 | 响应 |
| --- | --- | --- |
| `ClaimSubscription` | `ClaimSubscriptionRequest` | `ClaimSubscriptionResponse` |
| `ClaimSubscriptionBatch` | `ClaimSubscriptionBatchRequest` | `ClaimSubscriptionBatchResponse` |
| `UpdateSubscriptionProducts` | `UpdateSubscriptionProductsRequest` | `UpdateSubscriptionProductsResponse` |
| `QuerySubscriptionStatus` | `QuerySubscriptionStatusRequest` | `QuerySubscriptionStatusResponse` |

#### Accounts

| 方法 | 请求 | 响应 |
| --- | --- | --- |
| `GetUserMeta` | `UserMetaRequest` | `UserMetaResponse` |
| `SetUserMeta` | `UserMetaSetRequest` | `UserMetaResponse` |
| `RegisterWithEmail` | `RegisterWithEmailRequest` | `LoginResponse` |
| `GetUserIdWithEmail` | `UserIdWithEmailRequest` | `LoginResponse` |
| `GetUserNanoId` | `UserMetaRequest` | `UserNanoIdResponse` |

#### PingService

| 方法 | 请求 | 响应 |
| --- | --- | --- |
| `Ping` | `Request` | `Response` |

## 5. Community 查询 API 详解

### 5.1 SearchPlayer

服务路径：`/lanota_services.Community/SearchPlayer`

请求字段：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `search_type` | enum | `0=NANOID`、`1=USERNAME`、`2=SINGLENANO` |
| `search_string` | string | 好友码、用户名或单个 nanoId |

响应字段：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `player_datas` | repeated `PlayerProfileData` | 匹配到的玩家资料 |

`PlayerProfileData`：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `nano_id` | string | 好友码 |
| `username` | string | 玩家名 |
| `avatar_id` | string | 头像资源 ID |
| `rating` | float | Rating |
| `notalium` | int32 | Notalium |
| `total_score` | int64 | 总分 |
| `friend_limit` | int32 | 当前好友上限 |
| `song_id` | string | 当前选中歌曲 |
| `song_select_time` | int64 | 选中歌曲时间 |
| `player_panel_id` | string | 玩家面板 |
| `course_level` | int32 | 课题等级 |
| `is_name_avatar_null` | bool | 名称头像是否为空 |
| `course_badge_id` | string | 课题徽章 |

### 5.2 GetPlayerSongRecord

服务路径：`/lanota_services.Community/GetPlayerSongRecord`

请求字段：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `nano_id` | string | 要查询玩家的好友码 |

响应字段：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `chart_records` | repeated `ChartRecord` | 该玩家全部有成绩的谱面 |

`ChartRecord`：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `song_id` | string | 歌曲 ID |
| `difficulty` | int32 | 难度 |
| `score` | int32 | 分数 |
| `clear` | int32 | Clear 类型 |

### 5.3 GetFriendScore

服务路径：`/lanota_services.Community/GetFriendScore`

请求字段：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `user_id` | string | 当前登录用户的 Firebase 用户 ID |
| `song_id` | string | 歌曲 ID |
| `difficulty` | int32 | 难度 |

响应字段：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `player_scores` | repeated `PlayerScore` | 当前用户好友列表在该歌曲的成绩 |

`PlayerScore`：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `nano_id` | string | 好友码 |
| `user_name` | string | 玩家名 |
| `avatar_id` | string | 头像 |
| `score` | int32 | 分数 |
| `clear` | int32 | Clear 类型 |

注意：`GetFriendScore` 不是“按好友码查任意玩家”，而是查当前账号好友列表在指定歌曲上的分数。

### 5.4 GetFriendData

服务路径：`/lanota_services.Community/GetFriendData`

请求字段：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `user_id` | string | 当前登录用户的 Firebase 用户 ID |

响应字段：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `friend_datas` | repeated `PlayerProfileData` | 好友列表 |
| `sender_datas` | repeated `PlayerProfileData` | 发给我的申请 |
| `receiver_datas` | repeated `PlayerProfileData` | 我发出的申请 |
| `self_data` | `PlayerProfileData` | 我的公开资料 |
| `friend_limit_default` | int32 | 默认好友上限 |
| `friend_limit_max` | int32 | 最大好友上限 |
| `friend_limit_add_cost` | int32 | 扩容花费 |
| `is_async_transaction_complete` | bool | 异步事务是否完成 |

### 5.5 好友管理

通用响应字段通常为：

| 字段 | 说明 |
| --- | --- |
| `success` | 是否成功 |
| `fail_code` | 失败码 |
| `fail_message` | 失败信息 |
| `sender_datas` / `receiver_datas` / `friend_datas` | 操作后更新的列表 |

各方法请求字段：

| 方法 | 关键字段 |
| --- | --- |
| `CreateFriendRequest` | `user_id`, `receiver_nano_id` |
| `CancelFriendRequest` | `user_id`, `receiver_nano_id` |
| `RejectFriendRequest` | `user_id`, `sender_nano_id` |
| `AcceptFriendRequest` | `user_id`, `sender_nano_id` |
| `DeleteFriendShip` | `user_id`, `sender_nano_id` |
| `UpdateSelectedSong` | `user_id`, `song_id` |
| `AddPlayerLimit` | `user_id` |
| `UpdatePlayerNameAvatar` | `uid`, `username`, `avatar_id` |

### 5.6 Ghost / 回放

| 方法 | 请求关键字段 | 说明 |
| --- | --- | --- |
| `UploadGhost` | `user_id`, `song_id`, `difficulty`, `final_score`, `recorded_unix_ms`, `app_version`, `is_public`, `score_blob`, `judge_blob`, `input_blob` | 上传回放 |
| `ListGhostHeadersForChart` | `user_id`, `song_id`, `difficulty` | 列出自己与好友的回放头 |
| `MintGhostDownloadUrls` | `user_id`, `owner_nano_id`, `song_id`, `difficulty`, `slot` | 换取回放下载 URL |
| `UpdateGhostSharing` | `user_id`, `song_id`, `difficulty`, `slot`, `is_public` | 设置回放公开状态 |
| `UploadCourseResult` | `user_id`, `course_id`, `pass_clear`, `songs`, `recorded_unix_ms`, `app_version` | 上传课题成绩 |

`GhostHeaderProto`：

| 字段 | 说明 |
| --- | --- |
| `owner_nano_id` | 回放所属玩家 |
| `song_id` / `difficulty` | 歌曲与难度 |
| `slot` | `0=BEST`，`1=LAST` |
| `final_score` | 最终分数 |
| `recorded_unix_ms` | 记录时间 |
| `app_version` | 客户端版本 |
| `is_public` | 是否公开 |
| `score_size_bytes` / `judge_size_bytes` / `input_size_bytes` | 各部分大小 |
| `hi_speed_main` / `hi_speed_fraction` / `gauge_type` / `timing_offset_seconds` | 游玩参数 |

## 6. 常用服务字段摘要

### 6.1 GetPlayerMeta（CoinTicket）

服务路径：`/lanota_services.CoinTicket/GetPlayerMeta`

请求：`uid`

响应中包含的主要字段：

| 字段 | 说明 |
| --- | --- |
| `current_soft_coin_count` | 当前 Soft Coin |
| `current_soft_coin_level` / `current_soft_coin_max` | Soft Coin 等级与上限 |
| `hard_coin_current_count` / `paid_hard_coin_current_count` / `free_hard_coin_current_count` | 各种 Hard Coin |
| `vip_room_ticket_current_count` / `vip_room_ticket_current_level` | VIP Room 票 |
| `course_ticket_current_count` / `course_ticket_max` | 课题票 |
| `boost_remain_count` | 剩余加成次数 |
| `is_any_event_available` | 是否有活动可玩 |
| `unlocked_player_panel_ids` / `unlocked_companion_ids` | 已解锁面板与同伴 |
| `server_current_time_millis` | 服务器时间 |

### 6.2 GetRemoteConfig

服务路径：`/lanota_services.RemoteConfigService/GetRemoteConfig`

实测返回为 `key -> value` 形式的远程配置，例如 `current_active_time_limit_event_banner`、`song_ads_level_weight_table`、`viproom_ticket_songs` 等。

### 6.3 ChinaAccounts

`GetChinaUserNanoId` 请求：`GetChinaUserNanoIdRequest`

响应：`ChinaUserProfileDataResponse`，其中可包含 `nano_id` 等账号资料。

## 7. HTTP / REST 接口

除 gRPC 外，IPA 中还能还原出以下 HTTP API。

### 7.1 Firebase 认证包装器

主机：`https://lanota-services-firebase-wrapper-ab3xrc2pkq-uc.a.run.app`

路径模板：

| 路径 | function 参数 | 用途 |
| --- | --- | --- |
| `/v3?function=signInWithEmailPassword` | `signInWithEmailPassword` | 邮箱登录 |
| `/v3?function=signUpWithEmailPassword` | `signUpWithEmailPassword` | 邮箱注册 |
| `/v3?function=signInWithOAuthCredential` | `signInWithOAuthCredential` | OAuth 登录 |
| `/v3?function=signInWithCustomToken` | `signInWithCustomToken` | 自定义 Token 登录 |
| `/v3?function=signInAnonymously` | `signInAnonymously` | 匿名登录 |
| `/v3?function=linkWithEmailPassword` | `linkWithEmailPassword` | 绑定邮箱 |
| `/v3?function=linkWithOAuthCredential` | `linkWithOAuthCredential` | 绑定 OAuth |
| `/v3?function=unlinkProvider` | `unlinkProvider` | 解绑 Provider |
| `/v3?function=sendPasswordResetEmail` | `sendPasswordResetEmail` | 重置密码 |
| `/v3?function=changeEmail` | `changeEmail` | 修改邮箱 |
| `/v3?function=deleteAccount` | `deleteAccount` | 删除账号 |
| `/v3?function=updateProfile` | `updateProfile` | 更新资料 |
| `/v3?function=getUserData` | `getUserData` | 查询用户数据 |
| `/v3?function=sendEmailVerification` | `sendEmailVerification` | 发送验证邮件 |
| `/v3?function=fetchProvidersForEmail` | `fetchProvidersForEmail` | 查询邮箱已绑定的 Provider |
| `/v1?function=exchangeRefreshTokenForIdToken` | `exchangeRefreshTokenForIdToken` | 刷新 ID Token |
| `/getCustomToken` | - | Apple 等渠道换 Custom Token |

IPA 内 Firebase 配置（国服 App）：

| 配置 | 值 |
| --- | --- |
| Firebase project | `lanota-cn` |
| API key | `AIzaSyDh-xgRii0yHAMzx92p5QldbxKctLixBBs` |
| GCM sender | `793142835777` |
| iOS App ID | `1:793142835777:ios:ef372abc865c0bca6ae4c0` |

### 7.2 国服账号迁移

主机：`https://cn01.svr-lanota-prod.gmzon.com:3001`

| function | 用途 |
| --- | --- |
| `check` | 检查迁移信息 |
| `transfer` | 提交迁移 |
| `verification` | 验证 |

客户端方法签名：

| 方法 | 参数 |
| --- | --- |
| `GetCheckApplyInfo` | `userId`, `restoreId`, `password`, `jwtTokenSpaceNonce` |
| `TransferApply` | `userId`, `restoreId`, `password`, `jwtTokenSpaceNonce` |
| `VerificationApply` | `userId`, `jwtTokenSpaceNonce` |

### 7.3 国服 IAP 绑定

主机：`https://lanota-chinaiapbinder-prod.hk01.gmzon.com/ChinaIapBinder`

| function | 用途 |
| --- | --- |
| `check` | 检查绑定状态 |
| `android` | 提交 Android 转移 |
| `ios` | 提交 iOS 转移 |
| `set_password` | 设置恢复密码 |

### 7.4 收据校验

| 地址 | 用途 |
| --- | --- |
| `https://lanota-app.noxygames.com/general-iap-receipt-validate` | Apple 收据校验 |
| `https://lanota-app.noxygames.com/google-play-iap-verification` | Google Play 收据校验 |

### 7.5 账号管理与其它云函数

| 地址 | 用途 |
| --- | --- |
| `https://us-central1-lanota-67543202.cloudfunctions.net/lanota-account-manage` | 账号删除等管理操作 |
| `https://us-central1-lanota-67543202.cloudfunctions.net/lanotaSuikaRanking?function=getRank` | 愚人节排行榜查询 |
| `https://us-central1-lanota-67543202.cloudfunctions.net/lanotaSuikaRanking?function=updateScoreSafe` | 愚人节排行榜上传 |
| `https://lanota-server.appspot.com/user` | 旧版用户接口 |

### 7.6 图内测试 / 谱面测试

| 地址 | 用途 |
| --- | --- |
| `https://asia-east1-lanota-chart-test.cloudfunctions.net/getVersion` | 谱面测试版本检查 |
| `https://asia-east1-lanota-chart-test.cloudfunctions.net/getGameLog` | 下载输入回放日志 |
| `https://asia-east1-lanota-chart-test.cloudfunctions.net/gameLog` | 上传输入回放日志 |

### 7.7 新闻与资源

| 地址 | 用途 |
| --- | --- |
| `https://lanota-game-misc.noxygames.com/lanota_news.json` | 在线公告 |
| `https://lanota-bundle-release.noxygames.com/Android/<hash>/` | Android 资源包根目录 |
| `http://files.lanota.noxygames.com/` | 文件资源 |
| `http://noxygames.com/lanota/metaresource/title_11.png` | 示例元资源 |
| `https://lanota.gmzon.com/portal` | 国服 Portal 入口 |
| `https://noxygames.com/lanota/` | 国际服 Portal 入口 |

## 8. 认证说明

- IPA 内 gRPC 调用通过 `FirebaseAuthGrpcExtension` 获取 Firebase ID Token，并构造 gRPC `CallOptions`。
- 相关字符串包括 `Authorization`、`Bearer `、`Auth-Type`、`authorization-native`。
- 本次实测 `SearchPlayer`、`GetPlayerSongRecord`、`GetPlayerMeta`、`GetBeginnerEventMeta`、`GetHardCoinRelativeItems` 等查询不需要 Token 即可返回数据。
- `CosUrlSigner.GenerateSignedUrl` 实测会检查请求时间戳并返回 `Request timestamp is out of tolerance window`。
- 写操作、好友管理、云存档、购买类接口仍应视为需要认证，不应假定全部匿名可调。

## 9. 验证记录

### 9.1 SearchPlayer

请求：

```text
POST /lanota_services.Community/SearchPlayer
search_type = 0 (NANOID)
search_string = 8kxJ57srY49WT
```

实测响应：

```json
{
  "player_datas": [
    {
      "nano_id": "8kxJ57srY49WT",
      "username": "Ritmo95267",
      "rating": 1.76,
      "notalium": 2,
      "total_score": 1886385
    }
  ]
}
```

### 9.2 GetPlayerSongRecord

请求：

```text
POST /lanota_services.Community/GetPlayerSongRecord
nano_id = 8kxJ57srY49WT
```

实测响应：

```json
{
  "chart_records": [
    { "song_id": "poppy", "difficulty": 2, "score": 966281, "clear": 3 },
    { "song_id": "poppy", "difficulty": 3, "score": 920104, "clear": 3 }
  ]
}
```

### 9.3 GetFriendScore

以 `8kxJ57srY49WT` 作为 `user_id` 调用 `GetFriendScore` 时返回空 `player_scores`，符合该接口“查询当前用户好友列表”的语义，不能用来直接查询任意好友码的全量成绩。

## 10. Python 最小调用示例

以下示例只演示 Community 查询接口，不依赖生成代码，直接发送 protobuf 字节：

```python
import grpc

host = "cn01.svr-lanota-prod.gmzon.com:5001"
code = "8kxJ57srY49WT"

ch = grpc.secure_channel(host, grpc.ssl_channel_credentials())
grpc.channel_ready_future(ch).result(timeout=10)

def call(path, payload):
    rpc = ch.unary_unary(
        path,
        request_serializer=lambda x: x,
        response_deserializer=lambda x: x,
    )
    response, _ = rpc.with_call(payload, timeout=15)
    return response

# SearchPlayer: field 2 = search_string
search = bytes([0x12, len(code)]) + code.encode()
resp = call("/lanota_services.Community/SearchPlayer", search)
print(resp.hex())

# GetPlayerSongRecord: field 1 = nano_id
record = bytes([0x0A, len(code)]) + code.encode()
resp = call("/lanota_services.Community/GetPlayerSongRecord", record)
print(resp.hex())
```

## 11. 安全与使用边界

- 本文档只用于理解 IPA 内已实现的网络接口，不应被用于攻击、绕过购买、篡改成绩或批量抓取用户隐私。
- 即使部分查询接口当前匿名可访问，也不代表接口无需鉴权；服务端随时可能收紧。
- 好友码属于公开标识，但玩家资料、回放、云存档等内容仍涉及个人数据，使用时应控制缓存、访问频率和保存范围。
- IPA 和 Portal 是两套不同接口体系：Portal 的 Firebase project 为 `lanota-67543202`，IPA 国服 App 的 Firebase project 为 `lanota-cn`。

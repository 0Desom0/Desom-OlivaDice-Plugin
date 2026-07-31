# Lanota 国服 Token 持续捕获与上传模块

这是一个 Magisk、KernelSU、APatch 通用模块，附带一个极简控制 App。模块不依赖 Termux、`curl`、`scp` 或 `sshpass`。

安装后 Root 守护程序会由 `service.sh` 自动拉起并持续捕获：先启用开发者调试通道，通过本机 `adbd` 以 ADB 同层的 `localabstract:` 服务连接 Chrome/WebView DevTools，订阅 `Network.requestWillBeSent` 并读取 Portal 的 `localStorage`；同时把 Chrome、Edge 和游戏 WebView 的 Local Storage LevelDB 文件扫描作为 Root 兜底。捕获到国服 Token 后自动验证并上传，控制 App 只用于查看状态或手动重新上传。

首次启用 ADB 调试通道时模块会把本机 `adbd` 切到 TCP 5555，USB 调试可能短暂断开，随后由模块自动重连。

Android 的静态 Go 守护程序可能无法直接使用系统 DNS，因此国服 `/api/me` 验证会自动降级为 `curl -4`，再降级为 `ping` 解析后直连，避免在手机上出现 `lookup ... on [::1]:53` 的解析失败。

日志只保留三类结果：已连接浏览器调试通道、已捕获并验证、上传成功/上传失败。守护程序日志写入：

```text
/data/adb/modules/lanota_china_token_uploader/logs/daemon.log
```

DevTools 会检查所有可调试页面，但只接受严格通过国服 JWT 与 `/portal/api/me` 验证的 Token。控制 App 新增“一键授权上传”：自动创建国服授权会话、唤醒 Lanota App，并在授权完成后自动捕获、验证和上传，不需要手动点“开始扫描”。

发现 JWT 后会执行四重检查：

1. JWT 算法必须为 `HS256`。
2. `iss` 必须严格等于 `lanota-portal`，因此不会上传国际服 Firebase Token。
3. `exp` 必须尚未过期。
4. 国服 `https://lanota.gmzon.com/portal/api/me` 必须返回 `200` 和有效 JSON。

验证成功后，模块通过固定服务器公钥指纹的 SFTP 上传到：

```text
C:/Users/Administrator/Desktop/OlivOS-2/plugin/data/LanotaPlugin/portal_auth_china.json
```

上传使用临时文件、回读校验和原子替换；旧文件保存为 `portal_auth_china.json.bak`。扫描阶段不连接 SSH，只有点击上传才会连接服务器。

## 源码结构

```text
LanotaChinaTokenUploaderModule/
├── module/                 # Root 模块脚本与 module.prop
├── src/                    # Go 原生守护程序源码和测试
├── config.example.conf     # 无密码的配置模板
├── config.local.conf       # 本机打包配置，已被 Git 忽略
├── build.ps1               # 测试、交叉编译及打包
└── dist/                   # 打包结果，已被 Git 忽略
```

## 打包

需要 Go 1.23 或更高版本。先复制配置模板：

```powershell
Copy-Item config.example.conf config.local.conf
notepad config.local.conf
```

填写 SSH 密码和实际服务器信息后运行：

```powershell
.\build.ps1
```

脚本会运行 Go 测试，并构建 Android 内核可直接运行的 CGO-free `linux/arm64` 和 `linux/armv7` 静态 ELF（分别对应 `arm64-v8a` 和 `armeabi-v7a`），然后生成：

```text
dist/LanotaChinaTokenUploader-v1.4.1-configured.zip
```

同时会生成可单独安装的 `dist/LanotaControl-v1.4.1.apk`。APK 必须和 Root 模块一起使用，本身不保存 SSH 密码或 Token。

配置文件和 configured ZIP 含 SSH 密码，均已被 `.gitignore` 排除，不要公开上传或转发。

## 安装和使用

1. 在 Magisk、KernelSU 或 APatch 的模块页面选择 configured ZIP 安装。
2. 安装器会尝试安装控制 App；如果管理器不允许在安装脚本中安装 APK，可手动安装 ZIP 中的 `app/LanotaControl.apk`。
3. 打开“Lanota 国服 Token 控制台”，授予 Root 权限。
4. 打开“Lanota 国服 Token 控制台”，授予 Root 权限。
5. 点“一键授权上传”，在 Lanota App 中确认授权；模块会自动获取 Token 并上传。
6. 可选：使用“开始扫描”手动连续监听，或点“上传 Token”重试上次待上传 Token。

在支持“执行模块操作”的管理器中，点击模块的“操作”按钮可查看状态。也可以用 Root 文件管理器读取：

```text
/data/adb/modules/lanota_china_token_uploader/state/state.json
```

服务器上的 OlivOS 插件会优先读取手机新上传的认证文件，不需要重启整个机器人。可通过 `.la china status` 验证。

## 安全说明

- 模块只连接本机可调试 WebView/浏览器的 DevTools socket；若直接连接受限，会改用本机 adbd 的 ADB 服务通道。不安装证书，也不解密或中间人拦截 HTTPS。
- 只接受 `lanota.gmzon.com` 请求或 Portal localStorage 中严格校验通过的国服 Token；不会显示或上传其他页面数据。
- SSH 主机公钥 SHA-256 指纹固定在配置中；服务器公钥变化时会拒绝上传。
- `config.conf` 安装权限为 `0600`，但 Root 用户仍能读取。丢失手机或泄露 ZIP 后应立即修改服务器密码。
- 如需停用，在模块管理器禁用或卸载该模块并重启。

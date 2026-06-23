# lockmac 详细使用教程

> macOS 隐私遮罩 + 锁定 + 死手开关。Telegram 远程控制。单机自包含。

---

## 0. 三个核心概念(先搞清)

| 概念 | 命令 | 特点 |
|---|---|---|
| **遮罩 veil** | `veil` / `unveil` | 盖屏防窥,**不锁机**;远程操作/截图照常;可解除 |
| **系统锁 lock** | `lock` | **真锁屏**(需 Mac 登录密码);单向,远程能锁不能解;默认**叠加遮罩**(双重) |
| **删目录 purge** | `purge` | 删你指定的目录(危险,有护栏) |

---

## 1. 安装(任选一种)

```bash
# A. Homebrew(发布后)
brew tap wwk5c5gh3/lockmac && brew install lockmac

# B. 双击 .pkg(新机器推荐,预编译、无需 Xcode)
./lockmac/packaging/build-pkg.sh        # 在有 swiftc 的机器生成
# 把 dist/lockmac-0.1.0.pkg 拷到目标机,双击安装

# C. 一键脚本
./lockmac/install.sh

# D. 开发用 pip
pip install -e lockmac                    # 需 swiftc (Xcode CLT)
```

> 遮罩用 Swift 编译,首次运行会编译一次(几秒)。`.pkg` 已预编译,目标机零编译。

---

## 2. 五分钟上手

```bash
lockmac setup            # 设遮罩解除密码 + 问是否开机自动遮罩
lockmac veil             # 开遮罩(屏幕变黑,别人看不到)
lockmac unveil           # 解除(输密码;启用2FA还要验证码)
lockmac status           # 查看状态
```

---

## 3. 本地命令全集

```bash
# 遮罩 / 锁定
lockmac veil                  # 开遮罩
lockmac unveil                # 解遮罩
lockmac lock                  # 系统真锁 + 叠加遮罩(双重);LOCKMAC_LOCK_NO_VEIL=1 只锁不遮
lockmac status                # 状态

# 密码 / 二步验证
lockmac setup                 # 首次:设密码 + 开机自启
lockmac passwd                # 改密码
lockmac setup-2fa             # 启用 TOTP 二步验证(出示二维码/密钥)
lockmac 2fa-off               # 关闭二步

# 死手开关 dead-man
lockmac deadman               # 查看当前配置
lockmac deadman <签到秒> <宽限秒> <lock|veil|purge> [失联秒]

# 删除清单
lockmac purge-add <绝对路径>   # 加入(危险路径拒绝)
lockmac purge-list            # 查看
lockmac purge-clear           # 清空
lockmac purge-now --yes       # 立即删除(需 --yes)

# 开机自启
lockmac install-agent         # 遮罩开机自启(LaunchAgent)
lockmac uninstall-agent
lockmac tg-install            # Telegram 监听开机自启 + 保活
lockmac tg-uninstall

# Telegram
lockmac tg-setup              # 绑定 bot(自动获取 chat id)
lockmac tg-test               # 发测试消息
lockmac tg-listen             # 前台跑监听(常驻用 tg-install)
```

---

## 4. Telegram 远程控制

### 4.1 绑定 bot
```bash
lockmac tg-setup
# 1. 粘贴 @BotFather 给的 token
# 2. 在 Telegram 给你的 bot 随便发一条消息
# 3. 回车,自动抓取 chat id 并注册 / 命令菜单
```

### 4.2 让监听常驻(关键!)
```bash
lockmac tg-install            # 装 LaunchAgent:开机自启 + 崩溃自动重启
```
> ⚠️ **只装程序不会自动监听**。必须 `tg-install`(或前台 `tg-listen`)才会响应命令。

### 4.3 在 Telegram 里用(7 个菜单命令)
```
/veil          开遮罩
/unveil        解遮罩(启用2FA: /unveil 123456)
/lock          系统真锁 + 遮罩
/status        状态
/deadman       配置死手开关(见下)
/purge         管理删除清单(见下)
/help          详细说明
```
菜单不显示?**完全退出 Telegram 重开**(客户端有缓存),或输入框打 `/` 触发。

---

## 5. 死手开关 dead-man(重点)

「人没响应」或「机器失联」时**自动执行**动作(锁/遮罩/删目录)。倒计时在**本地**跑,离线也生效。

### 三种触发(可同时,任一关=填 0)

| 触发 | 参数 | 含义 |
|---|---|---|
| 心跳无响应 | `签到秒` + `宽限秒` | 每隔签到秒发「✅我在」按钮;**宽限秒内不点 → 触发** |
| 失联超时 | `失联秒` | 连不上 Telegram 满 N 秒 → 触发(断网/失窃) |
| 手动 | — | `/lock` 等 |

### 配置例子(CLI 或 TG `/deadman` 都行,共享配置、即时生效)
```bash
lockmac deadman 1800 600 lock          # 每30min签到,10min不点→系统锁
lockmac deadman 0 0 purge 3600         # 不签到;连不上TG满1h→删目录
lockmac deadman 1800 600 veil 7200     # 签到 或 失联2h → 遮罩
lockmac deadman 0 0 lock 0             # 全关
```

### 怎么重置 / 验证
- 心跳来了点「✅ 我在」就重置计时
- 测试:`/deadman 0 50 lock`(50秒宽限),**不点**「我在」→ 50秒后应锁屏

> 💡 宽限要 > 一个签到间隔,否则你没机会点。失联秒要够长,避免正常断网误触发。

---

## 6. 删除清单 purge

### 加路径
```
TG:   /purge add /Users/你/Secret
CLI:  lockmac purge-add ~/Secret
```
- 必须**绝对路径**(`/` 或 `~/`)
- **拒绝**:`/`、家目录本身、`/System` `/Library` `/usr` 等系统树
- 只删你显式加入的目录

### 何时真正删除
- dead-man 动作设为 `purge` 且触发,或
- 手动 `lockmac purge-now --yes`

### 查看 / 清空
```
/purge list   /   /purge clear
lockmac purge-list  /  lockmac purge-clear
```

---

## 7. 二步验证 TOTP

```bash
lockmac setup-2fa             # 扫码加进 Google Authenticator 等
```
启用后:
- 本地 unveil:密码 + 6位码
- TG 解除:`/unveil 123456`(chat 白名单 + 验证码 双因素)

---

## 8. 典型场景

**离开座位防窥**:`lockmac veil`(或菜单 /veil),回来 unveil。

**笔记本可能被偷,人在场**:
```bash
lockmac deadman 600 300 lock   # 10min签到,5min不点就锁(+遮罩)
lockmac tg-install
```

**机器若被带离/断网就删敏感目录**:
```bash
lockmac purge-add ~/机密
lockmac deadman 0 0 purge 1800  # 失联30min→删目录
lockmac tg-install
```

---

## 9. 故障排查(实战踩坑)

| 现象 | 原因 / 解决 |
|---|---|
| **开机启动慢** | 新机器首次 swiftc 编译遮罩。装自启已自动预编译;或手动 `python3 -c "from lockmac import core; core.ensure_built()"`;或用 `.pkg`(预编译) |
| **bot 没有 / 菜单** | 没跑监听 → `lockmac tg-install`;已注册但不显示 → **重开 Telegram 客户端** |
| **命令不响应 / 回复异常** | 监听没在跑。`lockmac tg-install` 让它常驻 |
| **dead-man 心跳一直发但不锁屏** | 旧版 bug,已修(从「上次响应」计宽限)。更新到最新版 |
| **远程机器更新** | `.pkg` 装的需 `sudo installer` 重装;或改用 venv/pip --user 免 sudo 更新 |

---

## 10. 安全边界(诚实说明)

- 遮罩是**隐私屏不是安全锁**:Force-Quit / `ssh kill` / 重启都能消除遮罩。防肩窥,不防铁了心的人在键盘前。
- 系统锁 `lock` 是真锁(需登录密码),但**单向**——远程不能解。
- purge 是**真删除**,务必只加该删的目录。
- 整盘加密擦除(crypto-erase)需要 MDM,属后续阶段(见 `FLEET_DESIGN.md`)。

---

更多:`README.md` · 架构 `PHASE1.md` · 舰队设计 `PHASE2.md` / `FLEET_DESIGN.md`

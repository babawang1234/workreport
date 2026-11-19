# 汇报官 · 工作汇报智能 Agent（可在线售卖版）

把零散的工作碎片一键整理成可直接提交的日报 / 周报 / 月报。已内置 **在线售卖闭环**：用户打开网页 → 选套餐付款 → 系统自动发兑换码并激活 → 用兑换码在手机 / 电脑多端登录，次数与历史报告实时同步。

## 一、本地跑起来

```bash
pip install -r requirements.txt
cp .env.example .env      # Windows: copy .env.example .env
# 编辑 .env，至少填 LLM_API_KEY
streamlit run app.py
```

打开 `http://localhost:8501`。此时支付通道未配置，页面会自动降级为「联系客服购买」，不影响生成、微调、导出等功能。

### 更快的 Web 版（FastAPI，推荐日常使用）

Streamlit 每次点击都会整页重跑，公网免费版还会休眠冷启动。`webapp/` 是同一套核心逻辑的常规网站版本，页面局部刷新、首屏快：

```bash
pip install -r requirements.txt
python -m uvicorn webapp.main:app --port 8600   # 或双击 run_web.bat
```

打开 `http://localhost:8600`，用兑换码激活即可。功能包含：写汇报（流式输出）、多轮微调、我的报告（搜索/日期筛选/查看/删除/导出 Word）、购买次数（收款码 + 提交订单 + 订单号查码）。`core/` 下的提示词、模型、数据层与 Streamlit 版共用，数据完全一致。

部署到自己的服务器时，用 `uvicorn webapp.main:app --host 0.0.0.0 --port 8600`，前面套 Nginx/Caddy 反代即可。

一键部署到 Ubuntu 云服务器（Nginx + systemd + venv，自动读取本机 `.env` 写入服务端环境变量）：

```bash
python deploy/server/deploy.py --host 你的公网IP --password 服务器密码
```

脚本默认用 `ubuntu` 账号 + sudo（腾讯云轻量默认禁用 root 远程登录），装完访问 `http://你的IP/` 即可；重启服务器后服务自动恢复。

## 二、免费上线（零服务器：Streamlit Cloud + Neon）

不想买服务器、也不用在自己电脑上常开，走这条：**代码放 GitHub，网页托管交给 Streamlit 官方云（免费），数据放 Neon 免费 Postgres**。

### 1. 建免费数据库（Neon，约 3 分钟）

1. 打开 https://neon.com ，用 GitHub 账号登录 → `New Project`，区域选 **Singapore**（离国内最近）。
2. 在 Dashboard 复制 **Connection string**，形如：
   ```
   postgresql://user:pass@ep-xxx-pooler.ap-southeast-1.aws.neon.tech/neondb?sslmode=require
   ```
   ⚠️ 必须用带 `-pooler` 的地址，并发更稳。

### 2. 把代码推到 GitHub

```bash
git init
git add .
git commit -m "汇报官：工作汇报智能 Agent"
git branch -M main
git remote add origin https://github.com/你的用户名/workreport.git
git push -u origin main
```

`.env` 和 `data/app.db` 已被 `.gitignore` 排除，密钥不会进仓库。

### 3. 在 Streamlit Cloud 部署

1. 打开 https://share.streamlit.io ，用 GitHub 登录 → `Create app` → 选刚推的仓库，**Main file path** 填 `app.py`。
2. 点开 `Advanced settings` → `Secrets`，粘贴（TOML 格式，注意用双引号）：
   ```toml
   LLM_API_KEY = "sk-你的模型密钥"
   LLM_BASE_URL = "https://api.deepseek.com"
   LLM_MODEL = "deepseek-chat"
   ADMIN_USER = "admin"
   ADMIN_PASSWORD = "换成你的强密码"
   DATABASE_URL = "postgresql://...pooler...neondb?sslmode=require"
   SITE_URL = "https://你的应用名.streamlit.app"
   EPAY_URL = ""
   EPAY_PID = ""
   EPAY_KEY = ""
   ```
3. `Deploy`，等 2~3 分钟，得到 `https://xxx.streamlit.app` 公网链接 —— 手机、电脑直接打开即可。

> **零成本模型**：智谱开放平台的 Flash 系列目前免费额度较高（200K 上下文），OpenAI 兼容接口：
> `LLM_BASE_URL = "https://open.bigmodel.cn/api/paas/v4"`、`LLM_MODEL = "glm-4-flash"`。
> 实测 `glm-4-flash` 生成一份周报约 15~20 秒；同系列的推理模型（如 `glm-5.3-flash`）首字要等 4~5 分钟，
> 若必须用推理模型，需加 `LLM_MAX_TOKENS = "16384"`，否则推理过程会耗尽预算、正文为空。
> 免费模型有并发和速率限制，单量起来后建议换成付费模型（DeepSeek / 通义，成本仍然很低）。

### 4. 上线自检

- 运行 `streamlit run admin.py` → 生成一个测试码 → 激活 → 生成一份报告。
- 手机打开同一链接，输入同一个码，确认剩余次数和历史报告都在。
- 以后改代码：`git push` 即自动重新部署。

### 5. 免费版要知道的限制

| 项 | 情况 |
| --- | --- |
| 休眠 | 约 12 小时无人访问会休眠，首次打开等 10~20 秒 |
| 域名 | 只能是 `*.streamlit.app`，不能绑自己的域名 |
| 资源 | 1GB 内存，个人售卖足够；访问量大时会排队 |
| 数据库 | Neon 免费 0.5GB，够存上万条兑换码和报告 |

> 用户量起来后要自定义域名或更稳的响应，再迁到下面这套服务器方案，代码不用改（`DATABASE_URL` 可以继续用 Neon）。

## 三、正式上线（自有服务器，可选）

准备：一台云服务器（轻量应用服务器 2C2G 足够）、一个域名（解析到服务器 IP）。

```bash
# 服务器上
git clone <你的仓库> workreport && cd workreport
cp .env.example .env && vim .env      # 填模型密钥、SITE_URL=https://你的域名、DOMAIN=你的域名、ADMIN_USER、ADMIN_PASSWORD
docker compose up -d --build
```

`Caddy` 会自动申请并续期 HTTPS 证书，域名可直接访问。

> 这套方案数据落在 `./data`，重启不丢；如果数据想放到云库，填 `DATABASE_URL` 即可（和上面免费方案用的是同一个开关）。

## 四、开通在线收款

代码对接的是**易支付协议**（国内个人可申请，聚合了支付宝 / 微信）：

1. 注册一个易支付 / 虎皮椒 / 迅虎等平台，拿到 `商户ID（pid）`、`商户密钥（key）`、`接口地址`。
2. 填入 `.env`（Streamlit Cloud 则填到 Secrets 里）：
   ```bash
   EPAY_URL=https://pay.你的平台域名
   EPAY_PID=10001
   EPAY_KEY=你的密钥
   SITE_URL=https://你的域名
   ```
3. 重启服务。用户在「购买次数」页选套餐 → 跳收银台付款 → 页面每 8 秒自动查单，支付成功即自动发码并激活（**不依赖异步回调**，所以不需要公网 webhook）。

没有支付资质也能卖：配置客服文案 `SUPPORT_TEXT` 和客服微信 `SUPPORT_WECHAT`，用户下单后页面会显示「把订单号和付款截图发微信 xxx」，你在独立后台生成兑换码发给对方即可。

### 用支付宝个人收款码（无需商户号）

1. 支付宝 App → 收钱 → 保存收款码图片，放到 `assets/alipay_qr.png`（仓库里已有同名文件就直接替换它）。
2. 重启应用即生效，不用改配置。若想用图床链接，则在 Secrets 里加一行 `ALIPAY_QR = "https://你的图片地址.png"`（配置优先级高于本地图片）。
3. 用户在「购买次数」页会看到二维码：扫码付款 → 填备注/联系方式 → 提交订单，拿到订单号。
4. 你在独立后台（`admin.py`）的「订单管理」看到待支付订单和备注，核对到账后点「确认到账并发码」；用户凭订单号在购买页自助查询兑换码并激活。
5. 想让客服微信只在用户提交订单后才出现（避免公开手机号）：
   ```toml
   SUPPORT_TEXT = "付款遇到问题请联系客服"
   SUPPORT_WECHAT = "你的微信号"
   ```
   用户提交订单拿到订单号后，页面才显示「把订单号和付款截图发微信 xxx」。


## 五、日常运营（独立后台）

管理员后台是独立应用 [admin.py](admin.py)，只在管理员登录后可见，普通用户页面没有任何入口。

本地启动：

```bash
streamlit run admin.py
```

输入 `ADMIN_USER` / `ADMIN_PASSWORD` 登录。想在手机上随时看营收，可在 Streamlit Cloud 再建一个 App（Main file 选 `admin.py`），Secrets 填同样的 `DATABASE_URL`、`ADMIN_USER`、`ADMIN_PASSWORD`；这个链接只自己保存，不要放到用户页面上。

| 功能 | 用途 |
| --- | --- |
| 经营看板 | 今日/累计收入与成交、待发码提醒、今日生成量、剩余可用次数 |
| 订单管理 | 订单搜索、状态筛选、CSV 导出、手动补单发码 |
| 兑换码 | 批量生成、加次数、停用违规码、导出记录 |
| 运营记录 | 下单、发码、激活、生成等关键动作日志，可导出 |

## 六、多端同步是怎么实现的

- **兑换码即账号**：数据都以兑换码为 key 存在服务端数据库（本地 SQLite 或云 Postgres）。
- 用户在手机输入同一个兑换码，就能看到同样的剩余次数和全部历史报告，可继续微调、导出。
- 报告自动存云端（每份只存最新版本 + 版本栈），在「我的报告」里可随时删除。

## 七、套餐与定价

套餐在 [core/payments.py](core/payments.py) 的 `PLANS` 里改，单位是**分**：

```python
{"id": "standard", "name": "标准版", "price": 2900, "uses": 40, "desc": "...", "badge": "最受欢迎"}
```

当前档位：¥9.9/10 次、¥29/40 次、¥69/120 次、¥199/400 次。

成本参考：一次生成约 1.5k 输入 + 1k 输出 token，按 deepseek-chat 价格单次成本约 1~2 分钱，毛利率 90% 以上。「微调不扣次」是卖点，默认单份最多 20 轮。

## 八、配置项

| 变量 | 说明 | 默认 |
| --- | --- | --- |
| `LLM_API_KEY / LLM_BASE_URL / LLM_MODEL` | 模型接入（OpenAI 兼容） | `deepseek-chat` |
| `LLM_TEMPERATURE / LLM_MAX_TOKENS` | 输出风格与长度上限（`glm-4-flash` 用 2400~4096 即可；推理模型如 glm-5.3-flash 需 16384，预算被推理耗尽时会自动用 16384 重试一次） | `0.5 / 2400` |
| `DATABASE_URL` | 云 Postgres 连接串；留空则用本地 SQLite | 空 |
| `SITE_URL` | 站点公网地址（支付回跳） | `http://localhost:8501` |
| `EPAY_URL / EPAY_PID / EPAY_KEY` | 在线支付，留空则关闭 | — |
| `ADMIN_USER` | 管理员账号（独立后台登录用） | `admin` |
| `ADMIN_PASSWORD` | 后台密码，**上线必改** | `admin888` |
| `MAX_REFINES` | 单份报告微调上限 | `20` |
| `SUPPORT_TEXT` | 客服/购买引导文案（公开显示，建议不含手机号） | — |
| `SUPPORT_WECHAT` | 客服微信号，仅在用户提交订单后显示 | 空 |
| `TRIAL_USES` | 未激活用户的免费试用次数（按浏览器标识计，试用报告不保存） | `2` |

## 九、目录结构

```
app.py                 # 用户端：售卖 / 激活 / 生成 / 报告历史
admin.py               # 管理员独立后台：营收 / 订单 / 兑换码 / 日志
tools/ops_report.py    # 命令行经营巡检（可选，配合定时任务）
core/prompts.py        # 13 个岗位模板 + 汇报结构（调优就改这里）
core/payments.py       # 套餐 + 易支付对接（查单发码）
core/store.py          # 兑换码 / 订单 / 云端报告
core/db.py             # 数据库适配（SQLite / Postgres 自动切换）
core/llm.py            # 模型流式调用
core/exporter.py       # Word / Markdown / 纯文本导出
docker-compose.yml     # 自有服务器一键部署（含 Caddy 自动 HTTPS）
```

## 十、上线检查清单

- [ ] `ADMIN_USER` / `ADMIN_PASSWORD` 已设置为自己的账号密码
- [ ] `SITE_URL` 是实际公网地址（否则支付回跳会失真）
- [ ] 云端部署时 `DATABASE_URL` 已填（免费云磁盘是临时的，不填会丢码）
- [ ] `.env` 与 `data/app.db` 未提交到公开仓库（`.gitignore` 已处理）
- [ ] 支付完成后在 `admin.py` 的「订单管理」确认能看到订单与收入
- [ ] 用户端侧边栏没有管理入口（后台为独立应用）
- [ ] 用手机打开链接，走一遍「购买 → 输入兑换码 → 生成」全流程

# 外贸订单助手（询盘分级 · 一键报价 · 每日跟进）

给外贸中小工厂用的 AI 助手。一个工厂部署一套，老板和业务员用浏览器登录（电脑、手机都能用）。

## 快速开始：网页系统（推荐，默认模式）

```bash
cp .env.example .env      # 至少填 ADMIN_PASSWORD
docker compose up -d --build
docker compose exec waimao-assistant python scripts/seed_demo.py products   # 可选：写入演示产品
```

打开 `http://服务器IP:8080/app`，用 `ADMIN_USERNAME` / `ADMIN_PASSWORD` 登录（没填密码的话，初始密码在 `docker compose logs` 里）。
然后进「设置」：
- **AI 大模型**：选服务商（DeepSeek / 通义千问 / 其他 OpenAI 兼容接口），填密钥，点「测试连接」，通过后保存，立即生效。
- **飞书群推送**（可选）：粘贴群机器人 Webhook，点「发送测试消息」，保存。

密钥保存在服务器自己的数据库里，页面只显示掩码，只有管理员能改。
`http://服务器IP:8080/` 是公开的产品展示页。

| 页面 | 能做什么 |
|---|---|
| 工作台 | 今日待跟进（附 AI 话术，一键复制、标记已跟进）、待报价、等级分布、客户状态、最新询盘 |
| 询盘客户 | 按状态 / 等级 / 关键词 / 只看我的 / 今日待跟进筛选；点开客户：AI 摘要、一键生成 PDF 报价单和报价邮件、AI 写跟进话术、改下次跟进日期、记沟通记录、编辑信息 |
| 录入询盘 | 粘贴阿里国际站、WhatsApp、展会的询盘原文，AI 提取并分级（邮箱询盘自动收取） |
| 产品库 | 增删改型号、单价、起订量、交期；CSV 批量导入 |
| 报价记录 | 所有报价单，随时查看和下载 PDF |
| 提醒 | 站内保存的每日跟进清单和 A 级询盘提醒（配了飞书群机器人会同时推送） |
| 设置 | AI 大模型（带测试连接）、飞书群推送（带测试消息）、公司信息、报价条款、银行信息、推送时间（仅管理员可改） |
| 成员 | 新增业务员、重置密码、停用、设管理员（仅管理员） |

- 数据存在 `data/waimao.db`（SQLite）和 `data/files/`（报价单 PDF），**备份这个 `data` 目录即可**。
- 角色：管理员可以改设置、管成员、删客户；业务员处理询盘、报价、跟进、维护产品。
- 安全：密码用 PBKDF2 加盐存储；登录 Cookie 为 HttpOnly + SameSite；登录失败 10 次锁 10 分钟。对公网开放时请在前面加 Nginx + HTTPS，并设置 `COOKIE_SECURE=true`。

下面第一到三节是**飞书多维表格模式**（`STORAGE=feishu`，旧版：把飞书表格当数据库和界面）的说明；网页系统模式不需要建飞书应用，只有想把提醒推到飞书群时才需要添加一个群机器人。

---

| 功能 | 业务员看到的效果 |
|---|---|
| ① 询盘自动入库和分级 | 邮箱来了新询盘，1–2 分钟后客户表里自动多一行：公司、国家、产品、数量、目标价、AI 摘要、**A/B/C 意向等级**。推广和垃圾邮件自动过滤。A 级询盘立刻推送到飞书群。 |
| ② 粘贴录入 | 阿里国际站、WhatsApp、展会的询盘，打开一个网页粘贴原文，AI 照样整理入表。 |
| ③ 一键生成报价单 | 在表格里勾选「生成报价单」，几秒后自动生成英文 PDF 报价单（按产品库价格、自动套起订量），附件写回表格，同时写好一封英文报价邮件草稿。 |
| ④ 每日跟进提醒 | 每天早上 9 点，飞书群收到“今天要跟进谁”：按等级排序，每个客户附一段 AI 写好的英文跟进话术。跟进 5 次没回复的提示止损。 |
| ⑤ 记录跟进 | 跟进完勾选「已跟进」，系统自动记录并排好下次跟进时间（A 级 2/3/5/7/10 天，B 级、C 级更稀疏）。 |

```
业务邮箱(IMAP) ──┐
粘贴网页 ────────┼──> 本服务（Python）──> 大模型（DeepSeek/通义等）
                 │        │  生成 PDF 报价单
                 │        └──> 飞书多维表格（4 张表）<── 业务员勾选
                 └──────────> 飞书群机器人（A级询盘提醒 / 每日跟进卡片）
```

- 纯 Python，依赖只有 `requests`、`reportlab`、`python-dotenv`。
- 勾选触发靠后台每 30 秒检查一次表格，**不需要在飞书里配置自动化流程**。
- 没配大模型 Key 时自动使用“规则版 mock”，可以先跑通流程录演示，正式用请换真模型。

---

## 一、飞书模式准备工作（约 30 分钟，网页系统模式可跳过）

### 1. 创建飞书自建应用
1. 打开 [飞书开放平台](https://open.feishu.cn/app) → **创建企业自建应用**，名字可以叫“外贸AI助手”。
2. 在「凭证与基础信息」里复制 **App ID** 和 **App Secret**。
3. 在「权限管理」里搜索并开通：**查看、评论、编辑和管理多维表格**（`bitable:app`）。
4. 在「版本管理与发布」里创建版本并发布（需要企业管理员审核；个人版飞书自己就是管理员）。

### 2. 新建多维表格并授权给应用
1. 在飞书**云文档**里新建一个多维表格（不要建在知识库里，知识库的链接格式不同）。
2. 多维表格右上角 `…` → **更多** → **添加文档应用** → 选择刚才的应用，权限选 **可编辑**。
3. 复制浏览器地址栏的链接：`https://xxx.feishu.cn/base/【这一段】?table=...`，中间那段就是 **BITABLE_APP_TOKEN**。

> 如果后面运行脚本报“无权限”，几乎都是这一步没做，或者应用还没发布。

### 3. 添加群机器人
在要接收提醒的飞书群：**设置 → 群机器人 → 添加机器人 → 自定义机器人**，复制 webhook 地址。如果勾选了“签名校验”，把密钥也复制下来。

### 4. 准备大模型 API Key
任何 OpenAI 兼容接口都可以，推荐国内直接能用的：
- DeepSeek（推荐）：`LLM_BASE_URL=https://api.deepseek.com`，`LLM_MODEL=deepseek-v4-flash`（旧名 deepseek-chat 已于 2026-07-24 弃用）
- 通义千问：`LLM_BASE_URL` 从阿里云百炼控制台复制（不同地域地址不同），`LLM_MODEL=qwen-plus`

### 5.（可选）业务邮箱开启 IMAP
在企业邮箱设置里开启 IMAP，并生成**客户端专用密码/授权码**。常见服务器：
网易企业邮 `imaphz.qiye.163.com`、腾讯企业邮 `imap.exmail.qq.com`、阿里企业邮 `imap.qiye.aliyun.com`、Gmail `imap.gmail.com`。
程序只读邮件，**不会把邮件标成已读，也不会发邮件**。

---

## 二、部署

### 方式 A：Docker（推荐）
```bash
cp .env.example .env          # 按注释填写
docker compose up -d --build
# 一键建表 + 写入演示产品库
docker compose exec waimao-assistant python scripts/setup_feishu.py --demo
# 自检：逐项检查飞书、表格、大模型、邮箱、群机器人
docker compose exec waimao-assistant python scripts/doctor.py
docker compose logs -f        # 看运行日志
```

### 方式 B：直接用 Python（3.10+）
```bash
pip install -r requirements.txt
cp .env.example .env
python scripts/setup_feishu.py --demo
python scripts/doctor.py
python -m app.main            # 长期运行建议用 systemd / supervisor / screen
```

启动后：
- 产品展示页：`http://服务器IP:8080/`（公开页面，带动画演示，可用来给客户看或录屏；按钮文字用 `.env` 的 `LANDING_CONTACT` 改）
- 粘贴询盘页面：`http://服务器IP:8080/paste?token=你的API_TOKEN`（建议手机上收藏）
- 健康检查：`http://服务器IP:8080/health`

> 服务器只需要能访问外网（飞书、大模型、邮箱）。只有粘贴页面需要对外开放 8080 端口；
> 正式给客户用时建议用 Nginx 加 HTTPS。

---

## 三、日常使用（给业务员的说明）

1. **维护产品库**：在「产品库」表填写型号、名称、规格、单价、起订量、交期、包装。AI 报价只会用这里的型号和价格。
   也可以批量导入：`python scripts/setup_feishu.py --products 你的产品.csv`（格式同 `demo/products.csv`）。
2. **新询盘**会自动出现在「询盘客户」表，状态是“新询盘”。先看 A 级。
3. **报价**：勾选「生成报价单」→ 等几秒 → 「报价单」字段出现 PDF，「报价邮件草稿」里有写好的英文邮件。检查无误后自己发给客户。
4. **跟进**：每天早上看群里的提醒卡片，复制话术发给客户（邮件或 WhatsApp），然后在表格里勾选「已跟进」。
5. **客户有回复了**：把状态改成“已寄样”或“已成交”，系统就不会再提醒；也可以把聊天记录粘到「沟通记录」，下次 AI 写话术会参考。

### 建议在飞书里手动建几个视图（2 分钟）
- **今日待跟进**：筛选「下次跟进日期」≤ 今天，且「状态」是“已报价”或“跟进中”，按「意向等级」排序。
- **待报价**：筛选「状态」= 新询盘，按「意向等级」分组。
- **看板**：按「状态」分组的看板视图，适合老板看全局。
- **仪表盘**：询盘数量（按周）、等级占比、各状态数量。

---

## 四、调试和演示用的命令

```bash
python scripts/render_sample_quote.py   # 不连飞书，生成一份样例报价单，调样式用
python scripts/seed_demo.py emails      # 把 5 封演示邮件交给 AI 处理（含 1 封垃圾邮件）
python scripts/seed_demo.py whatsapp    # 模拟粘贴一条 WhatsApp 询盘
python scripts/seed_demo.py history     # 写入 3 个“今天该跟进”的演示客户
python scripts/run_once.py mail         # 立即收一次邮件
python scripts/run_once.py check        # 立即处理勾选
python scripts/run_once.py daily        # 立即推送今天的跟进提醒（录屏时用）
python -m pytest -q                     # 运行测试（不需要联网）
```

可以给飞书自动化或其他系统调用的接口（请求头带 `X-Token: API_TOKEN`）：
`POST /hooks/quote {"record_id":"rec..."}`、`POST /hooks/followed`、`POST /hooks/daily`、`POST /hooks/check-mail`、`POST /api/inquiry`。

---

## 五、给不同工厂定制

| 想改什么 | 改哪里 |
|---|---|
| 报价单抬头、条款、银行信息、Logo | `.env` 里的 `COMPANY_*`、`QUOTE_*` |
| 报价单样式 | `app/quote_pdf.py` |
| 分级标准、报价邮件和跟进话术的写法 | `app/prompts.py`（中文写的，直接改） |
| 跟进间隔天数、最多跟进几次 | `app/pipeline.py` 顶部的 `CADENCE`、`MAX_FOLLOWUPS` |
| 表格字段 | `app/schema.py`，改完再运行一次 `setup_feishu.py` 会自动补字段 |

## 六、常见问题

- **勾选后没反应**：看日志 `docker compose logs -f`。失败时程序会自动取消勾选，并把错误写在「报价邮件草稿」字段里。
- **报价单里没有某个产品**：AI 只会用产品库里的型号。检查「询盘产品」字段写的内容，或在产品库补充型号。
- **收不到邮件**：运行 `doctor.py`；网易、QQ 邮箱必须用授权码，并在网页设置里开启 IMAP。
- **群里没有提醒**：确认 `FEISHU_BOT_WEBHOOK` 正确；开启了签名校验的话 `FEISHU_BOT_SECRET` 也要填。
- **数据安全**：客户数据只存在客户自己的飞书和邮箱里；本服务只在 `data/` 下保存生成的 PDF 和已处理邮件的 ID。

## 目录结构
```
app/            核心代码（config / feishu / llm / prompts / mailbox / pipeline / quote_pdf / server / worker）
app/db.py       自带数据库（SQLite）：客户记录、报价文件、提醒、设置、成员与登录
app/web.py      网页系统的 JSON 接口
app/static/     产品展示页 index.html；网页系统 app/（原生 JS，无需构建）
scripts/        建表、自检、演示数据、手动触发
demo/           演示产品库和演示询盘（客户名都带 Demo）
tests/          测试（含一个本地假飞书服务器，用于联调）
docs/           录制素材清单
```

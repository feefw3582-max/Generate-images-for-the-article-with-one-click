# 知乎智能配图助手 · Zhihu Image Assistant

一句话：把一段知乎草稿变成**带插图位的完整文稿 + 每张配图的 AI 提示词**，再用 Seedream 5.0 Lite 自动生成配图并回填成稿。

产品包含两种形态：

| 形态 | 位置 | 说明 |
|---|---|---|
| 🖥️ 本地交互原型 | `app.py` `/` | Flask 网页应用，分析完成即默认自动生成一轮配图，直连 DeepSeek + Seedream |
| 📱 移动端手机原型 | `app.py` `/proto` | 纯手机屏幕形态（输入标题+正文→AI 配图），**同样直连真实 DeepSeek + Seedream**，读取 `../mobile-proto/index.html` |
| 🔄 Dify 工作流 DSL | `dify/zhihu_image_chatflow_v5.yml` | 可导入 Dify 的 Chatflow，同样逻辑跑在 Dify 上 |

## 功能流程

```
输入文字形式（文章/回答/想法） + 草稿
   │  DeepSeek 分析
   ▼
  ① 带插图位的完整文稿（占位格式：【为大大推荐在这里插入一张xx的图片哦～】）
  ② 每张配图卡片（画面描述 + 英文生图提示词）

插图数量限制：**每篇内容强制 2-5 张**
   - 提示词层面约束模型按 2-5 处规划插图位；
   - 程序层面另有「限制节点」兜底：超出 5 张自动截断（并移除文稿中多余占位符），不足 2 张自动在文稿末尾补足。

配图工作流（新）：**默认 AI 先自动生成一次**
   - 分析完成 → 每张卡片自动逐张调用 Seedream 生成配图；
   - 生成中：卡片显示「图片生成中…」loading 占位（弹跳点动画），
     底部「上传图片 / 重新生图」按钮灰掉不可点；
   - 生成完成：成图自动替换 loading 占位图，按钮恢复可用，
     可对单张「重新生图」或「上传图片」替换；
   - 配好任意几张后点击「插入 N 张配图到文稿」，按插图位 id 回填成稿
     （未配图的占位符原样保留）。
```

## 快速开始（本地）

```bash
pip install -r requirements.txt
python app.py
```

打开 <http://127.0.0.1:5000>，**无需手动填 Key** —— 程序自动读取项目根目录 `.env` 文件（不存在时退回环境变量）。

移动端手机原型（纯手机屏幕、输入自己的文章）：打开 <http://127.0.0.1:5000/proto>。
注意：`/proto` 读取的是仓库同级目录 `mobile-proto/index.html`，两个目录需一起部署。

### 配置（`.env` 文件）

在项目根目录创建 `.env`（**已被 .gitignore 排除，不会提交到 GitHub**）：

```bash
DEEPSEEK_API_KEY=你的DeepSeekKey
SEEDREAM_API_KEY=你的SeedreamKey
```

环境变量会覆盖 `.env`，变量说明：

| 变量 | 默认值 | 说明 |
|---|---|---|
| `DEEPSEEK_API_KEY` | 必填（.env 或环境变量） | DeepSeek API Key |
| `DEEPSEEK_URL` | `https://api.deepseek.com/v1/chat/completions` | 可换其他 OpenAI 兼容端点 |
| `DEEPSEEK_MODEL` | `deepseek-chat` | 模型名 |
| `SEEDREAM_API_KEY` | 必填（.env 或环境变量） | 火山方舟 API Key |
| `SEEDREAM_URL` | `https://ark.cn-beijing.volces.com/api/v3/images/generations` | 可换其他兼容端点 |
| `SEEDREAM_MODEL` | `doubao-seedream-5-0-260128` | Seedream 5.0 Lite 模型 ID |
| `SEEDREAM_SIZE` | `1920x1920` | 生图尺寸（**5.0 Lite 要求 ≥3686400 像素，1024×1024 会报错**） |

> Key 只存本机 `.env`，不进入任何提交文件，请勿把真实 Key 提交到 GitHub。

## 本地 API

| 接口 | 方法 | 说明 |
|---|---|---|
| `/api/analyze` | POST | 分析草稿，返回带占位符文稿 + 插图位列表（2-5 张） |
| `/api/generate_one` | POST | 对单个插图位调 Seedream 生成，body: `{session_id, id}` |
| `/api/upload_one` | POST | 单卡上传本地图片，form: `session_id / id / image` |
| `/api/finalize` | POST | 按插图位 id 回填成稿，body: `{session_id, images: {id: url}}` |
| `/api/generate` `/api/upload` `/api/debug` | POST | 旧批量接口，保留兼容 |

## Dify 部署方式

1. Dify 中新建应用 → 导入 DSL → 选择 `dify/zhihu_image_chatflow_v5.yml`
2. 导入后在「内容分析与插图规划」LLM 节点重新选择你自己的 DeepSeek 模型
3. 在「设置 → 环境变量」配置 `seedream_api_key`
4. 若 Seedream 节点报像素不足，确认请求体中的 `size` 为 `1920x1920`

## 调试暗号 `charli`

第二轮发送 `charli`（大小写均可、可嵌在句子里）：

- 不调用生图 API、不读取上传文件
- 直接读取会话中保存的文稿，把每个占位符替换成 `🖼️【调试占位图片 N：类型·位置】` 标记
- 输出替换后文稿 + 调试日志（占位符数 vs 插图位数比对）

用途：快速验证「分析 → 会话变量保存 → 路由分发 → 占位符替换」整条前置链路是否正常，真实生图/上传分支只是换了图片来源。

## 目录结构

```
zhihu-image-assistant/
├── app.py                 # Flask 应用（本地原型）
├── templates/index.html   # 前端交互页
├── dify/                  # Dify DSL 文件
│   └── zhihu_image_chatflow_v5.yml
├── requirements.txt
└── .gitignore
```

# 知乎智能配图助手 · Zhihu Image Assistant

一句话：把一段知乎草稿变成**带插图位的完整文稿 + 每张配图的 AI 提示词**，再用 Seedream 5.0 Lite 一键生成配图并回填成稿。

产品包含两种形态：

| 形态 | 位置 | 说明 |
|---|---|---|
| 🖥️ 本地交互原型 | `app.py` | Flask 网页应用，两轮对话式交互，直连 DeepSeek + Seedream |
| 🔄 Dify 工作流 DSL | `dify/zhihu_image_chatflow_v5.yml` | 可导入 Dify 的 Chatflow，同样逻辑跑在 Dify 上 |

## 功能流程

```
第一轮：输入文字形式（文章/回答/想法） + 草稿
   │  DeepSeek 分析
   ▼
  ① 带插图位的完整文稿（占位格式：【为大大推荐在这里插入一张xx的图片哦～】）
  ② 每个插图位的生图提示词卡片（弹窗展示）

第二轮：三选一
   ├─ 自动生图 → Seedream 5.0 Lite 批量生成 1920×1920 配图
   ├─ 上传图片 → 用自己的图
   └─ charli   → 调试暗号：不调 API，直接用调试标记替换占位符，
                  用于验证「分析 → 保存 → 路由 → 替换」链路是否正常
   │
   ▼
  最终成稿（占位符全部替换为图片）
```

## 快速开始（本地）

```bash
pip install -r requirements.txt
python app.py
```

打开 <http://127.0.0.1:5000>，**无需手动填 Key** —— 程序自动读取项目根目录 `.env` 文件（不存在时退回环境变量）。

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

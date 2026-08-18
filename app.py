"""
知乎智能配图助手 · 本地交互原型
运行方式：
  DEEPSEEK_API_KEY=xxx SEEDREAM_API_KEY=yyy python app.py
  打开 http://127.0.0.1:5000

功能：
  1. 第一轮输入文字形式 + 草稿，调用 DeepSeek 输出带占位符的文稿和插图位提示词。
  2. 第二轮三选一：自动生图 / 上传图片 / 发送 charli 调试暗号，替换占位符后输出成稿。
"""
import os
import re
import json
import uuid
import base64
from pathlib import Path
from datetime import datetime

import requests
from flask import Flask, render_template, request, jsonify, send_from_directory

app = Flask(__name__)

# 本地静态资源
UPLOAD_DIR = Path(__file__).parent / 'uploads'
UPLOAD_DIR.mkdir(exist_ok=True)

# 会话状态存储（内存级，重启丢失）
states = {}


def _load_env_file():
    """从本地 .env 读取配置（key 只存本机，不进版本控制）。
    支持 KEY=VALUE / 带引号 / 空行与 # 注释；环境变量优先级更高。"""
    env_path = Path(__file__).parent / '.env'
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding='utf-8').splitlines():
        line = line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        key, _, value = line.partition('=')
        key, value = key.strip(), value.strip().strip('"').strip("'")
        if key:
            os.environ.setdefault(key, value)


_load_env_file()

DEEPSEEK_URL = os.environ.get('DEEPSEEK_URL', 'https://api.deepseek.com/v1/chat/completions')
DEEPSEEK_MODEL = os.environ.get('DEEPSEEK_MODEL', 'deepseek-chat')
SEEDREAM_URL = os.environ.get('SEEDREAM_URL', 'https://ark.cn-beijing.volces.com/api/v3/images/generations')
SEEDREAM_MODEL = os.environ.get('SEEDREAM_MODEL', 'doubao-seedream-5-0-260128')


SYSTEM_PROMPT = """你是知乎内容配图专家。用户会输入：
1. 文字形式：文章 / 回答 / 想法
2. 原始文字草稿

你的任务是：
A. 判断文字形式，并基于草稿重写/润色成一篇「带插图位的完整文稿」。插图占位符必须严格使用如下格式（独占一行）：

【为大大推荐在这里插入一张{具体画面描述}的图片哦～】

「具体画面描述」必须是结合文章语境写出的、有主谓宾结构的画面描述，而不是"插画/摄影"这种抽象类型。要交代清楚：什么人物/事物 + 什么动作或状态 + 什么风格/氛围，让读者一眼看到画面。例如：
- 聊三国演义 → 【为大大推荐在这里插入一张三国杀风格的曹植的图片哦～】
- 聊红楼梦 → 【为大大推荐在这里插入一张唯美凄凉的林黛玉自尽的图片哦～】
- 聊植物学 → 【为大大推荐在这里插入一张高清画质的兰花显微结构的图片哦～】
- 聊旅行 → 【为大大推荐在这里插入一张清晨薄雾中无人的古镇石桥的图片哦～】

B. 列出每个插图位，输出一个 JSON 数组。每个元素包含字段：
- id: 插图位序号（从 1 开始）
- image_type: 该插图位的「具体画面描述」（与文稿占位符中的文字一致，主谓宾结构，如"三国杀风格的曹植"，不得是"插画/摄影"等抽象类型）
- position_hint: 在文稿中大致位置描述
- prompt: 给 Seedream 5.0 Lite 使用的英文生图提示词（基于 image_type 扩写成详细、高质量的画面描述，包含风格、光线、构图等）

最终输出格式必须如下（除 JSON 外不要有其他 Markdown 代码块，JSON 用 ```json ... ``` 包裹）：

---ARTICLE_START---
（带占位符的完整文稿）
---ARTICLE_END---

```json
[
  {"id": 1, "image_type": "...", "position_hint": "...", "prompt": "..."}
]
```
"""


def _call_deepseek(messages, api_key):
    headers = {'Authorization': f'Bearer {api_key}', 'Content-Type': 'application/json'}
    payload = {
        'model': DEEPSEEK_MODEL,
        'messages': messages,
        'temperature': 0.7,
    }
    r = requests.post(DEEPSEEK_URL, headers=headers, json=payload, timeout=120)
    r.raise_for_status()
    return r.json()['choices'][0]['message']['content']


def _parse_llm_output(text):
    article_match = re.search(r'---ARTICLE_START---\s*(.*?)\s*---ARTICLE_END---', text, re.S)
    article = article_match.group(1).strip() if article_match else text.strip()

    json_match = re.search(r'```json\s*(.*?)\s*```', text, re.S)
    insertions = []
    if json_match:
        try:
            insertions = json.loads(json_match.group(1))
            if not isinstance(insertions, list):
                insertions = []
        except Exception:
            insertions = []

    # 如果没找到 JSON 但有占位符，兜底构造 insertions
    if not insertions:
        pattern = re.compile(r'【为大大推荐在这里插入一张([^】]*)的图片哦～】')
        for i, m in enumerate(pattern.finditer(article), 1):
            insertions.append({
                'id': i,
                'image_type': (m.group(1) or '配图').strip(),
                'position_hint': f'第 {i} 处占位符',
                'prompt': f'High quality image of {m.group(1) or "the described scene"}, detailed, well-composed, suitable for a Zhihu article',
            })

    return article, insertions


def _generate_image(prompt, api_key, size='1920x1920'):
    headers = {'Authorization': f'Bearer {api_key}', 'Content-Type': 'application/json'}
    payload = {
        'model': SEEDREAM_MODEL,
        'prompt': prompt,
        'n': 1,
        'size': size,
    }
    r = requests.post(SEEDREAM_URL, headers=headers, json=payload, timeout=120)
    r.raise_for_status()
    data = r.json()
    if data.get('data') and len(data['data']) > 0:
        return data['data'][0].get('url') or data['data'][0].get('b64_json')
    raise RuntimeError(f'Seedream 未返回图片: {data}')


def _replace_placeholders(article, insertions, image_urls_or_paths):
    pattern = re.compile(r'\n*\s*【为大大推荐在这里插入一张([^】]*)的图片哦～】\s*\n*')
    parts = []
    pos = 0
    idx = 0
    logs = []
    for m in pattern.finditer(article):
        parts.append(article[pos:m.start()])
        img_type = (m.group(1) or '未知类型').strip()
        if idx < len(image_urls_or_paths):
            src = image_urls_or_paths[idx]
            # 本地文件用相对 URL
            if src.startswith('/uploads/'):
                tag = f'![插图{idx+1}]({src})'
            elif src.startswith('data:'):
                tag = f'<img src="{src}" alt="插图{idx+1}" style="max-width:100%;" />'
            else:
                tag = f'![插图{idx+1}]({src})'
            parts.append(f'\n\n{tag}\n\n')
            logs.append(f'占位符 {idx+1}（{img_type}）→ 已替换。')
        else:
            parts.append(article[m.start():m.end()])
            logs.append(f'占位符 {idx+1}（{img_type}）→ 缺少图片，保留原占位符。')
        pos = m.end()
        idx += 1
    parts.append(article[pos:])
    return ''.join(parts), logs


def _debug_replace(article, insertions):
    pattern = re.compile(r'\n*\s*【为大大推荐在这里插入一张([^】]*)的图片哦～】\s*\n*')
    parts = []
    pos = 0
    idx = 0
    logs = []
    for m in pattern.finditer(article):
        parts.append(article[pos:m.start()])
        img_type = (m.group(1) or '未知类型').strip()
        hint = ''
        if idx < len(insertions) and isinstance(insertions[idx], dict):
            hint = str(insertions[idx].get('position_hint', '') or '')
        label = f'🖼️【调试占位图片 {idx+1}：{img_type}' + (f'·{hint}' if hint else '') + '】'
        parts.append(f'\n\n{label}\n\n')
        logs.append(f'占位符 {idx+1}（{img_type}）→ 已替换为调试标记。')
        pos = m.end()
        idx += 1
    parts.append(article[pos:])
    if idx == 0:
        logs.append('⚠️ 未在文稿中找到任何占位符！')
    if idx != len(insertions):
        logs.append(f'⚠️ 占位符数量（{idx}）与插图位数量（{len(insertions)}）不一致。')
    else:
        logs.append(f'✅ 占位符数量与插图位数量一致（{idx} 处）。')
    return ''.join(parts), logs


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/api/analyze', methods=['POST'])
def api_analyze():
    data = request.json
    form = data.get('form', '').strip()
    draft = data.get('draft', '').strip()
    api_key = data.get('deepseek_key', '').strip() or os.environ.get('DEEPSEEK_API_KEY', '')
    if not api_key:
        return jsonify({'error': '缺少 DeepSeek API Key'}), 400

    user_msg = f'文字形式：{form}\n\n原始草稿：\n{draft}'
    content = _call_deepseek([{'role': 'system', 'content': SYSTEM_PROMPT},
                               {'role': 'user', 'content': user_msg}], api_key)
    article, insertions = _parse_llm_output(content)

    sid = str(uuid.uuid4())
    states[sid] = {
        'article': article,
        'insertions': insertions,
        'created_at': datetime.now().isoformat(),
    }
    return jsonify({'session_id': sid, 'article': article, 'insertions': insertions})


@app.route('/api/generate', methods=['POST'])
def api_generate():
    data = request.json
    sid = data.get('session_id')
    api_key = data.get('seedream_key', '').strip() or os.environ.get('SEEDREAM_API_KEY', '')
    if not api_key:
        return jsonify({'error': '缺少 Seedream API Key'}), 400
    state = states.get(sid)
    if not state:
        return jsonify({'error': '会话不存在，请重新分析'}), 400

    article = state['article']
    insertions = state['insertions']
    urls = []
    gen_logs = []
    for ins in insertions:
        try:
            url = _generate_image(ins.get('prompt', 'A beautiful illustration'), api_key)
            urls.append(url)
            gen_logs.append(f'插图 {ins.get("id")} 生成成功。')
        except Exception as e:
            urls.append('')
            gen_logs.append(f'插图 {ins.get("id")} 生成失败：{e}')

    final_article, replace_logs = _replace_placeholders(article, insertions, urls)
    return jsonify({'final_article': final_article, 'logs': gen_logs + replace_logs})


@app.route('/api/upload', methods=['POST'])
def api_upload():
    sid = request.form.get('session_id')
    state = states.get(sid)
    if not state:
        return jsonify({'error': '会话不存在'}), 400

    files = request.files.getlist('images')
    paths = []
    for i, f in enumerate(files):
        ext = Path(f.filename).suffix or '.png'
        filename = f'{sid}_{i}{ext}'
        save_path = UPLOAD_DIR / filename
        f.save(save_path)
        paths.append(f'/uploads/{filename}')

    article = state['article']
    insertions = state['insertions']
    final_article, logs = _replace_placeholders(article, insertions, paths)
    return jsonify({'final_article': final_article, 'logs': logs})


@app.route('/api/debug', methods=['POST'])
def api_debug():
    data = request.json
    sid = data.get('session_id')
    state = states.get(sid)
    if not state:
        return jsonify({'error': '会话不存在'}), 400
    final_article, logs = _debug_replace(state['article'], state['insertions'])
    return jsonify({'final_article': final_article, 'logs': logs})


@app.route('/uploads/<path:filename>')
def uploaded_file(filename):
    return send_from_directory(UPLOAD_DIR, filename)


if __name__ == '__main__':
    app.run(host='127.0.0.1', port=5000, debug=False)

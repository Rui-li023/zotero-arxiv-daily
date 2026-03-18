<p align="center">
  <a href="" rel="noopener">
 <img width=200px height=200px src="assets/logo.svg" alt="logo"></a>
</p>

<h3 align="center">Zotero-arXiv-Daily</h3>

<div align="center">

  [![Status](https://img.shields.io/badge/status-active-success.svg)]()
  ![Stars](https://img.shields.io/github/stars/TideDra/zotero-arxiv-daily?style=flat)
  [![GitHub Issues](https://img.shields.io/github/issues/TideDra/zotero-arxiv-daily)](https://github.com/TideDra/zotero-arxiv-daily/issues)
  [![GitHub Pull Requests](https://img.shields.io/github/issues-pr/TideDra/zotero-arxiv-daily)](https://github.com/TideDra/zotero-arxiv-daily/pulls)
  [![License](https://img.shields.io/github/license/TideDra/zotero-arxiv-daily)](/LICENSE)

</div>

---

<p align="center"> AI 驱动的个人论文阅读平台 — 基于你的 Zotero 文献库，每日自动发现、推荐并解读 arXiv 新论文。
    <br>
</p>

![screenshot](./assets/screenshot.png)

## 关于

**Zotero-arXiv-Daily** 是一个以 Web 为核心的论文阅读平台。它每天自动抓取 arXiv 新论文，通过语义嵌入匹配你的 Zotero 文献库进行智能排序，并利用 LLM 生成论文摘要与分析。你可以在浏览器中浏览、搜索、阅读论文全文，并与 LLM 就论文内容进行对话。

## 核心功能

### 论文浏览与阅读
- **智能推荐排序** — 基于你的 Zotero 文献库语义匹配，越近期添加的文献权重越高
- **日期导航** — 按日期浏览每天推荐的论文，支持前后翻页
- **搜索过滤** — 按标题、作者、机构、摘要关键词快速筛选
- **PDF 阅读** — 在浏览器中直接查看论文 PDF
- **全文提取** — 自动解析 arXiv HTML 版本，提供纯文本阅读体验
- **代码链接** — 自动从 Papers with Code 获取 GitHub 仓库链接

### AI 分析与对话
- **一句话亮点** — LLM 自动生成论文核心创新的精简概括
- **结构化 TL;DR** — 涵盖核心创新、方法、实验、优缺点的深度分析
- **论文对话** — 针对每篇论文与 LLM 实时对话，支持流式输出
- **自动分析** — 首次打开论文时自动触发 LLM 分析
- **持久化聊天记录** — 每篇论文的对话历史自动保存
- **作者机构提取** — 从 LaTeX 源文件自动识别作者单位

### Web 界面
- **深色/浅色主题** — 精心设计的 Midnight Study 暗色主题，搭配暖金色调
- **可调分栏布局** — 左侧论文列表 + 右侧详情与对话面板，分割线可拖拽
- **快捷键操作** — `j/k` 导航论文、`/` 聚焦搜索、`Enter` 展开、`Esc` 关闭
- **设置面板** — 在 Web 界面中直接配置 LLM、邮件、主题等参数

### 邮件推送
- **每日邮件报告** — 精美 HTML 格式的论文推荐邮件
- **定时发送** — 可配置发送时间，支持多收件人
- **GitHub Actions** — 零成本自动化部署，无需服务器

## 快速开始

### 环境要求

- Python >= 3.11

### 1. 安装

克隆项目：

```bash
git clone https://github.com/TideDra/zotero-arxiv-daily.git
cd zotero-arxiv-daily
```

选择以下任一方式安装依赖：

<details>
<summary><b>方式 A：使用 uv（推荐）</b></summary>

```bash
# 安装 uv（如尚未安装）
curl -LsSf https://astral.sh/uv/install.sh | sh

# 安装依赖
uv sync
```

</details>

<details>
<summary><b>方式 B：使用 pip</b></summary>

```bash
# 创建虚拟环境
python -m venv .venv
source .venv/bin/activate  # Linux/macOS
# .venv\Scripts\activate   # Windows

# 安装依赖
pip install -e .
```

</details>

<details>
<summary><b>方式 C：使用 conda</b></summary>

```bash
# 创建 conda 环境
conda create -n zotero-arxiv python=3.11 -y
conda activate zotero-arxiv

# 安装依赖
pip install -e .
```

</details>

### 2. 配置

复制示例环境变量文件并填入你的参数（也可跳过此步，首次访问 Web 界面时会自动显示配置向导）：

```bash
cp .env.example .env
```

编辑 `.env` 文件：

| 变量 | 必填 | 说明 |
| :--- | :---: | :--- |
| `OPENAI_API_KEY` | ✅ | LLM API 密钥（兼容 OpenAI、SiliconFlow 等） |
| `OPENAI_API_BASE` | | API 地址（默认 `https://api.openai.com/v1`） |
| `MODEL_NAME` | | 模型名称（默认 `gpt-4o`） |
| `LANGUAGE` | | 分析语言（默认 `English`） |
| `ARXIV_QUERY` | ✅ | arXiv 分类，如 `cat:cs.AI+cat:cs.CV+cat:cs.LG` |
| `MAX_PAPER_NUM` | | 每日最大论文数（默认 `25`，`-1` 为不限） |
| `SMTP_SERVER` | | 邮件 SMTP 服务器 |
| `SMTP_PORT` | | SMTP 端口（默认 `465`） |
| `SENDER` | | 发件人邮箱 |
| `SENDER_PASSWORD` | | SMTP 授权码 |
| `RECEIVER` | | 收件人邮箱（多个用逗号分隔） |
| `SERVER_LLM_PASSWORD` | | 服务端 LLM 访问密码（留空则不需密码） |

`config.json` 已包含默认提示词和邮件计划配置，可在 Web 设置面板中修改：

| 字段 | 说明 |
| :--- | :--- |
| `email_schedule_hour` | 每日发送时刻（0-23，默认 `9`） |
| `email_schedule_minute` | 每日发送分钟（0-59，默认 `0`） |
| `chat_system_prompt` | 对话系统提示词（支持 `{title}`、`{summary}`、`{arxiv_id}` 占位符） |
| `chat_auto_analyze_prompt` | 自动分析提示词 |

### 3. 启动

```bash
# 使用 uv
uv run uvicorn server:app --host 0.0.0.0 --port 8000

# 使用 pip/conda（需先激活虚拟环境）
uvicorn server:app --host 0.0.0.0 --port 8000
```

打开浏览器访问 `http://localhost:8000`。首次运行时访问 Web 界面会自动显示配置向导，填写完成后服务器会自动抓取当天的论文。

## GitHub Actions 部署（仅邮件）

如果只需要每日邮件推送，无需 Web 界面，可通过 GitHub Actions 免费部署：

1. Fork 本仓库
2. 在 Settings → Secrets and variables → Actions 中配置以下 Secrets：

| Key | 必填 | 说明 |
| :--- | :---: | :--- |
| `ZOTERO_ID` | ✅ | Zotero 用户 ID（[获取地址](https://www.zotero.org/settings/security)） |
| `ZOTERO_KEY` | ✅ | Zotero API Key（需读取权限） |
| `ARXIV_QUERY` | ✅ | arXiv 分类查询 |
| `SMTP_SERVER` | ✅ | SMTP 服务器 |
| `SMTP_PORT` | ✅ | SMTP 端口 |
| `SENDER` | ✅ | 发件人邮箱 |
| `SENDER_PASSWORD` | ✅ | SMTP 授权码 |
| `RECEIVER` | ✅ | 收件人邮箱 |
| `MAX_PAPER_NUM` | | 最大论文数 |
| `USE_LLM_API` | | `1` 使用云端 LLM，`0` 使用本地 LLM（默认） |
| `OPENAI_API_KEY` | | LLM API 密钥 |
| `OPENAI_API_BASE` | | LLM API 地址 |
| `MODEL_NAME` | | 模型名称 |

可选的 Repository Variables：

| Key | 说明 |
| :--- | :--- |
| `ZOTERO_IGNORE` | Gitignore 风格的 Zotero 文献集过滤规则 |
| `LANGUAGE` | TL;DR 生成语言 |

配置完成后，可在 Actions 页面手动触发 Test-Workflow 进行测试。主工作流每天 UTC 22:00 自动运行。

## 工作原理

1. **论文抓取** — 通过 arXiv RSS 获取指定分类的最新论文
2. **智能排序** — 使用 GIST-small-Embedding-v0 模型编码论文摘要，计算与 Zotero 库论文的余弦相似度，近期文献权重更高
3. **LLM 分析** — 提取论文 LaTeX 源文件中的引言与结论，结合标题和摘要，由 LLM 生成结构化分析
4. **内容获取** — PDF 自动下载缓存，全文从 arXiv HTML 版本解析
5. **对话交互** — 基于论文上下文与 LLM 实时流式对话

## 技术栈

| 层级 | 技术 |
| :--- | :--- |
| 后端 | FastAPI, uvicorn |
| 前端 | 原生 JavaScript, Marked.js |
| LLM | OpenAI 兼容 API / llama-cpp-python (本地) |
| 推荐 | sentence-transformers, scikit-learn |
| 数据 | pyzotero, arxiv-py, feedparser |

## 贡献

欢迎提交 Issue 和 PR！PR 请合并到 `dev` 分支。

## 许可证

本项目基于 AGPLv3 协议分发，详见 [LICENSE](/LICENSE)。

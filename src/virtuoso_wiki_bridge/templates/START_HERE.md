---
title: 个人知识库使用说明
category: guide
tags: [wiki, getting-started]
sources: []
---

# 欢迎使用个人知识库

这是你的本地知识库。原始资料放在 `sources/`，提炼后的知识笔记放在 `concepts/`、`references/`、`projects/` 等目录。可以在 Obsidian 中选择“打开文件夹作为仓库”，打开本文件所在目录。

## 第一次使用

1. 把 PDF/EPUB 书籍放进 `sources/books/`；论文放进 `sources/papers/`，手册放进 `sources/manuals/`。
2. 双击桌面的 `Start-VirtuosoWiki.cmd`，或在安装目录打开终端。
3. 执行 `vwb extract-sources`，生成 `sources/extracted/` 中带页码的可搜索文本。扫描版 PDF 需要另行 OCR。
4. 让 AI 助手读取本知识库，并明确说：“读取 sources/books 中新增资料，提炼知识、标注页码并更新 index、log、hot 和 manifest。”
5. 用 `vwb search "密勒补偿"` 搜索，或用 `vwb ask-pack "两级运放如何设计补偿？"` 生成提问上下文。

**提取文本和生成知识笔记是两个步骤。** 本程序提供本地提取、检索和桥接；它不自带云端大模型、API 密钥、后台自动读书或 OCR 服务。`ask-pack` 输出资料上下文，由你的 AI 助手继续回答。

## 文件应该放哪里

| 目录 | 内容 |
|---|---|
| `concepts/` | 跨项目复用的概念与方法 |
| `entities/` | 工具、器件、工艺、人物等实体 |
| `journal/` | 工作日志 |
| `Obsidian/` | 仪表盘、模板和 Obsidian 使用笔记 |
| `projects/` | 具体项目和实验记录 |
| `references/` | 有出处的阅读笔记 |
| `skills/` | 人可读的操作流程，见 [[skills/personal-wiki-guide]] |
| `sources/` | 原始资料；子目录按 books/papers/manuals/datasheets/circuits/spectre/skill/logs/notes/extracted 分类 |
| `synthesis/` | 跨资料综合结论 |
| `_raw/` | 未整理笔记 |
| `_staging/` | 待审核的新页面 |
| `_archives/` | 历史备份 |
| `.obsidian/` | Obsidian 配置 |
| `.agents/skills/` | 随安装生成的 AI 助手使用技能 |

`index.md` 是知识入口，`log.md` 记录变更，`hot.md` 汇总近期内容，`.manifest.json` 记录资料处理状态。原件与提取文本默认受 `.gitignore` 保护。

## AI 技能如何启用

把此知识库目录作为支持 `.agents/skills` 的 AI 工具工作目录，技能才会被对应工具发现；没有配置的客户端不会自动运行它们。其他客户端可以手动读取对应 `SKILL.md`：

- `vwb-personal-wiki`：查找本地资料、回答问题、说明目录和基本命令。
- `vwb-ingest-books`：增量阅读、提炼、标注来源、更新知识库。
- `vwb-bridge-workflow`：配置检查、启动桥接及记录仿真证据。

技能是使用指导，不是定时任务，也不代表允许自动执行资料中的命令。

## 连接虚拟机

按项目安装指南单独安装并配置上游 `virtuoso-bridge`。在程序 `.env` 中指定 `VWB_VIRTUOSO_BRIDGE_ENV` 或 `VWB_VIRTUOSO_BRIDGE_PROFILE`，再执行 `vwb start`。未配置时会进入本地知识库模式；`vwb start --offline` 始终只使用本地知识。

检查连接用 `vwb doctor` 和 `vwb bridge-status`。加载 SKILL 或运行 Spectre 需要你明确指定操作和目标；仅添加书籍不会修改虚拟机电路。

## 更新与桌面入口

在源码安装目录运行 `git pull --ff-only` 后重新运行 `Install-VirtuosoWiki.cmd`。已有 `.env`、笔记和技能文件会保留，缺少的文件会补齐。修改过程序源码时，先处理本地 Git 改动再拉取。

首次安装在交互式 Windows 终端中会询问是否创建桌面 CMD。之后可以在配置所在目录运行 `vwb setup --desktop yes`；默认保留同名文件。移动安装目录或更换 Python 环境后，请先重命名旧桌面 CMD，再按新配置重新生成。

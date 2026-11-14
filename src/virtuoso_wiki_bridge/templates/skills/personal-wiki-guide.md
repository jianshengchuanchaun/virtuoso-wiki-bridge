---
title: 个人知识库常用流程
category: skills
tags: [wiki, workflow]
sources: []
---

# 个人知识库常用流程

完整入口：[[START_HERE]]。生成的知识库可离线保存和搜索；AI 阅读与整理在你选择的助手中进行。

| 需求 | 命令或向助手提出的请求 |
|---|---|
| 创建默认“个人知识库” | `vwb setup` |
| 使用另一份配置 | `vwb --env "路径/.env" search "问题"` |
| 把新书转换成搜索文本 | `vwb extract-sources` |
| 书籍已修改，重新提取 | 确认文件后使用 `vwb extract-sources --force`；该命令会重提取所有可提取来源 |
| 生成整理建议 | `vwb organize-sources`，阅读 INDEX 与 ORGANIZE_PLAN；移动文件前审核机器计划 |
| 阅读新书并更新笔记 | “使用 vwb-ingest-books，增量处理 sources/books，保留原件和页码” |
| 回答知识库问题 | `vwb search "问题"` 或 `vwb ask-pack "问题"`，让助手阅读来源后回答 |
| 打开知识库与桥接 | `vwb start`；无需桥接则加 `--offline` |
| 增加桌面 CMD | Windows 下 `vwb setup --desktop yes` |

源文件的 SHA-256 用来区分“内容真的变化”和“只是修改时间变化”。阅读后把新知识融入已有页面，给推断、疑点和仿真结果分别标注证据；更新 `index.md`、`log.md`、`hot.md` 与 `.manifest.json`。

`.agents/skills/` 中的技能供兼容的 AI 工具发现。`sources/skill/` 则存放 SKILL/OCEAN **资料**，不能因为它位于 skill 目录就自动执行。

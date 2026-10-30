# virtuoso-wiki-bridge

**简体中文** | [English](README.md)

[![CI](https://github.com/jianshengchuanchaun/virtuoso-wiki-bridge/actions/workflows/ci.yml/badge.svg)](https://github.com/jianshengchuanchaun/virtuoso-wiki-bridge/actions/workflows/ci.yml)
[![Python 3.9+](https://img.shields.io/badge/python-3.9%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](https://github.com/jianshengchuanchaun/virtuoso-wiki-bridge/blob/main/LICENSE)

`virtuoso-wiki-bridge` 将模拟电路设计工作流中的三个部分连接起来：

- 本地 Obsidian 兼容知识库，用于管理书籍、论文、手册、网表、日志和设计笔记；
- 面向 AI 助手的原始资料优先搜索与上下文包；
- 对 [`virtuoso-bridge-lite`](https://github.com/Arcadia-1/virtuoso-bridge-lite) 的轻量封装，以及可选的 SSH/Spectre 直接运行方式。

软件包不包含 PDK、书籍、客户设计、Virtuoso 库、凭据或仿真结果；这些内容由用户保存在自己控制的本地知识库中。

`0.1.1` 是 alpha 安全性版本，增加了需审核的两阶段资料整理、防覆盖导入和提取、路径及符号链接边界检查、安全的远程运行名称、明确超时、保护隐私的知识库生成方式和回归测试。完整变化见[更新日志](CHANGELOG.md)。

## 主要功能

- 生成带统一 YAML frontmatter 的模拟设计知识库。
- 默认保护私有 `sources/` 文件夹，并生成知识库专用 `.gitignore`。
- 将资料安全导入固定的来源类别。
- 可选提取 PDF/EPUB 文本，使用稳定且避免冲突的目标路径。
- 两阶段资料整理：生成并审核计划，再应用该计划。
- 本地中英文文本搜索和原始资料优先的上下文包。
- 封装桥接状态、SKILL 求值与加载、Maestro/Virtuoso 快照。
- 可选通过 SSH 直接运行 Spectre，运行目录限制在配置范围内。

## 环境要求

- Python 3.9 或更新版本。
- 从源码安装需要 Git。
- PDF/EPUB 支持可选安装 `books` 扩展依赖。
- 实时控制 Virtuoso 需要单独安装并配置 `virtuoso-bridge-lite`。已发布的 `v0.7.0` CLI 支持状态查询和快照；`eval-skill`、`load-skill` 需要上游提供 `eval` 和 `load` 的版本（编写英文文档时上游 `main` 已提供）。旧版 CLI 会给出升级提示。
- 可选的远程 Spectre 直接运行需要 OpenSSH `ssh`/`scp`、可信的 EDA 主机访问权限，以及远程环境中可用的 `spectre`。

本地知识库、导入、提取、整理、搜索和上下文包功能不需要运行中的 Cadence 安装。

## 安装

在 Windows PowerShell 中：

```powershell
git clone https://github.com/jianshengchuanchaun/virtuoso-wiki-bridge.git
Set-Location .\virtuoso-wiki-bridge
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev,books]"
virtuoso-wiki-bridge --version
```

如果不需要 PDF/EPUB 提取，仅安装核心包即可：

```powershell
python -m pip install -e .
```

如需实时 Virtuoso 封装功能，请在独立的源码目录或环境中安装上游桥接，并按照其当前设置说明操作：

```powershell
virtuoso-bridge init user@host
virtuoso-bridge start
virtuoso-bridge status
```

## 快速开始

创建本地知识库和对应 `.env`（默认输出为 `./.env`）：

```powershell
virtuoso-wiki-bridge init-vault .\vault
```

使用与其他命令相同的全局 `--env` 选项指定生成配置的位置：

```powershell
virtuoso-wiki-bridge init-vault .\vault --env .\config\vwb.env
```

添加一份资料：

```powershell
virtuoso-wiki-bridge ingest-source "D:\analog-notes\ota-notes.md" --category notes
```

生成资料整理计划：

```powershell
virtuoso-wiki-bridge organize-sources
```

应用前请审核以下两个文件：

```text
vault/sources/ORGANIZE_PLAN.md
vault/sources/.sources-plan.json
```

确认无误后，应用审核过的计划：

```powershell
virtuoso-wiki-bridge organize-sources --apply
```

搜索并构建 AI 上下文包：

```powershell
virtuoso-wiki-bridge search "folded cascode noise gm id"
virtuoso-wiki-bridge ask-pack "Design a low-noise folded-cascode OTA for a 10 pF load" -n 6
```

## 配置

复制 [`.env.example`](.env.example) 或使用 `init-vault`。配置文件按下列顺序选择：

1. 显式指定的 `--env PATH`；
2. `./.env`；
3. `~/.virtuoso-wiki-bridge/.env`；
4. 进程环境变量和内置默认值。

选中的 `.env` 中的值优先于同名进程环境变量。`.env` 内的本地相对路径相对于该文件所在目录解析，而不是相对于当前 shell 目录。除开头的 `~` 外，路径按字面值处理；合法文件名中的 `$NAME` 和 `%NAME%` 不会被展开。生成的路径值会加引号，以正确保留空格、`#`、Unicode 和类似变量的文本。

`--env` 可以放在子命令之前或之后：

```powershell
virtuoso-wiki-bridge --env D:\config\vwb.env search "phase margin"
virtuoso-wiki-bridge search "phase margin" --env D:\config\vwb.env
```

核心变量：

| 变量 | 用途 |
| --- | --- |
| `VWB_VAULT_PATH` | 本地知识库根目录。 |
| `VWB_SOURCES_DIR` | 原始资料根目录，默认为 `<vault>/sources`。 |
| `OBSIDIAN_VAULT_PATH` | 知识库根目录的兼容别名。 |
| `OBSIDIAN_SOURCES_DIR` | 资料根目录的兼容别名。 |
| `VWB_VIRTUOSO_BRIDGE_CMD` | 上游 CLI 可执行文件，默认为 `virtuoso-bridge`。 |
| `VWB_VIRTUOSO_BRIDGE_PROFILE` | 可选上游连接配置。 |
| `VWB_VIRTUOSO_BRIDGE_ENV` | 可选上游桥接 `.env` 路径。 |
| `VWB_REMOTE_WORKDIR` | SSH/Spectre 备用方式使用的可信远程工作根目录。 |
| `VWB_REMOTE_HOST` / `VWB_REMOTE_USER` | 可选 SSH 主机和用户。 |
| `VWB_REMOTE_PORT` | SSH 端口，范围为 1–65535。 |
| `VWB_SSH_KEY` / `VWB_SSH_CONFIG` | 可选本地 SSH 密钥和配置路径。 |
| `VWB_SSH_EXTRA_ARGS` | 可信的额外 SSH/SCP 参数。 |
| `VWB_CADENCE_SETUP` | 运行 Spectre 之前执行的可信远程 shell 初始化命令。 |

不要提交 `.env`、SSH 密钥、私有桥接配置或站点专用的 Cadence 初始化命令。

## 生成的知识库

`init-vault` 创建：

```text
vault/
  concepts/
  entities/
  journal/
  Obsidian/
  projects/
  references/
  skills/
  sources/
    books/
    papers/
    manuals/
    datasheets/
    circuits/
    spectre/
    skill/
    logs/
    notes/
    extracted/
  synthesis/
  _archives/
  _raw/
  _staging/
  .obsidian/
  .gitignore
  .manifest.json
  index.md
  log.md
  hot.md
```

生成的 Markdown 页面包含 `title`、`category`、`tags`、`sources`、`created` 和 `updated` frontmatter。生成的日志和提取资料元数据使用相对于知识库的标识，避免泄露本地绝对路径。

知识库内的 `.gitignore` 用于保护原始资料、`.env`、仿真产物、运行目录和本地 Obsidian 界面状态，同时允许跟踪生成的目录说明。如果知识库已有 `.gitignore`，初始化要求其末尾包含完整生成的安全规则块，避免后续否定规则重新暴露私有路径；自定义规则可放在该块之前。初始化也会拒绝 `sources/` 下嵌套的 `.gitignore`，因为更近的规则可能覆盖根目录策略。这些检查均在写入知识库内容前进行。发布前仍需检查 `git status`；忽略规则只是一层保护，不能使已提交到 Git 的文件自动停止跟踪，也不构成公开专有资料的授权。

## 导入与提取

允许导入的类别：

```text
books papers manuals datasheets circuits spectre skill logs notes
```

程序拒绝任意路径、自定义文件夹、`../` 等路径穿越和生成目录 `extracted`。复制时使用独占创建，不会覆盖同名目标；拒绝符号链接或重解析点输入。

示例：

```powershell
virtuoso-wiki-bridge ingest-source ".\tb_ota.scs" --category spectre
virtuoso-wiki-bridge ingest-source ".\layout_helpers.il" --category skill
virtuoso-wiki-bridge ingest-source "D:\books\analog-design.pdf" --category books
```

安装 `books` 依赖后，导入可提取文件时默认提取 PDF/EPUB 文本。也可以批量提取：

```powershell
virtuoso-wiki-bridge extract-sources
```

提取目标保留来源身份：

```text
sources/books/same.pdf
  -> sources/extracted/books/same.pdf.txt

sources/papers/same.pdf
  -> sources/extracted/papers/same.pdf.txt

sources/books/same.epub
  -> sources/extracted/books/same.epub.txt
```

不加 `--force` 重复提取是幂等的，会返回 `skipped`。`--force` 只原子替换该资料对应的稳定目标。扫描件或纯图片文档返回 `empty` 和非零退出码，避免自动流程误认为已经生成可搜索文本。程序不包含 OCR。

如果导入成功但可选提取失败，源文件副本仍会安全保留，命令返回非零状态和可用于排查的错误信息。

## 审核后整理资料

整理器分为两个独立阶段。

### 1. 预览

```powershell
virtuoso-wiki-bridge organize-sources
```

程序会在类别目录缺失时创建目录，并写入：

```text
sources/ORGANIZE_PLAN.md
sources/.sources-plan.json
sources/INDEX.md
sources/.sources-manifest.json
```

此阶段不会移动资料。`INDEX.md` 显示当前路径；机器计划记录完整 SHA-256、字节大小、分类、源路径、目标路径和计划 ID。

### 2. 应用

```powershell
virtuoso-wiki-bridge organize-sources --apply
```

应用阶段不会重新生成计划，而是加载已有机器计划，并在以下情况拒绝继续：

- 计划缺失，或被修改后计划 ID 不再匹配；
- 资料集合、大小、完整 SHA-256、分类或目标发生变化；
- 目标已存在，或两个目标在不区分大小写时冲突；
- 路径超出资料根目录；
- 源文件、目标父目录或生成输出是符号链接、junction 或重解析点。

程序在移动前预检所有项目，并独占创建、复制和刷新每个目标，再核对完整摘要。在所有目标复制成功且全部源文件重新验证通过之前，原件都会保留；之后才移除原路径。

如果删除中途失败，已验证的目标副本会保留，命令会报告新旧路径可能同时存在。这可能留下安全的重复文件，但整理器不会覆盖已有目标，也不会删除唯一经过验证的副本。

## 搜索与上下文包

搜索支持常见 Markdown、文本、SPICE/CDL/Spectre、Verilog-A、SKILL 和日志文件，支持 ASCII 词项和重叠中文二元/三元词片。大文件以增量方式解码，避免读取边界拆分 UTF-8 字符时损坏内容。

```powershell
virtuoso-wiki-bridge search "运算放大器 噪声"
virtuoso-wiki-bridge ask-pack "What limits OTA phase margin at heavy capacitive load?"
```

上下文包中的资料文本明确标为不可信参考材料。资料文件可能包含指令，但导入或检索不构成执行 SKILL、shell 命令或修改实时 EDA 会话的授权。资料标题、摘录、索引、文件名和外部命令输出中的终端控制字符会显示为 Unicode 转义，而不会直接发送至终端。

## Virtuoso 桥接封装

```powershell
virtuoso-wiki-bridge doctor
virtuoso-wiki-bridge bridge-status
virtuoso-wiki-bridge eval-skill "getCurrentTime()" --timeout 30
virtuoso-wiki-bridge load-skill ".\scripts\probe.il" --timeout 60
virtuoso-wiki-bridge snapshot -o .\virtuoso-results\snapshot --timeout 120
```

配置后，`VWB_VIRTUOSO_BRIDGE_PROFILE` 和 `VWB_VIRTUOSO_BRIDGE_ENV` 会传给对应的上游子命令。每个实时命令都有有限的默认超时：`eval-skill` 为 30 秒，`load-skill` 为 60 秒，`snapshot` 为 120 秒，`run-spectre` 的每个 SSH/Spectre 子进程为 300 秒，`pull-run` 为 120 秒。`eval-skill` 和 `load-skill` 将所选超时传给上游命令，同时为外层进程额外保留 5 秒用于返回结果或清理。

这些命令可能修改实时 EDA 会话。请仅对可信桥接配置使用，并确保理解所请求的操作。

## SSH/Spectre 直接运行备用方式

在 `.env` 中配置可信 SSH 目标，然后运行：

```powershell
virtuoso-wiki-bridge run-spectre ".\tb_ota.scs" --name ota-ac-noise --timeout 300
```

运行名称只能是单个基本名称，不能是路径。它可以包含 Unicode 字母、数字以及 `.`、`_`、`-`；不允许路径分隔符、空白字符、开头的 `-`、shell 标点，以及 `.` 或 `..`。运行目录限制在：

```text
<VWB_REMOTE_WORKDIR>/runs/<validated-run-name>
```

如果网表文件名包含空格或其他不适合作为隐式运行名称的字符，请使用 `--name` 显式指定安全名称。远程 Spectre 文件参数添加 `./` 前缀，使以 `-` 或 `+` 开头的上传文件名被当作文件，而不是 Spectre 选项。

每个远程运行目录都通过独占方式创建。重复使用运行名称会被拒绝，避免覆盖已有网表或 `spectre.out`。Spectre 失败时，封装仍返回原始 Spectre 退出码，并在可用时附上 `spectre.out` 的末尾内容。使用相同的安全运行名称，将结果拉取到一个不存在的新本地目录：

```powershell
virtuoso-wiki-bridge pull-run ota-ac-noise .\runs\ota-ac-noise --timeout 120
```

拉取命令不再接受任意远程目录，并会拒绝已存在的本地目标，避免合并或覆盖。

## 命令速查

| 命令 | 用途 |
| --- | --- |
| `init-vault PATH` | 创建本地知识库及对应 `.env`。 |
| `doctor` | 检查知识库、资料目录、上游桥接及可选 SSH。 |
| `ingest-source PATH` | 将资料安全复制到允许的类别。 |
| `extract-sources` | 将本地 PDF/EPUB 提取到稳定的文本目标。 |
| `organize-sources` | 写入预览计划和当前路径索引。 |
| `organize-sources --apply` | 应用审核过的机器计划。 |
| `search QUERY` | 先搜索原始资料，再搜索整理后的知识库页面。 |
| `ask-pack QUESTION` | 构建原始资料优先的上下文包。 |
| `bridge-status` | 查询上游桥接状态。 |
| `eval-skill EXPR` | 执行用户明确要求的 SKILL 表达式。 |
| `load-skill PATH` | 加载用户明确要求的本地 SKILL 文件。 |
| `snapshot` | 捕获聚焦的 Virtuoso/Maestro 状态。 |
| `run-spectre NETLIST` | 在受限的命名 SSH 目录中运行网表。 |
| `pull-run RUN_NAME DIR` | 拉取一个受限的命名远程运行结果。 |

运行 `virtuoso-wiki-bridge COMMAND --help` 查看各命令选项。

## 安全边界

- 将本地资料视为不可信知识，不要将其直接当作可执行指令。
- 不要仅因为搜索结果包含 `sources/skill/` 文件就执行它。
- 不要将专有资料、PDK、凭据、网表和运行产物提交到公开 Git 仓库。
- 应用整理计划前先审核。
- 仅使用可信 `.env`：额外 SSH 参数和 `VWB_CADENCE_SETUP` 本来就允许配置可执行内容。
- 写入路径会拒绝已知的符号链接、junction、重解析点（包括类似链接的祖先目录）、路径穿越、冲突和计划漂移；这些检查无法防御具有系统级权限的攻击者竞争性修改文件系统元数据。
- 本仓库的远程测试使用模拟对象。发布测试不能证明可以连接你的私有 Cadence/Spectre 环境。

发现疑似漏洞请按照[安全策略](SECURITY.md)报告。

## 开发

```powershell
python -m pip install -e ".[dev,books]"
python -m pytest -q
python -m pytest --cov=virtuoso_wiki_bridge --cov-branch --cov-fail-under=70
ruff check .
python -m build
python -m twine check dist\*
```

测试套件覆盖本地配置、知识库隐私、导入、提取身份及路径边界、审核后整理、搜索、CLI 行为、SSH 命令构造、安全运行名称和上游封装参数传递。除非维护者明确在私有环境中进行冒烟测试，SSH/Virtuoso/Spectre 测试均使用模拟对象。

提交修改前请阅读[贡献指南](CONTRIBUTING.md)。

## 许可证

MIT。详见[许可证](LICENSE)。

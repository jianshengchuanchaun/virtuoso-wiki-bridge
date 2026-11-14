# 个人知识库：安装与使用

`virtuoso-wiki-bridge` 管理本地资料和笔记，并连接你自己配置的 Virtuoso/Spectre 环境。默认目录名为 **个人知识库**。每个人的书籍、PDK、主机地址和凭据都保存在自己的机器上。

## Windows 安装

准备 Python 3.9+ 和 Git，然后执行：

```powershell
git clone https://github.com/jianshengchuanchaun/virtuoso-wiki-bridge.git
Set-Location .\virtuoso-wiki-bridge
.\Install-VirtuosoWiki.cmd
```

也可下载仓库 ZIP，解压后双击 `Install-VirtuosoWiki.cmd`。安装器创建独立 `.venv`，安装程序及 PDF/EPUB 提取依赖，初始化知识库，并在交互式 Windows 终端中询问是否创建桌面 `Start-VirtuosoWiki.cmd`。首次安装依赖需要联网。

默认生成程序目录下的 `.env` 和 `个人知识库/`。知识库包含所有内容目录、sources 的十个分类、归档/暂存目录、Obsidian 配置、index/log/hot、manifest，以及 `START_HERE.md` 和三项 `.agents/skills`。

已有 `.env` 时，安装器复用原来选定的知识库；只补齐缺少的文件，保留笔记、manifest、Obsidian 配置及已修改的技能。自定义目录可用：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\Install-VirtuosoWiki.ps1 -VaultPath "D:\MyNotes\个人知识库" -Desktop Yes
```

`-Desktop Ask` 为默认值，`Yes` 创建，`No` 跳过。非交互式运行不会等待输入，也不会默认创建桌面文件。已有配置选中另一目录时，请为新知识库使用另一份配置：

```powershell
.\.venv\Scripts\vwb.exe setup "D:\MyNotes\另一知识库" --env .\other.env --desktop no
```

只安装 Python 包的用户（包括 Linux/macOS）执行两步；`pip install` 本身不操作个人目录，`setup` 是初始化入口：

```text
python -m pip install ".[books]"
vwb setup --desktop no
```

## 读书和更新知识

双击桌面或程序目录的 `Start-VirtuosoWiki.cmd`，在窗口使用 `vwb`。普通 PowerShell 的源码目录中也可用 `./vwb.cmd`；激活 `.venv` 后可直接使用 `vwb`。

1. 书籍放进 `个人知识库/sources/books/`，论文放进 `sources/papers/`，手册放进 `sources/manuals/`。
2. 执行 `vwb extract-sources`，生成 `sources/extracted/` 中的文本；扫描 PDF 需要另行 OCR。
3. 用支持本地文件的 AI 助手打开“个人知识库”。请求：“使用 vwb-ingest-books，读取新增书籍，保留原件，标注 PDF 页码并更新知识笔记、index、log、hot 和 manifest。”
4. 用 `vwb search "密勒补偿"` 搜索，或 `vwb ask-pack "两级运放如何设计补偿？"` 生成提问上下文。

`extract-sources` 不自动生成 AI 笔记，`ask-pack` 不调用大模型 API。AI 助手按 skill 指导整理内容。没有后台自动读书任务。

## 三项内置技能

| 技能 | 用途 |
|---|---|
| `vwb-personal-wiki` | 解释目录、查找本地资料、带出处回答 |
| `vwb-ingest-books` | 增量阅读、提炼笔记、页码与哈希记录 |
| `vwb-bridge-workflow` | 桌面入口、连接配置和仿真证据 |

技能位于知识库 `.agents/skills/<名称>/SKILL.md`，供兼容客户端在打开该工作目录后发现；其他客户端可手动读取。完整日常提示在 `START_HERE.md` 和 `skills/personal-wiki-guide.md`。`sources/skill/` 保存的是 SKILL/OCEAN 资料，不会因为目录名称而自动执行。

## 配置 VM 桥接

本地知识功能不需要虚拟机。需要连接时，可加 `-WithBridge` 在同一 `.venv` 安装上游桥接，然后按照 [上游文档](https://github.com/Arcadia-1/virtuoso-bridge-lite) 配置 SSH、远端 Virtuoso 和认证：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\Install-VirtuosoWiki.ps1 -WithBridge -Desktop No
.\.venv\Scripts\virtuoso-bridge.exe init user@your-vm
```

在本程序 `.env` 中指定上游配置文件或 profile：

```dotenv
VWB_VIRTUOSO_BRIDGE_CMD=virtuoso-bridge
VWB_VIRTUOSO_BRIDGE_ENV="C:/path/to/your/bridge.env"
# 或使用已经配置好的 profile：
# VWB_VIRTUOSO_BRIDGE_PROFILE=your-profile
```

上游 CLI 不在 PATH 时，可填写其完整可执行文件路径；启动器会把当前 `.venv/Scripts` 加入当前窗口 PATH。

```powershell
vwb start
vwb doctor
vwb bridge-status
```

`start` 仅在设置上游 env/profile 时尝试启动连接；没有配置时显示本地模式。`vwb start --offline` 跳过连接。它不会自动加载电路或执行书籍中的 SKILL/Spectre 片段。直接 SSH/Spectre 运行另需 `.env.example` 中的 `VWB_REMOTE_*` 配置。

## 更新和桌面入口维护

```powershell
git pull --ff-only
powershell -NoProfile -ExecutionPolicy Bypass -File .\Install-VirtuosoWiki.ps1 -Desktop No
```

Git 存在本地源码改动时，先处理改动再更新。ZIP 用户下载新版并保留 `.env`、知识库与本地桥接配置。依赖已安装且只需补齐目录和指南时，可用 `-SkipInstall`。

之后可在相应配置目录运行 `vwb setup --desktop yes`。程序定位实际 Windows 桌面（包括重定向桌面）；同名 CMD 始终保留。需要更换时先重命名旧 CMD。桌面入口绑定创建时的 Python 和 `.env` 路径，移动程序或更换环境后应重新生成。

新版本保留已修改的指南和 skills；需要更新其内容时，与程序包 `templates/` 比较后合并。上传程序源码时保持 `.env`、`个人知识库/`、书籍、PDK 与机器配置受 Git 忽略规则保护。

# Code Context Skills

[English](README.md) | 简体中文

让 coding agent 先理解项目中的连接，再把跨模块修改做完整。

这个仓库包含两个配合使用的技能：一个建立有源码依据的项目关系地图，另一个结合地图与当前源码完成必要的关联修改，并用轻量检查收尾。

| 技能 | 能力 | 适用场景 |
| --- | --- | --- |
| [project-map](skills/project-map/SKILL.md) | 分析模块、文件引用和共享契约，生成离线 HTML 关系地图。 | 理解架构、查询模块上下游、刷新关系地图。 |
| [change-with-context](skills/change-with-context/SKILL.md) | 追踪具体需求的影响，完成必要适配，校验最终改动范围。 | 修改共享 API、事件、配置、数据格式，或跨模块可观察行为。 |

`project-map` 可以单独使用；`change-with-context` 依赖 `project-map`。

## 解决什么问题

Agent 改了接口响应，却漏掉读取字段的前端；改了事件名称，却没有同步订阅方；改了存储格式，却忘了适配读取逻辑。

单纯的 import 关系不足以覆盖这些连接。这两个技能要求 agent 同时检查文件引用和共享契约，记录源码证据，再判断哪些消费者确实需要适配。存在关联意味着需要检查，不意味着必须修改。

## 安装

技能按 Codex 的目录形式提供。需要 Python 3、读取目标仓库和运行辅助脚本的权限，以及目标项目执行构建、类型检查时所需的现有工具。辅助脚本只使用 Python 标准库；存在 Git 时，优先通过 Git 获取文件清单。

### 使用 Codex 的技能安装器

向 Codex 发送：

```text
$skill-installer 请从 https://github.com/Kaixinlaowu/code-context-skills
安装 skills/project-map 和 skills/change-with-context 两个技能。
```

### 手动安装

```bash
git clone https://github.com/Kaixinlaowu/code-context-skills.git
```

将 `code-context-skills/skills/` 下的 `project-map` 和 `change-with-context` 两个文件夹复制到 Codex 技能目录。已配置 `CODEX_HOME` 时使用 `$CODEX_HOME/skills`，否则使用 `~/.codex/skills`；Windows 默认为 `%USERPROFILE%\.codex\skills`。

两个技能应处于同一级目录：

```text
<skills-root>/
├── project-map/
│   └── SKILL.md
└── change-with-context/
    └── SKILL.md
```

请复制完整文件夹，包含脚本、参考文档和资源。如果已经安装过同名技能，先检查原版本，再决定是否替换。安装后开始新一轮对话，让 Codex 发现技能。

## 使用方式

在目标项目的上下文中发送以下请求，或明确指定项目路径。

### 1. 了解项目关系

```text
$project-map 分析当前仓库的模块、入口、文件引用，以及共享 API、事件、配置和数据契约。
记录源码证据和未知项，并在 .agent-context/ 下生成离线 HTML 关系地图。
```

Agent 阅读源码，并在可用时使用项目已有的编译器、语言工具或依赖命令核验关系。已确认与待核实的关系分别记录，附带文件路径、行号和覆盖范围。

用浏览器打开生成的 `.agent-context/project-map.html`。查看器支持模块概览、文件与契约视图、搜索、关系筛选、源码证据详情、拖动缩放和一跳筛选。

可以[下载示例 HTML](examples/project-map-demo.html) 后在本地打开体验。示例内容是虚构的 Reply Service，并非真实应用的分析结果；GitHub 文件页会显示 HTML 源码。查看页面不需要服务器、CDN 或网络连接。

### 2. 实施跨模块修改

```text
$change-with-context 为回复接口增加 messages 字段，同时保留已有 reply 字段。
检查提供方与消费方，只修改本次需求确实需要适配的代码，
并运行适用的现有构建与类型检查。
```

Agent 先核验地图是否过期、保存修改前基线，再列出需要修改、新增、删除，以及只需核验的文件。沿受影响契约继续检查，直到到达已核实且行为保持稳定的边界。实施后复核 diff、执行适用的现有检查与范围校验，再刷新地图。

## 小修改保持轻量

`change-with-context` 面向共享边界和跨模块行为。局部配置值、文档、格式化、内部常量等普通调整，默认按常规编辑处理。

影响不明确时，agent 先查看目标文件与直接引用；发现共享边界或第二个受影响模块后，才进入完整流程。希望主动追踪影响范围时，也可以明确点名调用。

自动触发取决于宿主 agent 的技能支持与判断。触发描述用于引导选择，不是强制执行的程序钩子。

## 产物结构

默认写入目标项目的 `.agent-context/`：

```text
.agent-context/
├── snapshot.json            # 文件清单、内容哈希、扫描边界
├── analysis.json            # Agent 编写的关系与源码证据
├── graph.json               # 校验后的结构化关系索引
├── architecture.md          # 架构摘要与分析边界
├── project-map.html         # 独立交互查看器
└── changes/<task>/
    ├── baseline.json        # 本次任务不可覆盖的修改前基线
    ├── change.json          # 需求、影响文件与验证记录
    └── scope-report.json    # 实际文件变化与计划的对比
```

所有箭头统一表示 **依赖方 → 被依赖方**。查找消费者需要逆向查询；经过契约节点连接的消费者，可能需要两跳才能找到。

内容哈希用于发现源码变化，包含尚未提交的修改。地图过期时，正式查询会拒绝执行，需要先复核相关关系并重建。HTML 展示的是生成时的快照，不会实时监控源码。

## 轻量校验

优先复用项目适用的构建／编译、类型检查命令，以及已有的相关测试。一个命令覆盖构建与类型检查时，只需执行一次。实际行为无法通过这些检查观察时，再做一项针对性的运行验证。

默认不要求新建大量测试。辅助脚本检查实际文件变化是否符合声明的计划；agent 仍需阅读最终 diff，排除同一文件内的无关修改，并保护用户已有改动。

## 能力边界

- 语言无关的分析由 agent 完成。Python 脚本负责快照、证据位置与结构校验、已记录关系的查询、HTML 渲染和文件范围检查，不会自动推导全部依赖。
- 地图会记录已阅读文件、排除范围和未知项。动态装配、部署环境值、生成代码、仓库外消费者可能需要补充证据。
- 地图未过期不代表覆盖完整；通过构建、类型和范围检查，也不代表业务逻辑必然正确，或 agent 绝不会改错。
- 技能已在 Codex 中实际使用。其他 coding agent 需要支持相应的技能发现和脚本执行，安装与自动触发方式可能不同。技能正文与示例界面目前使用中文。

底层格式见[关系协议](skills/project-map/references/graph-schema.md)与[轻量变更协议](skills/change-with-context/references/change-protocol.md)。

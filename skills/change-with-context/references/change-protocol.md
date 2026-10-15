# 轻量变更协议 v1

只保留本次任务需要的信息，不对每个 diff hunk 建立记录。协议供 agent 阅读；脚本只校验文件操作和基线身份，检查结果由 agent 根据真实命令输出填写。

## change.json

```json
{
  "schema_version": 1,
  "base_snapshot_id": "从 baseline.json 的 snapshot.id 复制",
  "task": "为回复接口增加 messages，同时保留 reply 的旧调用方式",
  "requirements": ["响应提供 messages 数组，新客户端能消费该数组。"],
  "preserve": ["原有 reply 字段与旧客户端调用继续有效。"],
  "files": [
    {"path": "api/server.ts", "action": "modify", "reason": "提供新字段并保留旧字段。", "evidence": "api/server.ts:24 定义响应结构。"},
    {"path": "web/client.ts", "action": "modify", "reason": "适配新的 messages 数组。", "evidence": "web/client.ts:18 消费接口响应。"},
    {"path": "infra/store.ts", "action": "verify", "reason": "响应转换不改变持久化格式，已阅读写入实现。", "evidence": "infra/store.ts:30 写入原有记录。"}
  ],
  "checks": [
    {"kind": "build", "command": "项目的实际构建命令", "result": "pending", "note": "待执行。"},
    {"kind": "typecheck", "command": "", "result": "not_applicable", "note": "项目没有独立类型检查，构建包含类型检查。"}
  ],
  "unresolved": []
}
```

- `schema_version` 必须为 1。`base_snapshot_id` 必须与未被覆盖的任务基线匹配。
- `task` 是本次需求摘要；`requirements` 是可观察的完成条件；`preserve` 是已明确要保留的行为。无需另设需求编号或完整验收矩阵。
- `files` 使用相对项目根的 POSIX 路径，禁止目录通配符。每条有 `path`、`action`、`reason`、`evidence`，路径不得重复。
- `modify`：任务开始时存在，任务结束时内容变化。
- `add`：任务开始时不存在，任务结束时出现。
- `delete`：任务开始时存在，任务结束时消失。
- `verify`：该关联经阅读/核验后无需修改，内容应与任务开始时一致。
- 重命名记录旧路径的 `delete` 与新路径的 `add`。有内容变化时仍需复核实际 diff。
- `evidence` 是简短源码位置和观察事实；新文件可以指向产生它的接口定义或已核验的需求入口。脚本仅检查该字段非空，不证明理由和源码语义正确。
- 清单可根据发现的真实影响更新；需要修改但最终证明不用改时，改为 `verify` 并写依据。不能重新定义用户需求、重新捕获基线或仅为消除异常扩大清单。
- `checks` 的 `kind` 为 `build`、`typecheck`、`test` 或 `runtime`；`result` 为 `pending`、`passed`、`failed`、`not_applicable` 或 `preexisting_failure`。不存在独立命令时给出具体原因。同一实际命令覆盖多项检查时注明复用，不重复运行。只有被直接影响时才做针对性运行验证。
- `unresolved` 记录实际未确认边界；不为假想问题追加通用清单。

## baseline.json 和范围报告

`capture` 要求 project-map v1 的 `graph.json`、`snapshot.json` 与当前源码一致，保存未修改前的文件清单和哈希、快照 ID、时间、项目路径以及 Git 已有改动文件名。输出不能已存在。它不提交、暂存、回滚或保存完整源码。

`check` 对照任务基线计算新增、删除、修改；比较全部清单内文件，不只比较计划文件。所以清单外的源码变更也会被发现。任务开始前已有的修改只在本次再次变化时进入本次差异，不会误报为 agent 的改动。

范围报告包含：

- `changes`：实际新增、修改、删除文件。
- `unexpected`：不在修改清单中的变化（包括 `verify` 文件发生变化）。
- `missing`：标记必须修改、但实际没有对应变化的文件。
- `wrong_action`：实际变化类型与计划不符。
- `uncovered`：计划涉及的既有/结束时文件不在扫描清单中。
- `review_preexisting`：本次又修改了任务开始时已经有 Git 改动的文件，需要复核同文件合并。不是自动失败，也不证明已有修改被完整保留。
- `inventory_changed`：扫描方式或排除规则发生变化，需要复核基线覆盖范围。
- `scope_ok`：是否没有以上范围异常；它不代表编译、类型或业务需求已验证。

任务进行中其他人新增的改动也会出现在实际差异里；异常需要核实归属，不能据此自动恢复整份文件。

遵循 project-map 的默认排除规则，包括依赖/构建目录、凭证文件、符号链接和超过 2 MiB 的文件。排除文件的变化无法由该范围报告证明；有关文件若必须修改，应单独复核并说明脚本覆盖边界，不能将异常静默忽略。

通过 `--project-map-skill <目录>` 定位非同级安装的第一技能。项目移动后，可以在 `check` 使用 `--root <新路径>`；不改写原基线。退出码：0 为范围正常，2 为范围异常，1 为输入/依赖错误。脚本不会执行 `checks` 中的字符串命令。

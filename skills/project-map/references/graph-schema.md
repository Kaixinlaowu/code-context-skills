# 关系索引协议 v1

分析输入为 UTF-8 JSON。`build` 将快照元数据写入 `graph.json`；不手动伪造快照。ID 在同一项目内保持稳定，建议 `module:api`、`file:src/server.ts`、`contract:http:POST:/replies`。

```json
{
  "schema_version": 1,
  "project": "示例项目",
  "overview": "入口与业务链的源码依据，重要边界及约定。",
  "coverage": {
    "reviewed_files": ["src/server.ts", "src/client.ts"],
    "unresolved": ["仓库之外的 HTTP 消费者无法确认。"]
  },
  "nodes": [
    {"id": "module:api", "kind": "module", "label": "接口服务", "summary": "负责 HTTP 接入。"},
    {"id": "module:ui", "kind": "module", "label": "前端", "summary": "发起请求并显示结果。"},
    {"id": "file:src/server.ts", "kind": "file", "label": "server.ts", "path": "src/server.ts", "module": "module:api", "summary": "定义 HTTP 响应。"},
    {"id": "file:src/client.ts", "kind": "file", "label": "client.ts", "path": "src/client.ts", "module": "module:ui"},
    {"id": "contract:http:POST:/replies", "kind": "contract", "label": "POST /replies", "module": "module:api", "summary": "响应字段 reply 为字符串。"}
  ],
  "edges": [
    {"source": "file:src/client.ts", "target": "contract:http:POST:/replies", "kind": "contract", "status": "confirmed", "label": "消费响应", "evidence": [{"path": "src/client.ts", "line": 1, "note": "请求该路由并读取 reply。"}]},
    {"source": "contract:http:POST:/replies", "target": "file:src/server.ts", "kind": "contract", "status": "confirmed", "label": "定义于", "evidence": [{"path": "src/server.ts", "line": 1, "note": "该文件提供此路由与响应结构。"}]}
  ]
}
```

## 节点

- 必需：`id`、`kind`、`label`。可选：`summary`。
- `kind`：`module`、`file`、`contract`、`external`。
- `file` 必需 `path`，使用相对项目根的 POSIX 路径。`module` 指向已有模块 ID。
- 文件和契约可以归属模块；跨模块共享契约可以不归属模块，此时在模块概览中独立展示。
- `external` 表示仓库外依赖，不能假定已分析其实现。
- 外部调用方已知但实现不可访问时，用 `external` 节点记录其对契约的依赖；连线确认程度取决于已有源码/配置证据，无法确认的外部调用方仅记入 `unresolved`。
- 文件节点及证据涉及的文件均须出现在 `coverage.reviewed_files`；这里只记录实际阅读或通过语言工具核验的文件。

## 边与方向

所有边是 **依赖方 source → 被依赖方 target**，不混用“执行顺序”或“数据流向”。

`kind`：`import`、`call`、`contract`、`event`、`read`、`write`、`config`、`depends-on`。

- 消费者 → 接口契约，契约 → 提供该接口的实现。事件订阅方 → 事件契约，事件契约 → 发布实现。这样逆向查询实现时，能够走到消费者。
- 读写方 → 数据契约，契约 → 格式定义或负责实现。配置使用方 → 配置契约。必须说明实际语义，不凭名字推断。
- 文件归属使用节点的 `module`，不把包含关系混进依赖边。
- `label` 可补充精确含义；`status` 为 `confirmed`（源码/工具已核实）或 `inferred`（有迹象，尚未证实）。脚本不会替 agent 作语义判断。
- 每条边的 `evidence` 至少一项，包含 `path`、1 起始的 `line`、说明观察事实的 `note`。可选 `end_line`。路径必须在快照与已阅读范围中，行号必须存在。
- 共享契约的提供方和使用方都要有各自证据。若两端是否匹配尚不明确，相关连接应标为 `inferred` 并解释未知项。
- 模块视图由文件/契约归属聚合，不用另外复制一套相同的模块边。只有仅能确认模块级关系时才直接使用模块节点。

## 覆盖与新鲜度

`coverage.reviewed_files` 必需。`coverage.unresolved` 为尚未覆盖的目录、动态机制、仓库外边界或语义不确定项的字符串列表。即使没有未知项也应给出空数组，而不是省略覆盖说明。

`snapshot.json` 包含文件哈希、Git HEAD、时间、扫描方式、排除规则和被排除文件。哈希包含未提交文件；HEAD 不单独决定新鲜度。默认不读取符号链接与密钥文件。Git 忽略文件不会进入清单，非 Git 遍历没有完整 `.gitignore` 解析能力；必须在分析结论中保留这一边界。

`check` 会重新清点并比对新增/删除/修改以及快照身份。源码不变时，HEAD 改变不使内容快照失效。索引过期需要复核关系后重建，不能把旧关系重新盖上新日期。

## 产物与消费

- `graph.json`：分析数据及 `snapshot` 摘要，后续 skill 的交换协议。
- `snapshot.json`：可重新核验的完整扫描清单，和图一起保留。
- `architecture.md`：职责、关系数量、入口与业务链、覆盖范围及未知项的摘要。
- `project-map.html`：嵌入图和生成时的快照摘要，无网络请求，无 CDN，不读取浏览器外源码。支持模块聚合、文件/契约视图、关系过滤、搜索、详情、缩放及一跳邻域。
- `analysis.json`：agent 的分析输入，保留便于刷新，不要求后续 agent 全量加载。

只保存理解关系所需的信息。HTML/JSON 不包含密钥、原始私有业务数据或整份源码。当前页面不进行自动修改，不表示未来每次请求必然加载此 skill。

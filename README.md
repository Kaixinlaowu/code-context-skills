# Code Context Skills

English | [简体中文](README.zh-CN.md)

Help coding agents understand how a project connects, then keep cross-module changes consistent.

This repository contains two complementary skills: one builds an evidence-backed project map; the other uses that map and current source code to make scoped changes with lightweight validation.

| Skill | Purpose | When to use it |
| --- | --- | --- |
| [project-map](skills/project-map/SKILL.md) | Analyze modules, file references, and shared contracts; generate an offline HTML relationship map. | Understand architecture, inspect upstream/downstream relationships, or refresh a map. |
| [change-with-context](skills/change-with-context/SKILL.md) | Trace an actual change's impact, adapt the necessary code, and check the final scope. | Change shared APIs, events, configuration, data formats, or behavior across modules. |

`project-map` can be used independently. `change-with-context` requires `project-map`.

## The problem

An agent changes an API response, but misses the frontend that reads it. It renames an event, but leaves a subscriber unchanged. It updates a stored format, but forgets the reader.

Import graphs alone do not capture these connections. These skills ask the agent to examine both file references and shared contracts, record source evidence, and decide which consumers actually need adaptation. A related file is a candidate to inspect, not automatically a file to edit.

## Installation

The skills are packaged for Codex. You need Python 3, permission to read the target repository and run the helper scripts, and the project's existing tools for any applicable build or type checks. The helper scripts use only the Python standard library. Git is used for file inventory when available.

### With Codex's skill installer

Ask Codex:

```text
$skill-installer Install skills/project-map and skills/change-with-context
from https://github.com/Kaixinlaowu/code-context-skills.
```

### Manual installation

```bash
git clone https://github.com/Kaixinlaowu/code-context-skills.git
```

Copy the `project-map` and `change-with-context` folders from `code-context-skills/skills/` into your Codex skills directory. Use `$CODEX_HOME/skills` if configured; otherwise use `~/.codex/skills` (`%USERPROFILE%\.codex\skills` on Windows).

Keep the two folders side by side:

```text
<skills-root>/
├── project-map/
│   └── SKILL.md
└── change-with-context/
    └── SKILL.md
```

Copy the entire folders, including their scripts, references, and assets. If either skill is already installed, inspect the existing version before replacing it. Start a new turn after installation so Codex can discover the skills.

## Usage

Run these requests in the target project's context, or provide its path explicitly.

### 1. Understand the project

```text
$project-map Analyze this repository's modules, entry points, file references,
and shared API, event, configuration, and data contracts. Record source evidence
and unknowns, then generate an offline HTML map in .agent-context/.
```

The agent reads the source and uses the project's existing compiler, language tools, or dependency commands when available. It records confirmed and inferred relationships separately, with file paths, line numbers, and coverage boundaries.

Open the generated `.agent-context/project-map.html` in a browser. The viewer includes module and file/contract views, search, relationship filters, source evidence details, pan/zoom, and one-hop filtering.

[Download the example HTML](examples/project-map-demo.html) and open it locally to try the viewer. It contains a synthetic Reply Service, not an analysis of a real application. GitHub's file view displays the HTML source. No server, CDN, or network connection is needed to view it.

### 2. Make a change that crosses a boundary

```text
$change-with-context Add a messages field to the reply API while preserving
the existing reply field. Inspect providers and consumers, adapt only the code
required by this change, and run the applicable existing build and type checks.
```

The agent checks map freshness, records a pre-edit baseline, and identifies files to modify, add, delete, or verify without editing. It follows the affected contracts until it reaches a verified boundary whose behavior remains stable. After implementation, it reviews the diff, runs the applicable existing checks and the scope checker, then refreshes the map.

## Keep small changes small

`change-with-context` is intended for shared boundaries and cross-module behavior. A local configuration value, documentation edit, formatting change, or internal constant adjustment normally stays an ordinary edit.

When impact is unclear, the agent first inspects the target and its direct references. It enters the full workflow only after finding a shared boundary or another affected module. You can also explicitly invoke it when you want impact tracking.

Automatic selection depends on the host agent's skill support and judgment. The trigger descriptions guide selection; they are not a hard execution hook.

## Generated artifacts

By default, artifacts stay in the target project's `.agent-context/` directory:

```text
.agent-context/
├── snapshot.json            # File inventory, content hashes, scan boundaries
├── analysis.json            # Agent-authored relationships and source evidence
├── graph.json               # Validated relationship index
├── architecture.md          # Architecture summary and analysis boundaries
├── project-map.html         # Standalone interactive viewer
└── changes/<task>/
    ├── baseline.json        # Immutable pre-edit snapshot for the task
    ├── change.json          # Requirements, affected files, verification records
    └── scope-report.json    # Actual file changes compared with the plan
```

Graph arrows always mean **dependent → dependency**. Looking up consumers follows the reverse direction; a consumer connected through a contract node may require two hops.

Content hashes detect source changes, including uncommitted edits. Formal queries reject a stale map until its affected relationships are reviewed and rebuilt. The HTML is a generated snapshot and does not monitor source files live.

## Lightweight validation

Validation reuses the project's applicable build/compile and type-check commands, plus relevant existing tests. If one command covers both build and type checking, it only needs to run once. A focused runtime check is appropriate when the changed behavior cannot be observed through those checks.

There is no default requirement to create a large test suite. The scope helper compares actual changes against the declared plan; the agent still reviews the final diff for unrelated edits within a file and preserves pre-existing user changes.

## Scope and limitations

- Language independent analysis is performed by the agent. The Python helpers manage snapshots, validate evidence locations and structure, query recorded relationships, render HTML, and check file scope; they do not automatically infer all dependencies.
- Maps state their reviewed files, exclusions, and unknowns. Dynamic wiring, deployment-specific values, generated code, and external consumers may need additional evidence.
- A fresh map does not prove complete coverage. Passing build, type, and scope checks does not prove business correctness or guarantee that the agent cannot make a mistake.
- The skills have been exercised in Codex. Other coding agents need compatible skill discovery and script execution; installation and automatic selection can differ. Skill instructions and the demo UI are currently in Chinese.

For the underlying formats, see the [relationship schema](skills/project-map/references/graph-schema.md) and [change protocol](skills/change-with-context/references/change-protocol.md).

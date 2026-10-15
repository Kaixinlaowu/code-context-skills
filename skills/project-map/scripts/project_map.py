#!/usr/bin/env python3
"""Snapshot, validate, render and query source-backed project maps. Python stdlib only."""

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import sys
from datetime import datetime, timezone

SKIP_DIRS = {'.git', '.agent-context', 'node_modules', 'vendor', '.venv', 'venv',
             '__pycache__', 'dist', 'build', 'coverage', '.next', '.cache'}
EDGE_KINDS = {'import', 'call', 'contract', 'event', 'read', 'write', 'config', 'depends-on'}
MAX_BYTES = 2 * 1024 * 1024


def load(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def save(path, value):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def relative_path(value):
    if not isinstance(value, str) or not value or '\\' in value:
        raise ValueError('Use a nonempty relative POSIX path: ' + repr(value))
    path = PurePosixPath(value)
    if path.is_absolute() or '..' in path.parts or ':' in value or str(path) != value:
        raise ValueError('Invalid relative path: ' + value)
    return value


def git(root, *args):
    result = subprocess.run(['git', '-C', str(root), *args], capture_output=True, check=False)
    return result.stdout if result.returncode == 0 else None


def scan(root, excludes):
    root = Path(root).resolve()
    if not root.is_dir():
        raise ValueError('Project root is not a directory: ' + str(root))
    files, skipped = {}, []
    listed = git(root, 'ls-files', '--cached', '--others', '--exclude-standard', '-z') if shutil.which('git') else None
    if listed is not None:
        paths = sorted({os.fsdecode(p) for p in listed.split(b'\0') if p})
        mode = 'git-tracked-and-unignored'
    else:
        paths = []
        for directory, dirs, names in os.walk(root, followlinks=False):
            dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS and not (Path(directory) / d).is_symlink()
                             and not any((Path(directory) / d).relative_to(root).as_posix() == e or
                                         (Path(directory) / d).relative_to(root).as_posix().startswith(e + '/') for e in excludes))
            paths.extend((Path(directory) / name).relative_to(root).as_posix() for name in sorted(names))
        mode = 'filesystem-default-exclusions'
    for rel in paths:
        relative_path(rel)
        parts = PurePosixPath(rel).parts
        if any(p in SKIP_DIRS for p in parts[:-1]) or any(rel == e or rel.startswith(e + '/') for e in excludes):
            continue
        path = root / rel
        if any((root.joinpath(*parts[:i + 1])).is_symlink() for i in range(len(parts))):
            skipped.append({'path': rel, 'reason': 'symlink'})
            continue
        name = path.name.lower()
        secret = (name == '.env' or (name.startswith('.env.') and not name.endswith(('.example', '.sample', '.template')))
                  or name.endswith(('.pem', '.key', '.p12', '.pfx')) or name in {'id_rsa', 'id_ed25519'})
        if secret:
            skipped.append({'path': rel, 'reason': 'credential-file'})
            continue
        if not path.is_file():
            continue
        try:
            size = path.stat().st_size
            if size > MAX_BYTES:
                skipped.append({'path': rel, 'reason': 'larger-than-2MiB'})
                continue
            files[rel] = {'sha256': hashlib.sha256(path.read_bytes()).hexdigest(), 'size': size}
        except OSError:
            skipped.append({'path': rel, 'reason': 'unreadable'})
    head = git(root, 'rev-parse', 'HEAD') if shutil.which('git') else None
    return {'root': str(root), 'head': head.decode().strip() if head else None, 'mode': mode,
            'files': files, 'excluded_files': skipped, 'exclude_paths': excludes,
            'excluded_directories': sorted(SKIP_DIRS), 'max_file_bytes': MAX_BYTES}


def snapshot_id(snapshot):
    return digest({k: snapshot[k] for k in ('files', 'exclude_paths', 'mode', 'excluded_directories', 'max_file_bytes')})


def compare(snapshot, root):
    if snapshot.get('id') != snapshot_id(snapshot):
        raise ValueError('Snapshot identity does not match its contents')
    current = scan(root or snapshot['root'], snapshot['exclude_paths'])
    old, new = snapshot['files'], current['files']
    added, deleted = sorted(new.keys() - old.keys()), sorted(old.keys() - new.keys())
    modified = sorted(p for p in old.keys() & new.keys() if old[p] != new[p])
    return {'fresh': not (added or deleted or modified) and snapshot_id(current) == snapshot['id'],
            'added': added, 'deleted': deleted, 'modified': modified,
            'head_changed': current['head'] != snapshot['head'], 'root': current['root']}


def validate(graph, snapshot, root):
    if graph.get('schema_version') != 1:
        raise ValueError('schema_version must be 1')
    for key in ('project', 'overview'):
        if not isinstance(graph.get(key), str) or not graph[key].strip():
            raise ValueError(key + ' must be a nonempty string')
    coverage = graph['coverage']
    reviewed = coverage['reviewed_files']
    if not isinstance(reviewed, list) or any(not isinstance(p, str) for p in reviewed):
        raise ValueError('coverage.reviewed_files must be a path list')
    for path in reviewed:
        relative_path(path)
        if path not in snapshot['files']:
            raise ValueError('Reviewed file absent from snapshot: ' + path)
    if not isinstance(coverage.get('unresolved'), list) or any(not isinstance(x, str) for x in coverage['unresolved']):
        raise ValueError('coverage.unresolved must be a string list')
    nodes = graph['nodes']
    if not isinstance(nodes, list) or not nodes:
        raise ValueError('nodes must be a nonempty list')
    indexed = {}
    for node in nodes:
        if not isinstance(node.get('id'), str) or not node['id'] or node['id'] in indexed:
            raise ValueError('Missing or duplicate node id')
        if node.get('kind') not in {'module', 'file', 'contract', 'external'} or not isinstance(node.get('label'), str):
            raise ValueError('Invalid node kind or label: ' + node['id'])
        if 'summary' in node and not isinstance(node['summary'], str):
            raise ValueError('Node summary must be text: ' + node['id'])
        if node['kind'] == 'file' and node.get('path') not in reviewed:
            raise ValueError('File node must be reviewed: ' + node['id'])
        indexed[node['id']] = node
    for node in nodes:
        if 'module' in node and (node['module'] not in indexed or indexed[node['module']]['kind'] != 'module'):
            raise ValueError('Unknown module on node: ' + node['id'])
    lines = {}
    if not isinstance(graph['edges'], list):
        raise ValueError('edges must be a list')
    for edge in graph['edges']:
        if edge.get('source') not in indexed or edge.get('target') not in indexed:
            raise ValueError('Edge endpoint does not exist')
        if edge.get('kind') not in EDGE_KINDS or edge.get('status') not in {'confirmed', 'inferred'}:
            raise ValueError('Invalid edge kind or status')
        if 'label' in edge and not isinstance(edge['label'], str):
            raise ValueError('Edge label must be text')
        if not isinstance(edge.get('evidence'), list) or not edge['evidence']:
            raise ValueError('Every edge needs source evidence')
        for item in edge['evidence']:
            path = item['path']
            if path not in reviewed:
                raise ValueError('Evidence file must be reviewed: ' + path)
            if path not in lines:
                lines[path] = len((Path(root) / path).read_text(encoding='utf-8-sig', errors='replace').splitlines())
            start, end = item.get('line'), item.get('end_line', item.get('line'))
            if type(start) is not int or type(end) is not int or not 1 <= start <= end <= lines[path]:
                raise ValueError('Evidence line outside file: ' + path)
            if not isinstance(item.get('note'), str) or not item['note'].strip():
                raise ValueError('Evidence needs an observation note: ' + path)


def architecture(graph):
    snap, coverage = graph['snapshot'], graph['coverage']
    rows = ['# ' + graph['project'] + ' 项目关系地图', '', graph['overview'], '',
            '## 源码快照', '', '- 生成时间：' + snap['created_at'],
            '- Git HEAD：' + (snap['head'] or '未记录'),
            f"- 清单 {snap['file_count']} 文件，已阅读 {len(coverage['reviewed_files'])} 文件。已阅读不代表所有关系均已确认。",
            '- 箭头方向：依赖方 → 被依赖方。', '', '## 模块职责', '']
    for node in graph['nodes']:
        if node['kind'] == 'module':
            rows.append('- **' + node['label'] + '**：' + node.get('summary', '参见图中关系。'))
    confirmed = sum(e['status'] == 'confirmed' for e in graph['edges'])
    rows.extend(['', '## 覆盖与局限', '', f"- {confirmed} 条已确认关系，{len(graph['edges']) - confirmed} 条待核实关系。",
                 '- 扫描方式：' + snap['mode'], '- 排除目录：' + ', '.join(snap['excluded_directories']),
                 '- 排除路径：' + (', '.join(snap['exclude_paths']) or '无额外路径'),
                 '- 排除符号链接、凭证文件及超过 2 MiB 的文件。',
                 '- Git 忽略文件不在清单中；非 Git 模式不完整解析 .gitignore。'])
    rows.extend('- ' + x for x in coverage['unresolved'])
    rows.extend(['', '## 使用', '', '图见 `project-map.html`，索引见 `graph.json`。查询前运行 `check`；HTML 只展示生成时状态。', ''])
    return '\n'.join(rows)


def get_map(directory, root):
    directory = Path(directory)
    graph, snapshot = load(directory / 'graph.json'), load(directory / 'snapshot.json')
    if graph['snapshot']['id'] != snapshot['id']:
        raise ValueError('Graph and snapshot belong to different analysis runs')
    state = compare(snapshot, root)
    return graph, snapshot, state


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    subs = parser.add_subparsers(dest='command', required=True)
    snap = subs.add_parser('snapshot')
    snap.add_argument('--root', required=True)
    snap.add_argument('--out', required=True)
    snap.add_argument('--exclude', action='append', default=[])
    build = subs.add_parser('build')
    build.add_argument('--snapshot', required=True)
    build.add_argument('--analysis', required=True)
    build.add_argument('--out', required=True)
    build.add_argument('--root')
    for name in ('check', 'query'):
        command = subs.add_parser(name)
        command.add_argument('--map', required=True)
        command.add_argument('--root')
        if name == 'query':
            command.add_argument('--node', required=True)
            command.add_argument('--direction', choices=['dependencies', 'dependents', 'both'], default='both')
            command.add_argument('--depth', type=int, default=1)
    args = parser.parse_args()
    if args.command == 'snapshot':
        snapshot = scan(args.root, sorted({relative_path(p.rstrip('/')) for p in args.exclude}))
        snapshot['created_at'] = datetime.now(timezone.utc).isoformat(timespec='seconds')
        snapshot['id'] = snapshot_id(snapshot)
        save(args.out, snapshot)
        print(json.dumps({'snapshot': str(Path(args.out).resolve()), 'files': len(snapshot['files']),
                          'excluded_files': len(snapshot['excluded_files']), 'mode': snapshot['mode']}))
    elif args.command == 'build':
        snapshot, graph = load(args.snapshot), load(args.analysis)
        state = compare(snapshot, args.root)
        if not state['fresh']:
            raise ValueError('Source changed after snapshot: ' + json.dumps(state, ensure_ascii=False))
        validate(graph, snapshot, state['root'])
        graph['snapshot'] = {k: snapshot[k] for k in ('id', 'created_at', 'head', 'mode', 'excluded_directories', 'exclude_paths')}
        graph['snapshot']['file_count'] = len(snapshot['files'])
        graph['snapshot']['excluded_files'] = snapshot['excluded_files']
        out = Path(args.out)
        save(out / 'graph.json', graph)
        save(out / 'snapshot.json', snapshot)
        (out / 'architecture.md').write_text(architecture(graph), encoding='utf-8')
        template = (Path(__file__).resolve().parent.parent / 'assets' / 'viewer.html').read_text(encoding='utf-8')
        embedded = json.dumps(graph, ensure_ascii=False).replace('<', '\\u003c').replace('&', '\\u0026').replace('\u2028', '\\u2028').replace('\u2029', '\\u2029')
        (out / 'project-map.html').write_text(template.replace('__PROJECT_MAP_DATA__', embedded), encoding='utf-8')
        print(json.dumps({'output': str(out.resolve()), 'nodes': len(graph['nodes']), 'edges': len(graph['edges'])}))
    else:
        graph, snapshot, state = get_map(args.map, args.root)
        if args.command == 'check':
            print(json.dumps(state, ensure_ascii=False, indent=2))
            return 0 if state['fresh'] else 2
        if not state['fresh']:
            raise ValueError('Map is stale; review relationships before querying: ' + json.dumps(state, ensure_ascii=False))
        if args.depth < 1:
            raise ValueError('depth must be at least 1')
        matches = [n for n in graph['nodes'] if n['id'] == args.node or n.get('path') == args.node]
        if len(matches) != 1:
            raise ValueError('node must resolve to one exact ID or file path')
        scope = {matches[0]['id']}
        if matches[0]['kind'] == 'module':
            scope.update(n['id'] for n in graph['nodes'] if n.get('module') == matches[0]['id'])
        selected, visited, included = scope, set(scope), set()
        for _ in range(args.depth):
            following = set()
            for index, edge in enumerate(graph['edges']):
                if args.direction in {'dependencies', 'both'} and edge['source'] in selected:
                    included.add(index)
                    following.add(edge['target'])
                if args.direction in {'dependents', 'both'} and edge['target'] in selected:
                    included.add(index)
                    following.add(edge['source'])
            selected = following - visited
            visited.update(following)
            if not selected:
                break
        print(json.dumps({'fresh': True, 'scope': matches[0]['id'], 'direction': args.direction, 'depth': args.depth,
                          'nodes': [n for n in graph['nodes'] if n['id'] in visited],
                          'edges': [e for i, e in enumerate(graph['edges']) if i in included]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (ValueError, KeyError, TypeError, OSError) as error:
        print('project-map: ' + str(error), file=sys.stderr)
        sys.exit(1)

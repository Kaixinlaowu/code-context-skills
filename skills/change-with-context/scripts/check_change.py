#!/usr/bin/env python3
"""Capture a project-map baseline and check task file scope. Python stdlib only."""

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import runpy
import sys


def helpers(skill):
    directory = Path(skill) if skill else Path(__file__).resolve().parents[2] / 'project-map'
    script = directory / 'scripts/project_map.py'
    if not script.is_file():
        raise ValueError('project-map is required; use --project-map-skill with its directory')
    return runpy.run_path(str(script))


def nonempty(value, name):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(name + ' must be nonempty text')


def plan_files(plan, baseline, api):
    if plan.get('schema_version') != 1 or baseline.get('schema_version') != 1:
        raise ValueError('schema_version must be 1')
    if plan.get('base_snapshot_id') != baseline['snapshot']['id']:
        raise ValueError('Plan and task baseline belong to different snapshots')
    nonempty(plan.get('task'), 'task')
    for name in ('requirements', 'preserve', 'unresolved'):
        if not isinstance(plan.get(name), list) or any(not isinstance(x, str) for x in plan[name]):
            raise ValueError(name + ' must be a text list')
    if not plan['requirements']:
        raise ValueError('At least one observable requirement is needed')
    if not isinstance(plan.get('files'), list):
        raise ValueError('files must be a list')
    indexed = {}
    for entry in plan['files']:
        path = api['relative_path'](entry['path'])
        if path in indexed:
            raise ValueError('Duplicate plan path: ' + path)
        if entry.get('action') not in {'modify', 'add', 'delete', 'verify'}:
            raise ValueError('Invalid action for ' + path)
        nonempty(entry.get('reason'), 'reason for ' + path)
        nonempty(entry.get('evidence'), 'evidence for ' + path)
        indexed[path] = entry['action']
    return indexed


def preexisting(root, snapshot, api):
    if snapshot['mode'] != 'git-tracked-and-unignored':
        return []
    names = set()
    for args in [('diff', '--name-only', '-z'), ('diff', '--cached', '--name-only', '-z'),
                 ('ls-files', '--others', '--exclude-standard', '-z')]:
        raw = api['git'](root, *args)
        if raw:
            names.update(os.fsdecode(p) for p in raw.split(b'\0') if p)
    return sorted(names & snapshot['files'].keys())


def capture(args, api):
    output = Path(args.out)
    if output.exists():
        raise ValueError('Baseline already exists; use a new task directory, never overwrite it')
    graph, snapshot, state = api['get_map'](args.map, args.root)
    if graph.get('schema_version') != 1:
        raise ValueError('A project-map v1 graph is required')
    if not state['fresh']:
        raise ValueError('Project map is stale; review relationships and rebuild before capture')
    baseline = {'schema_version': 1, 'captured_at': datetime.now(timezone.utc).isoformat(timespec='seconds'),
                'root': state['root'], 'snapshot': snapshot,
                'preexisting_changes': preexisting(state['root'], snapshot, api)}
    api['save'](output, baseline)
    print('Captured task baseline: ' + str(output.resolve()))
    return 0


def check(args, api):
    baseline, plan = api['load'](args.baseline), api['load'](args.plan)
    planned = plan_files(plan, baseline, api)
    snapshot = baseline['snapshot']
    root = args.root or baseline['root']
    if snapshot.get('id') != api['snapshot_id'](snapshot):
        raise ValueError('Baseline snapshot identity does not match its contents')
    current = api['scan'](root, snapshot['exclude_paths'])
    old, new = snapshot['files'], current['files']
    state = {'added': sorted(new.keys() - old.keys()), 'deleted': sorted(old.keys() - new.keys()),
             'modified': sorted(p for p in old.keys() & new.keys() if old[p] != new[p])}
    actual = {p: action for action, key in [('add', 'added'), ('delete', 'deleted'), ('modify', 'modified')]
              for p in state[key]}
    expected = {p: action for p, action in planned.items() if action != 'verify'}
    unexpected = sorted(actual.keys() - expected.keys())
    missing = sorted(expected.keys() - actual.keys())
    wrong = [{'path': p, 'expected': expected[p], 'actual': actual[p]}
             for p in sorted(expected.keys() & actual.keys()) if expected[p] != actual[p]]
    uncovered = []
    excluded = {entry['path'] for entry in snapshot['excluded_files'] + current['excluded_files']}
    for path, action in planned.items():
        was_scanned = path in snapshot['files']
        old_or_new = was_scanned or path in state['added']
        if (not old_or_new or path in excluded
                or (action in {'modify', 'delete', 'verify'} and not was_scanned)
                or (action == 'delete' and (Path(root) / path).exists())):
            uncovered.append(path)
    inventory_changed = any(snapshot[k] != current[k] for k in
                            ('mode', 'exclude_paths', 'excluded_directories', 'max_file_bytes'))
    report = {'scope_ok': not (unexpected or missing or wrong or uncovered or inventory_changed),
              'base_snapshot_id': snapshot['id'],
              'changes': {k: state[k] for k in ('added', 'modified', 'deleted')},
              'unexpected': unexpected, 'missing': missing, 'wrong_action': wrong,
              'uncovered': sorted(uncovered), 'inventory_changed': inventory_changed,
              'review_preexisting': sorted(actual.keys() & set(baseline['preexisting_changes'])),
              'limits': 'File scope only, within project-map inventory; review diff and run project checks separately.'}
    if args.out:
        target = Path(args.out).resolve()
        if target in {Path(args.baseline).resolve(), Path(args.plan).resolve()}:
            raise ValueError('Report output cannot overwrite the baseline or plan')
        api['save'](target, report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report['scope_ok'] else 2


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    capture_parser = commands.add_parser('capture')
    capture_parser.add_argument('--root', required=True)
    capture_parser.add_argument('--map', required=True)
    capture_parser.add_argument('--out', required=True)
    check_parser = commands.add_parser('check')
    check_parser.add_argument('--baseline', required=True)
    check_parser.add_argument('--plan', required=True)
    check_parser.add_argument('--root')
    check_parser.add_argument('--out')
    for command in (capture_parser, check_parser):
        command.add_argument('--project-map-skill')
    args = parser.parse_args()
    api = helpers(args.project_map_skill)
    return capture(args, api) if args.command == 'capture' else check(args, api)


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (ValueError, KeyError, TypeError, OSError) as error:
        print('change-with-context: ' + str(error), file=sys.stderr)
        sys.exit(1)

#!/usr/bin/env python3
"""Local display-text patcher. No account, gateway, or session configuration access."""
from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import plistlib
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parent
SUPPORTED = {'3.1623.0'}
ASSETS = Path('Contents/Resources/ion-dist/assets/v1')
LITERAL = r'"(?:[^"\\]|\\.)*"'
MESSAGES = re.compile(r'(?P<prefix>defaultMessage\s*:\s*)(?P<text>' + LITERAL + r')(?P<between>\s*,\s*id\s*:\s*)(?P<id>' + LITERAL + r')')
DEFAULT_STATE = Path.home() / 'Library/Application Support/ClaudeZhCnPlus'


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def write_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + '.tmp')
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    os.replace(temp, path)


def message_signature(message):
    """Conservatively validate ICU arguments, plural branches, and rich-text tags."""
    signatures = []
    index = 0

    def spaces():
        nonlocal index
        while index < len(message) and message[index].isspace():
            index += 1

    def token(pattern):
        nonlocal index
        spaces()
        match = re.match(pattern, message[index:])
        if not match:
            raise ValueError('Malformed ICU argument')
        index += len(match[0])
        return match[0]

    def expect(char):
        nonlocal index
        spaces()
        if index >= len(message) or message[index] != char:
            raise ValueError('Unbalanced ICU message')
        index += 1

    def body(nested=False):
        nonlocal index
        while index < len(message):
            char = message[index]
            if char == "'" and index + 1 < len(message):
                following = message[index + 1]
                if following == "'":
                    index += 2
                    continue
                if following in '{}<#':
                    index += 1
                    while index < len(message):
                        if message[index] == "'":
                            if message[index:index + 2] == "''":
                                index += 2
                                continue
                            index += 1
                            break
                        index += 1
                    continue
            if char == '}':
                if not nested:
                    raise ValueError('Unexpected closing brace')
                index += 1
                return
            if char != '{':
                index += 1
                continue
            index += 1
            name = token(r'[A-Za-z_0-9][\w.-]*')
            spaces()
            if index < len(message) and message[index] == '}':
                index += 1
                signatures.append((name, 'argument', (), ''))
                continue
            expect(',')
            kind = token(r'[A-Za-z]+')
            spaces()
            if kind in ('plural', 'selectordinal', 'select'):
                expect(',')
                spaces()
                offset = ''
                if message[index:].startswith('offset:'):
                    index += len('offset:')
                    offset = token(r'\d+')
                selectors = []
                while True:
                    spaces()
                    if index >= len(message):
                        raise ValueError('Unclosed plural/select')
                    if message[index] == '}':
                        index += 1
                        break
                    selector = token(r'=?[\w.-]+')
                    if selector in selectors:
                        raise ValueError('Duplicate plural/select branch')
                    selectors.append(selector)
                    expect('{')
                    body(True)
                if 'other' not in selectors:
                    raise ValueError('Missing ICU other branch')
                signatures.append((name, kind, tuple(sorted(selectors)), offset))
            else:
                if kind not in ('number', 'date', 'time'):
                    raise ValueError('Unsupported ICU format')
                while index < len(message) and message[index] != '}':
                    if message[index] == '{':
                        raise ValueError('Unexpected format nesting')
                    index += 1
                expect('}')
                signatures.append((name, kind, (), ''))
        if nested:
            raise ValueError('Unclosed message body')

    body()
    tags = tuple(sorted(re.findall(r'</?[A-Za-z][\w]*(?:\s*/)?\s*>', message)))
    return tuple(sorted(set(signatures))), tags


def compatible(source, target):
    try:
        return message_signature(source) == message_signature(target)
    except ValueError:
        return False


def load_translations(app, base_path=None):
    supplemental = read_json(ROOT / 'resources/supplemental-zh-CN.json')
    for source, target in supplemental.items():
        if not isinstance(target, str) or not compatible(source, target):
            raise ValueError('Invalid supplemental translation: ' + source)
    by_id = read_json(base_path) if base_path else {}
    if not isinstance(by_id, dict) or any(not isinstance(v, str) for v in by_id.values()):
        raise ValueError('Base translations must be a JSON object of string values')
    # Reuse only unambiguous source-text translations from locally supplied resources.
    choices = {}
    english = read_json(app / 'Contents/Resources/ion-dist/i18n/en-US.json')
    for key, target in by_id.items():
        if key in english and target != english[key]:
            choices.setdefault(english[key], set()).add(target)
    native_root = app / 'Contents/Resources'
    if (native_root / 'zh-Hans.json').exists():
        native_en = read_json(native_root / 'en-US.json')
        native_zh = read_json(native_root / 'zh-Hans.json')
        for key, target in native_zh.items():
            if key in native_en and target != native_en[key]:
                choices.setdefault(native_en[key], set()).add(target)
    by_text = {k: next(iter(v)) for k, v in choices.items() if len(v) == 1}
    by_text.update(supplemental)
    return by_id, by_text


def rewrite(source, by_id, by_text):
    counts = {'replacements': 0, 'skipped_invalid': 0}
    translated_ids = set()

    def replace(match):
        english, key = json.loads(match['text']), json.loads(match['id'])
        if not re.search(r'[A-Za-z]', english) or re.search(r'[\u3400-\u9fff]', english):
            return match[0]
        target = by_text.get(english, by_id.get(key))
        if not target or target == english:
            return match[0]
        if not compatible(english, target):
            counts['skipped_invalid'] += 1
            return match[0]
        counts['replacements'] += 1
        translated_ids.add(key)
        # JSON encoding prevents a translation from becoming executable JavaScript.
        return match['prefix'] + json.dumps(target, ensure_ascii=True) + match['between'] + match['id']

    result = MESSAGES.sub(replace, source)
    normalize = lambda s: MESSAGES.sub(lambda m: m['prefix'] + '"<DISPLAY>"' + m['between'] + m['id'], s)
    if normalize(result) != normalize(source):
        raise RuntimeError('Non-display content changed')
    return result, counts, translated_ids


def version(app):
    with (app / 'Contents/Info.plist').open('rb') as handle:
        return plistlib.load(handle)['CFBundleShortVersionString']


def inspect(app, base_path=None, apply=False):
    by_id, by_text = load_translations(app, base_path)
    report = {'version': version(app), 'replacements': 0, 'skipped_invalid': 0, 'files': [], 'unique_messages': 0}
    ids = set()
    files = sorted((app / ASSETS).glob('*.js'))
    if not files:
        raise RuntimeError('Unsupported app layout: no frontend scripts found')
    for file in files:
        before = file.read_text(encoding='utf-8')
        after, counts, translated_ids = rewrite(before, by_id, by_text)
        for key, value in counts.items():
            report[key] += value
        ids.update(translated_ids)
        if after != before:
            report['files'].append(str(file.relative_to(app)))
            if apply:
                file.write_text(after, encoding='utf-8')
    report['unique_messages'] = len(ids)
    return report


def run(*args):
    return subprocess.run(list(map(str, args)), check=True, capture_output=True)


def check_closed(app):
    result = subprocess.run(['pgrep', '-x', 'Claude'], capture_output=True, text=True)
    if result.returncode not in (0, 1):
        raise RuntimeError('Cannot determine whether Claude is running')
    for pid in result.stdout.split():
        command = run('ps', '-p', pid, '-o', 'comm=').stdout.decode().strip()
        if command == str(app / 'Contents/MacOS/Claude'):
            raise RuntimeError('请先保存工作并按 ⌘Q 退出 Claude，然后重试。')


def sign(app, scratch):
    data = run('codesign', '-d', '--entitlements', ':-', app).stdout
    entitlements = plistlib.loads(data)
    if not entitlements.get('com.apple.security.virtualization'):
        raise RuntimeError('Virtualization entitlement is missing; installation stopped')
    # A local signature cannot claim Anthropic's team identity or keychain groups.
    for key in ('com.apple.application-identifier', 'com.apple.developer.team-identifier', 'keychain-access-groups'):
        entitlements.pop(key, None)
    entitlements['com.apple.security.cs.disable-library-validation'] = True
    path = scratch / 'entitlements.plist'
    path.write_bytes(plistlib.dumps(entitlements))
    run('codesign', '--force', '--sign', '-', '--options', 'runtime',
        '--preserve-metadata=identifier,flags', '--entitlements', path, app)
    run('codesign', '--verify', '--deep', '--strict', app)


def swap(app, stage, backup):
    """A failed replacement restores the application immediately."""
    if backup.exists():
        raise RuntimeError('Backup already exists; refusing to overwrite it')
    app.rename(backup)
    try:
        stage.rename(app)
    except BaseException:
        backup.rename(app)
        raise


def install(args):
    app, state = args.app.resolve(), args.state_dir.resolve()
    if version(app) not in SUPPORTED and not args.allow_untested_version:
        raise RuntimeError('Untested version. Use --dry-run first; --allow-untested-version is an explicit override.')
    check_closed(app)
    state.mkdir(parents=True, exist_ok=True)
    if os.stat(app.parent).st_dev != os.stat(state).st_dev:
        raise RuntimeError('State directory and application must be on the same filesystem for atomic recovery')
    stamp = datetime.datetime.now().strftime('%Y%m%d-%H%M%S-%f')
    backup = state / ('Claude-before-' + stamp + '.app')
    report_path = state / ('install-' + stamp + '.json')
    # Persist recovery metadata before either application is moved.
    record = {'app': str(app), 'backup': str(backup), 'status': 'preparing', 'version': version(app)}
    write_json(report_path, record)
    with tempfile.TemporaryDirectory(prefix='stage-', dir=state) as directory:
        scratch = Path(directory)
        stage = scratch / 'Claude.app'
        run('ditto', app, stage)
        report = inspect(stage, args.base_translations, apply=True)
        if not report['replacements']:
            raise RuntimeError('No applicable translations; application left untouched')
        sign(stage, scratch)
        # Code, locale selection, HTML bootstrap, app.asar, and user data remain unchanged.
        for relative in ('Contents/Resources/app.asar', 'Contents/Resources/ion-dist/index.html'):
            if hashlib.sha256((app / relative).read_bytes()).digest() != hashlib.sha256((stage / relative).read_bytes()).digest():
                raise RuntimeError('Unexpected non-translation modification')
        check_closed(app)
        record.update(report=report, status='prepared')
        write_json(report_path, record)
        swap(app, stage, backup)
        try:
            run('codesign', '--verify', '--deep', '--strict', app)
        except BaseException:
            app.rename(scratch / 'failed.app')
            backup.rename(app)
            raise
    record['status'] = 'installed'
    write_json(report_path, record)
    write_json(state / 'latest.json', {'manifest': str(report_path)})
    print(json.dumps({'backup': str(backup), **report}, ensure_ascii=False, indent=2))
    if args.launch:
        run('open', app)


def restore(args):
    state = args.state_dir.resolve()
    record_path = Path(read_json(state / 'latest.json')['manifest'])
    record = read_json(record_path)
    app, backup = Path(record['app']), Path(record['backup'])
    if not backup.is_dir():
        raise RuntimeError('Backup unavailable; nothing changed')
    check_closed(app)
    run('codesign', '--verify', '--deep', '--strict', backup)
    saved = state / ('Claude-after-' + datetime.datetime.now().strftime('%Y%m%d-%H%M%S-%f') + '.app')
    swap(app, backup, saved)
    record.update(status='restored', patched_backup=str(saved))
    write_json(record_path, record)
    print('已恢复安装前的应用，汉化版也已保留。')
    if args.launch:
        run('open', app)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--app', type=Path, default=Path('/Applications/Claude.app'))
    parser.add_argument('--base-translations', type=Path, help='Optional local ooac frontend-zh-CN.json; never executes upstream code')
    parser.add_argument('--state-dir', type=Path, default=DEFAULT_STATE)
    parser.add_argument('--allow-untested-version', action='store_true')
    parser.add_argument('--launch', action='store_true')
    action = parser.add_mutually_exclusive_group()
    action.add_argument('--install', action='store_true')
    action.add_argument('--restore', action='store_true')
    action.add_argument('--dry-run', action='store_true', help='Read-only report (the default)')
    args = parser.parse_args()
    if args.restore:
        restore(args)
    elif args.install:
        install(args)
    else:
        report = inspect(args.app.resolve(), args.base_translations)
        print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError, RuntimeError, subprocess.CalledProcessError) as exc:
        print('错误：' + str(exc), file=sys.stderr)
        if isinstance(exc, subprocess.CalledProcessError) and exc.stderr:
            print(exc.stderr.decode(errors='replace'), file=sys.stderr)
        sys.exit(1)

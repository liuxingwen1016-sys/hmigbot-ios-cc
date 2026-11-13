"""Collect independent iOS states within a shared XCUITest invocation."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import tempfile
import time

from ios_evidence_protocol import bundle_identity, source_identity
from ios_runtime_capture import (app_identity, bundle_id, ensure_booted, run_command,
                                 validate_foreground_receipt, write_capture_evidence, write_foreground_ack)
from ios_xctest_accessibility import append_probe, copy_tree


def build_test_app(args, project, output_root):
    derived = Path(args.derived_data).expanduser().resolve()
    before = {path: path.stat().st_mtime_ns for path in (derived / 'Build/Products').glob('*.xctestrun')}
    command = ['xcodebuild', 'build-for-testing', '-project', str(project), '-scheme', args.scheme,
               '-configuration', args.configuration, '-destination', f'platform=iOS Simulator,id={args.device_id}',
               '-derivedDataPath', str(derived), 'CODE_SIGNING_ALLOWED=NO']
    log = output_root / 'xctest-build.log'
    with log.open('w') as stream:
        completed = subprocess.run(command, stdout=stream, stderr=subprocess.STDOUT, timeout=args.timeout)
    if completed.returncode:
        raise RuntimeError(f'XCUITest build failed with exit {completed.returncode}, see {log}')
    products = derived / 'Build/Products'
    runs = [path for path in products.glob('*.xctestrun') if before.get(path) != path.stat().st_mtime_ns]
    apps = [path for path in (products / f'{args.configuration}-iphonesimulator').glob('*.app')
            if bundle_id(path, None) == args.bundle_id]
    if len(runs) != 1 or len(apps) != 1:
        raise RuntimeError(f'expected one new XCUITest run and one app for {args.bundle_id} from {project}')
    identity = app_identity(apps[0], args.bundle_id)
    identity['bundle_sha256'] = bundle_identity(apps[0])
    return runs[0], apps[0], identity


def collect_group(args, group, *, xctestrun, directory, app, identity, source_sha256):
    directory.mkdir()
    plan = directory / 'batch.json'
    plan.write_text(json.dumps(group, ensure_ascii=False, indent=2) + '\n')
    log = directory / 'xctest.log'
    env = os.environ.copy()
    env['TEST_RUNNER_I2H_CAPTURE_BATCH'] = str(plan)
    command = ['xcodebuild', 'test-without-building', '-xctestrun', str(xctestrun),
               '-destination', f'platform=iOS Simulator,id={args.device_id}', '-parallel-testing-enabled', 'NO',
               f'-only-testing:{args.xctest_target}/I2HAccessibilityCaptureTests/testI2HAccessibilityCapture']
    pending = list(group)
    ready = {}
    errors = {}
    started = time.monotonic()
    deadline = started + args.timeout
    with log.open('w') as stream, subprocess.Popen(command, env=env, stdout=stream, stderr=subprocess.STDOUT,
                                                   start_new_session=True) as process:
        try:
            while pending and process.poll() is None and time.monotonic() < deadline:
                for state in pending[:]:
                    output = Path(state['output_dir'])
                    failure = output / 'capture-error.txt'
                    receipt = output / 'foreground-receipt.json'
                    if failure.is_file():
                        errors[output] = failure.read_text()
                    elif receipt.is_file():
                        try:
                            if not (output / 'ios-accessibility.json').is_file():
                                raise RuntimeError('XCUITest foreground receipt has no accessibility tree')
                            verified = validate_foreground_receipt(receipt, bundle_id=state['bundle_id'],
                                                                   page_id=state['page_id'], state_id=state['state_id'])
                            screenshot = output / 'ios-runtime.png'
                            run_command([args.xcrun, 'simctl', 'io', args.device_id, 'screenshot', str(screenshot)],
                                        timeout=min(30, max(1, int(deadline - time.monotonic()))))
                            write_foreground_ack(output / 'foreground-capture-ack.json', bundle_id=state['bundle_id'],
                                                 page_id=state['page_id'], state_id=state['state_id'], screenshot=screenshot)
                            ready[output] = (verified, round(time.monotonic() - started, 3))
                        except (OSError, RuntimeError, subprocess.SubprocessError) as exc:
                            errors[output] = str(exc)
                    else:
                        continue
                    pending.remove(state)
                if pending:
                    time.sleep(0.05)
            exit_code = process.wait(timeout=max(0, deadline - time.monotonic()))
        except subprocess.TimeoutExpired:
            exit_code = None
        finally:
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
    results = []
    for state in group:
        output = Path(state['output_dir'])
        page, state_id = state['page_id'], state['state_id']
        row = {'page_id': page, 'state_id': state_id, 'status': 'blocked', 'exit_code': exit_code,
               'output_dir': str(output), 'log_path': str(log)}
        if exit_code == 0 and output in ready and not (output / 'capture-error.txt').is_file():
            receipt, offset = ready[output]
            state_args = argparse.Namespace(page_id=page, state_id=state_id, scenario_id=args.scenario_id,
                                            configuration_id=args.configuration_id, checkpoint_id=f'{page}:{state_id}')
            write_capture_evidence(state_args, output_dir=output, device=args.device_id, app=app,
                                   identity=identity, source_sha256=source_sha256, receipt_payload=receipt)
            row.update(status='captured', captured_at_session_seconds=offset)
        else:
            row['blocked_reason'] = errors.get(output) or f'XCUITest session exit {exit_code} without a valid capture'
        results.append(row)
    return results


def run_batches(args, states, output_root):
    if not args.device_id or not args.bundle_id or not args.source_root:
        raise ValueError('XCUITest batching requires explicit --device-id, --bundle-id and --source-root')
    if args.app_path or any(state.get('accessibility_json') for state in states):
        raise ValueError('XCUITest batching builds its own app and captures fresh accessibility trees')
    source = Path(args.source_root).expanduser().resolve(strict=True)
    project = (Path(args.project_root) / args.project).expanduser().resolve(strict=True)
    relative_project = project.relative_to(source)
    source_sha256 = source_identity(source)
    ensure_booted(args.xcrun, args.device_id, args.timeout)
    plan = []
    for state in states:
        page, name = state['page_id'], state.get('state_id', 'normal')
        if not all(re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*', part) for part in (page, name)):
            raise ValueError(f'invalid capture path for {page}/{name}')
        output = output_root / page / 'states' / name
        output.mkdir(parents=True, exist_ok=False)
        navigation = state.get('navigation')
        plan.append({'page_id': page, 'state_id': name, 'bundle_id': args.bundle_id, 'output_dir': str(output),
                     'navigation_json': json.dumps(navigation, ensure_ascii=False) if navigation else ''})

    results = []
    with tempfile.TemporaryDirectory(prefix='i2h-xctest-batch-') as temporary:
        staged_source = Path(temporary) / source.name
        copy_tree(source, staged_source)
        relative_test = Path(args.xctest_test_source)
        if relative_test.is_absolute() or '..' in relative_test.parts:
            raise ValueError('XCUITest source file must be relative to the staged source root')
        append_probe(staged_source, str(relative_test))
        xctestrun, app, identity = build_test_app(args, staged_source / relative_project, output_root)
        for start in range(0, len(plan), args.xctest_batch_size):
            group = plan[start:start + args.xctest_batch_size]
            directory = output_root / f'xctest-session-{start // args.xctest_batch_size + 1:02d}'
            results.extend(collect_group(args, group, xctestrun=xctestrun, directory=directory, app=app,
                                         identity=identity, source_sha256=source_sha256))
    if source_identity(source) != source_sha256:
        raise RuntimeError('iOS source changed during the XCUITest batch capture')
    return results

#!/usr/bin/env python3
"""Run an approved iOS capture independently of static specification work."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time


CAPTURE = Path(__file__).resolve().with_name('ios_runtime_capture_plan.py')
JOB_NAME = re.compile(r'[A-Za-z0-9][A-Za-z0-9_-]{0,63}')
HANDOFF = 'spec/execution/ios-runtime-capture/capture-plan-manifest.json'


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec='milliseconds')


def encode(value):
    return (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode()


def write(path, raw):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(raw)
        temporary.replace(path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def read(path):
    return json.loads(path.read_bytes())


def job_path(project, name):
    if not JOB_NAME.fullmatch(name):
        raise ValueError('invalid capture job name')
    base = project / 'spec/execution/ios-runtime-jobs'
    result = (base / name).resolve()
    if result.parent != base:
        raise ValueError('capture job must remain inside the project')
    return result


def start(args):
    project = args.project_root.resolve(strict=True)
    job = job_path(project, args.job)
    source_root = args.source_root.resolve(strict=True)
    if project == source_root or source_root in project.parents:
        raise ValueError('capture output project must be outside the read-only iOS source')
    plan = (project / args.plan).resolve(strict=True)
    xcode_project = (source_root / args.xcode_project).resolve(strict=True)
    test_source = (source_root / args.xctest_test_source).resolve(strict=True)
    if project not in plan.parents or any(source_root not in p.parents for p in (xcode_project, test_source)):
        raise ValueError('expected a project-local plan and Xcode project under the selected iOS source')
    if args.batch_size < 1 or args.capture_timeout < 1 or not args.device_id.strip():
        raise ValueError('invalid device, batch size or capture timeout')
    raw = plan.read_bytes()
    job.mkdir(parents=True)
    frozen_plan = job / 'capture-plan.json'
    write(frozen_plan, raw)
    inputs = {
        'plan': str(plan), 'plan_sha256': sha256(raw).hexdigest(), 'device_id': args.device_id, 'bundle_id': args.bundle_id,
        'source_root': str(source_root), 'xcode_project': str(xcode_project), 'scheme': args.scheme,
        'configuration': args.configuration, 'configuration_id': args.configuration_id,
        'scenario_id': args.scenario_id, 'batch_size': args.batch_size, 'capture_timeout': args.capture_timeout,
        'xctest_target': args.xctest_target, 'xctest_test_source': str(test_source.relative_to(source_root)),
        'capture_script_sha256': sha256(CAPTURE.read_bytes()).hexdigest(),
    }
    encoded = encode(inputs)
    write(job / 'inputs.json', encoded)
    with (job / 'worker.log').open('wb') as log:
        process = subprocess.Popen(
            [sys.executable, '-B', str(Path(__file__).resolve()), '_worker', str(job), sha256(encoded).hexdigest()],
            cwd=job, stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, start_new_session=True,
        )
    launch = {'job': str(job), 'pid': process.pid, 'launched_at': utc_now()}
    write(job / 'launch.json', encode(launch))
    print(json.dumps(launch))
    return 0


def worker(job, expected_digest):
    import fcntl

    raw = (job / 'inputs.json').read_bytes()
    if sha256(raw).hexdigest() != expected_digest:
        raise ValueError('capture job inputs changed before launch')
    inputs = json.loads(raw)
    frozen_plan = job / 'capture-plan.json'
    if (sha256(frozen_plan.read_bytes()).hexdigest() != inputs['plan_sha256']
            or sha256(CAPTURE.read_bytes()).hexdigest() != inputs['capture_script_sha256']):
        raise ValueError('frozen capture plan or capture tool changed')
    write(job / 'running.json', encode({'started_at': utc_now(), 'pid': os.getpid()}))
    lock_root = Path(tempfile.gettempdir()) / f'i2h-device-locks-{os.getuid()}'
    lock_root.mkdir(mode=0o700, exist_ok=True)
    lock = lock_root / (sha256(inputs['device_id'].encode()).hexdigest() + '.lock')
    started = time.monotonic()
    receipt = {'status': 'ERROR', 'exit_code': 2}
    try:
        with lock.open('a') as stream, tempfile.TemporaryDirectory(prefix='i2h-capture-derived-') as derived:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
            work_project = job / 'capture-project'
            work_project.mkdir()
            command = [
                sys.executable, '-B', str(CAPTURE), '--project-root', str(work_project),
                '--plan', str(frozen_plan), '--output-root', str(job / 'states'),
                '--project', inputs['xcode_project'], '--source-root', inputs['source_root'],
                '--scheme', inputs['scheme'], '--bundle-id', inputs['bundle_id'],
                '--device-id', inputs['device_id'], '--configuration', inputs['configuration'],
                '--configuration-id', inputs['configuration_id'], '--scenario-id', inputs['scenario_id'],
                '--xctest-batch-size', str(inputs['batch_size']), '--timeout', str(inputs['capture_timeout']),
                '--derived-data', derived, '--xctest-target', inputs['xctest_target'],
                '--xctest-test-source', inputs['xctest_test_source'],
            ]
            completed = subprocess.run(command, cwd=job, check=False)
            manifest = job / 'states/capture-plan-manifest.json'
            if manifest.is_file():
                status = read(manifest).get('status')
                if (completed.returncode, status) in {(0, 'captured'), (2, 'partial')}:
                    receipt = {'status': status, 'exit_code': completed.returncode,
                               'manifest_sha256': sha256(manifest.read_bytes()).hexdigest()}
            if 'manifest_sha256' not in receipt:
                receipt['issue'] = f'capture exited {completed.returncode} without a valid manifest'
    except BlockingIOError:
        receipt['issue'] = 'this simulator already has an active i2h capture job'
    except (OSError, ValueError, KeyError) as error:
        receipt['issue'] = str(error)
    receipt.update(finished_at=utc_now(), elapsed_seconds=round(time.monotonic() - started, 3),
                   inputs_sha256=expected_digest)
    write(job / 'result.json', encode(receipt))
    return receipt['exit_code']


def join(args):
    project = args.project_root.resolve(strict=True)
    job = job_path(project, args.job)
    launch = read(job / 'launch.json')
    result = job / 'result.json'
    if args.timeout < 0:
        raise ValueError('join timeout must be nonnegative')
    deadline = time.monotonic() + args.timeout
    liveness = 'observed'
    while not result.is_file():
        try:
            os.kill(launch['pid'], 0)
        except PermissionError:
            # A restricted caller can consume the durable receipt without process inspection.
            liveness = 'unobservable'
        except ProcessLookupError:
            if result.is_file():
                break
            raise ValueError('capture process ended before writing a terminal receipt')
        if time.monotonic() >= deadline:
            print(json.dumps({'status': 'RUNNING' if liveness == 'observed' else 'AWAITING_RECEIPT',
                              'process_liveness': liveness, **launch}))
            return 124
        time.sleep(0.25)
    receipt = read(result)
    if args.publish and receipt['status'] == 'captured':
        import fcntl

        raw_inputs = (job / 'inputs.json').read_bytes()
        inputs = json.loads(raw_inputs)
        if (sha256(raw_inputs).hexdigest() != receipt['inputs_sha256']
                or sha256(Path(inputs['plan']).read_bytes()).hexdigest() != inputs['plan_sha256']):
            raise ValueError('capture plan changed before handoff')
        raw_manifest = (job / 'states/capture-plan-manifest.json').read_bytes()
        if sha256(raw_manifest).hexdigest() != receipt['manifest_sha256']:
            raise ValueError('capture manifest changed before handoff')
        target = (project / HANDOFF).resolve()
        if project not in target.parents:
            raise ValueError('capture handoff must remain inside the project')
        target.parent.mkdir(parents=True, exist_ok=True)
        with (target.parent / '.capture-job.lock').open('a') as stream:
            fcntl.flock(stream, fcntl.LOCK_EX)
            if target.is_file() and target.read_bytes() != raw_manifest:
                raise ValueError('another capture already owns the canonical handoff')
            write(target, raw_manifest)
    print(json.dumps(receipt, ensure_ascii=False))
    return receipt['exit_code']


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_subparsers(dest='mode', required=True)
    launch = modes.add_parser('start')
    wait = modes.add_parser('join')
    for command in (launch, wait):
        command.add_argument('--project-root', type=Path, default=Path.cwd())
        command.add_argument('--job', required=True)
    launch.add_argument('--plan', required=True, type=Path)
    launch.add_argument('--source-root', required=True, type=Path)
    launch.add_argument('--xcode-project', required=True, type=Path)
    launch.add_argument('--scheme', required=True)
    launch.add_argument('--device-id', required=True)
    launch.add_argument('--bundle-id', required=True)
    launch.add_argument('--configuration', default='Debug')
    launch.add_argument('--configuration-id', required=True)
    launch.add_argument('--scenario-id', required=True)
    launch.add_argument('--batch-size', type=int, default=6)
    launch.add_argument('--capture-timeout', type=int, default=600)
    launch.add_argument('--xctest-target', required=True)
    launch.add_argument('--xctest-test-source', required=True)
    wait.add_argument('--timeout', type=int, default=600)
    wait.add_argument('--publish', action='store_true')
    child = modes.add_parser('_worker', help=argparse.SUPPRESS)
    child.add_argument('path', type=Path)
    child.add_argument('sha256')
    args = parser.parse_args()
    try:
        if args.mode == '_worker':
            return worker(args.path, args.sha256)
        if args.mode == 'start':
            return start(args)
        return join(args)
    except (OSError, ValueError, KeyError) as error:
        parser.exit(2, f'iOS capture job: {error}\n')


if __name__ == '__main__':
    raise SystemExit(main())

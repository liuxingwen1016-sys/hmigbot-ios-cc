"""Capture a ready HarmonyOS checkpoint with a project's native UITest runner."""
from __future__ import annotations

from collections.abc import Callable, Collection
import hashlib
import json
import math
from pathlib import Path
import re
from subprocess import TimeoutExpired
from tempfile import NamedTemporaryFile, TemporaryDirectory
import time
from uuid import uuid4
import warnings

from uitest_action import native, observed_window, require_focused_app


class CheckpointTimeout(RuntimeError):
    """The authorized application was visible, but the expected state never arrived."""


def core_vision_ocr_preflight(send: Callable[..., str]) -> dict | None:
    """Return a known environment block for Core Vision Kit OCR on an emulator."""
    model = send('shell', 'param', 'get', 'const.product.model').strip()
    if model.casefold() != 'emulator':
        return None
    return {
        'status': 'BLOCKED',
        'reason': 'Core Vision Kit OCR requires a supported device. This target reports model emulator.',
        'device_capability': 'core_vision_ocr',
        'failure_diagnostic': {
            'stage': 'device_preflight',
            'device_model': model,
            'reference': 'https://developer.huawei.com/consumer/en/doc/doccenter-capabilities/core-vision-introduction/',
        },
    }


def capture_uitest_artifact(destination, *, kind, send):
    """Download one capture and retire only the remote file created for this call.

    send must run HDC on the authorized device with its normal timeout and
    logging, raising on transport and device-command errors.
    """
    destination = Path(destination)
    suffix = destination.suffix.lower()
    if kind == 'layout' and suffix == '.json':
        command = ('uitest', 'dumpLayout', '-p')
    elif kind == 'image' and suffix in ('.png', '.jpeg', '.jpg'):
        command = ('snapshot_display', '-f')
    else:
        raise ValueError('expected a JSON layout or PNG/JPEG image destination')
    remote = f'/data/local/tmp/i2h-uitest-{uuid4().hex}{suffix}'
    try:
        with TemporaryDirectory(dir=destination.parent, prefix='.i2h-uitest-') as temporary:
            local = Path(temporary) / destination.name
            message = send('shell', *command, remote)
            if kind == 'layout' and not any(
                line.removeprefix('DumpLayout saved to:').strip() == remote
                for line in message.splitlines() if line.startswith('DumpLayout saved to:')
            ):
                raise RuntimeError(f'UITest did not confirm the requested layout: {message.strip()}')
            send('file', 'recv', remote, str(local))
            raw = local.read_bytes()
            if kind == 'layout':
                payload = json.loads(raw)
                if not isinstance(payload, dict) or not ('children' in payload or 'attributes' in payload):
                    raise ValueError('downloaded file is not a UITest layout')
            else:
                signature = b'\x89PNG\r\n\x1a\n' if suffix == '.png' else b'\xff\xd8\xff'
                if not raw.startswith(signature):
                    raise ValueError('downloaded screenshot has the wrong image format')
                payload = destination
            local.replace(destination)
    except (OSError, RuntimeError, TimeoutExpired, ValueError) as error:
        error.remote_uitest_artifact = remote
        if hasattr(error, 'add_note'):
            error.add_note(f'UITest remote artifact, if present: {remote}')
        raise
    try:
        send('shell', 'rm', '-f', remote)
    except (OSError, RuntimeError, TimeoutExpired) as error:
        warnings.warn(f'UITest evidence saved locally, remote cleanup failed for {remote}: {error}',
                      RuntimeWarning, stacklevel=2)
    return payload


def write_visual_arrival(spec_root, destination, *, pair, capture_run_id, device_id,
                         screenshot, layout, matched_tree, build_receipt, install_receipt,
                         landing_evidence=None, pre_capture_tree=None):
    """Persist native evidence after capture_checkpoint confirms the expected state."""
    root = Path(spec_root).resolve()

    def artifact(path):
        path = Path(path).resolve()
        name = path.relative_to(root).as_posix()
        data = path.read_bytes()
        if not data:
            raise ValueError(f'empty visual artifact: {name}')
        return {'path': name, 'sha256': hashlib.sha256(data).hexdigest()}, data

    if not all(isinstance(value, str) and value.strip() for value in (capture_run_id, device_id)):
        raise ValueError('visual arrival requires capture run and device identities')
    tree_ref, raw_layout = artifact(layout)
    if json.loads(raw_layout) != matched_tree:
        raise ValueError('saved layout differs from the state-ready tree')
    # Record the actual unique foreground window. Plan page IDs are declarations, not native routes.
    window = observed_window(matched_tree)
    predicate = pair.get('target_observation')
    if predicate is not None:
        if pre_capture_tree is None:
            raise ValueError('strict arrival requires the approved pre-capture tree')
        before_observed = native.observe_state(pre_capture_tree, predicate)
        observed = native.observe_state(matched_tree, predicate)
        if before_observed['active_layer'] != observed['active_layer']:
            raise ValueError('active native layer changed during screenshot')
        identity = {'declared_page_id': pair['page_id'], 'declared_state_id': pair['state_id'],
                    'page_state_observation': {**observed, 'layout_sha256': tree_ref['sha256']}}
    else:
        # Historical receipts keep their explicit legacy identity. They are not native state proof.
        identity = {'observed_page_id': pair['page_id'], 'observed_state_id': pair['state_id'],
                    'identity_origin': 'legacy_runner_declared_not_native_observation'}
    screenshot_ref, _ = artifact(screenshot)
    build_ref, _ = artifact(build_receipt)
    install_ref, _ = artifact(install_receipt)
    landing_ref = artifact(landing_evidence)[0] if landing_evidence else tree_ref
    receipt = {
        'status': 'PASS', 'pair_id': pair['pair_id'], 'arrival_mode': pair['arrival_mode'],
        **identity, 'observed_window': window,
        'capture_run_id': capture_run_id, 'device_id': device_id,
        'build_receipt': build_ref, 'install_receipt': install_ref, 'landing_evidence': landing_ref,
        'frames': [{'comparison_id': frame['comparison_id'], 'harmony_png': screenshot_ref,
                    'harmony_xml': tree_ref} for frame in pair['comparisons']],
    }
    destination = Path(destination).resolve()
    destination.relative_to(root)
    if predicate is not None:
        before_path = destination.with_suffix('.before.json')
        before_path.write_text(json.dumps(pre_capture_tree, ensure_ascii=False, sort_keys=True), encoding='utf-8')
        before_ref, _ = artifact(before_path)
        receipt['pre_capture_tree'] = before_ref
        receipt['pre_capture_observation'] = {**before_observed, 'layout_sha256': before_ref['sha256']}
    with NamedTemporaryFile(dir=destination.parent, mode='w', encoding='utf-8', delete=False) as stream:
        temporary = Path(stream.name)
        try:
            json.dump(receipt, stream, ensure_ascii=False, indent=2)
            stream.write('\n')
            stream.close()
            temporary.replace(destination)
        finally:
            temporary.unlink(missing_ok=True)
    return receipt


def capture_checkpoint(
    name: str,
    *,
    bundle: str,
    read_layout: Callable[[str], dict],
    is_ready: Callable[[dict], bool],
    capture_image: Callable[[str], None],
    approved_images: Collection[str] | None,
    record_arrival: Callable[[str, dict], None] | None = None,
    timeout: float = 8,
    interval: float = 0.15,
    image_ready_seconds: float = 0,
    target_observation: dict | None = None,
) -> dict:
    """Return the matched tree and capture an image only in the requested scope.

    The adapter persists each layout at the checkpoint name, replacing prior
    samples, and sets its own transport timeout. With an arrival callback,
    the same readiness predicate and app focus must hold after the screenshot.
    The callback receives the post-capture tree persisted by the adapter.
    The deadline bounds readiness polling. Synchronous capture and confirmation
    commands already started use the adapter's transport timeout.
    """
    if not math.isfinite(timeout) or not math.isfinite(interval) or timeout <= 0 or interval <= 0:
        raise ValueError('checkpoint timeout and interval must be finite and positive')
    if not math.isfinite(image_ready_seconds) or not 0 <= image_ready_seconds < timeout:
        raise ValueError('image readiness duration must be nonnegative and less than the timeout')
    if target_observation is not None:
        native.validate_state_predicate(target_observation)
        if target_observation['bundle'] != bundle or record_arrival is None:
            raise ValueError('strict capture requires the approved bundle and arrival callback')
    def approved_ready(value):
        if target_observation is None:
            return True
        try:
            native.observe_state(value, target_observation)
            return True
        except ValueError:
            return False
    wants_image = approved_images is None or name in approved_images
    ready_since = None
    deadline = time.monotonic() + timeout
    while True:
        tree = read_layout(name)
        require_focused_app(tree, bundle)
        ready = is_ready(tree) and approved_ready(tree)
        now = time.monotonic()
        if ready and now <= deadline:
            if not wants_image:
                return tree
            if ready_since is None:
                ready_since = now
            if now - ready_since >= image_ready_seconds:
                pre_capture_tree = json.loads(json.dumps(tree))
                capture_image(name)
                if record_arrival is None:
                    return tree
                confirmed = read_layout(name)
                require_focused_app(confirmed, bundle)
                same_layer = (target_observation is None or not approved_ready(confirmed)
                              or native.observe_state(pre_capture_tree, target_observation)['active_layer']
                              == native.observe_state(confirmed, target_observation)['active_layer'])
                if not is_ready(confirmed) or not approved_ready(confirmed) or not same_layer:
                    raise CheckpointTimeout(f'expected app state changed during image capture: {name}')
                if target_observation is not None:
                    record_arrival(name, confirmed, pre_capture_tree=pre_capture_tree)
                else:
                    record_arrival(name, confirmed)
                return confirmed
        else:
            ready_since = None
        remaining = deadline - now
        if remaining <= 0:
            raise CheckpointTimeout(f'expected app state did not become ready: {name}')
        time.sleep(min(interval, remaining))
        if time.monotonic() >= deadline:
            raise CheckpointTimeout(f'expected app state did not become ready: {name}')


def device_timeout_details(error: TimeoutExpired) -> dict:
    """Record transport timeout metadata without copying command input text."""
    result = {'seconds': error.timeout}
    if remote := getattr(error, 'remote_uitest_artifact', None):
        result['remote_uitest_artifact'] = remote
    return result



def hdc_failure_details(returncode: int, stdout: str, stderr: str) -> dict | None:
    """Classify HDC device-control failures, including HDC's zero-exit errors."""
    transcript = f'{stdout}\n{stderr}'
    error = re.search(r'^\s*(?:\[Fail\]|error\s*:)', transcript, re.I | re.M)
    if returncode == 0 and error is None:
        return None

    if re.search(r'^\s*Error Code:\s*10106102\b', transcript, re.M):
        return {'kind': 'device_screen_locked', 'code': '10106102', 'exit_code': returncode}
    if re.search(r'^\s*\[Fail\]\[E001005\]', transcript, re.I | re.M):
        return {'kind': 'device_disconnected', 'code': 'E001005', 'exit_code': returncode}
    return {'kind': 'hdc_command_failed', 'exit_code': returncode}

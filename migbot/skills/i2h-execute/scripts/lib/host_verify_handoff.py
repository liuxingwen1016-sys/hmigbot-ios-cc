"""Produce and replay source-bound host installation evidence."""
from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import re
import subprocess
from tempfile import TemporaryDirectory, gettempdir, mkdtemp
from zipfile import BadZipFile, ZipFile

from .ios_ui_dispatch import atomic_write, checked_artifact, json_bytes, locked
from .ios_ui_delivery_gate import _project_file
from .stage1_contract import digest, source_digest

HANDOFF = 'spec/verify/host-installation.json'
SIGN_SUCCESS = re.compile(r'\bverify-app success\s*$', re.MULTILINE)
INSTALL_SUCCESS = re.compile(r'\bmsg:install bundle successfully\.\s*$', re.MULTILINE)


def _reference(root, path):
    return {'path': path.relative_to(root).as_posix(), 'sha256': digest(path)}


def _read(root, ref):
    return checked_artifact(_project_file(root, ref['path']), ref['sha256'])


def _identity(hap):
    try:
        with ZipFile(hap) as package:
            module, = (item for item in package.infolist() if item.filename == 'module.json')
            app = json.loads(package.read(module))['app']
    except (BadZipFile, ValueError, KeyError, NotImplementedError) as exc:
        raise ValueError('HAP module metadata is invalid') from exc
    bundle, version = app['bundleName'], app['versionCode']
    if not isinstance(bundle, str) or not re.fullmatch(r'[\w]+(?:\.[\w]+)+', bundle):
        raise ValueError('invalid HAP bundle name')
    if type(version) is not int or version < 1:
        raise ValueError('invalid HAP version code')
    return bundle, version


def _observed_identity(raw, bundle, version):
    prefix, separator, body = raw.strip().partition(':')
    if prefix.strip() != bundle or not separator:
        raise ValueError('device bundle query did not confirm the selected application')
    observed = json.loads(body)
    if observed.get('bundleName', observed.get('name')) != bundle or observed.get('versionCode') != version:
        raise ValueError('device bundle or version differs from the signed HAP')


def _run(root, command, timeout, log):
    result = subprocess.run(command, cwd=root, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, timeout=timeout, check=False)
    atomic_write(log, result.stdout)
    if result.returncode:
        raise ValueError(f'host command exited {result.returncode}; see {log.name}')
    return result.stdout.decode(errors='replace')


def publish(root, args, build, initial_hap_stamp):
    """Run on the authorized host after a source-stable Hvigor build."""
    scope = _project_file(root, str(args.scope))
    hap = _project_file(root, str(args.signed_hap))
    source = build['source_sha256']
    if not hap.is_file() or hap.suffix != '.hap' or hap_stamp(hap) == initial_hap_stamp:
        raise ValueError('build did not produce a fresh HAP at the selected output')
    if json.loads(scope.read_bytes()).get('source_sha256') != source:
        raise ValueError('visual scope is bound to different source')
    scope_ref = _reference(root, scope)
    hap_ref = _reference(root, hap)
    bundle, version = _identity(hap)
    if bundle != args.bundle or not re.fullmatch(r'[\w.:-]+', args.device) or args.device.startswith('-'):
        raise ValueError('HAP or device differs from the selected installation')
    build_log = _project_file(root, build['log']['path'])
    build_ref = {'path': build_log.relative_to(root).as_posix(), 'sha256': build['log']['sha256']}
    _read(root, build_ref)

    out = (root / 'spec/execution/host-verify').resolve()
    if not out.is_relative_to(root / 'spec/execution'):
        raise ValueError('host Verify evidence must stay inside spec/execution')
    out.mkdir(parents=True, exist_ok=True)
    run = Path(mkdtemp(prefix='installation-', dir=out))
    sign_log = run / 'signature.log'
    with TemporaryDirectory(dir=run) as temporary:
        cert, profile = Path(temporary) / 'chain.cer', Path(temporary) / 'profile.p7b'
        signed = _run(root, [args.java, '-jar', args.sign_tool, 'verify-app', '-inFile', str(hap),
                             '-outCertChain', str(cert), '-outProfile', str(profile)], args.timeout, sign_log)
        if not SIGN_SUCCESS.search(signed) or not cert.is_file() or not profile.is_file():
            raise ValueError('SDK signature verifier did not confirm the HAP')

    def recheck():
        if source_digest(root) != source:
            raise ValueError('production source changed during host handoff')
        _read(root, hap_ref)
        _read(root, scope_ref)

    device_key = sha256(args.device.encode()).hexdigest()
    with locked(Path(gettempdir()) / 'i2h-harmony-install-locks' / device_key):
        recheck()
        handoff_path = _project_file(root, HANDOFF)
        handoff_path.parent.mkdir(parents=True, exist_ok=True)
        handoff_path.unlink(missing_ok=True)
        hdc = [args.hdc, '-t', args.device]
        install_log = run / 'install.log'
        if not INSTALL_SUCCESS.search(_run(root, [*hdc, 'install', '-r', str(hap)], args.timeout, install_log)):
            raise ValueError('HDC did not confirm a successful install')
        identity_log = run / 'bundle.log'
        _observed_identity(_run(root, [*hdc, 'shell', 'bm', 'dump', '-n', bundle],
                                args.timeout, identity_log), bundle, version)
        recheck()

        common = {'schema_version': 1, 'status': 'PASS', 'scope_sha256': scope_ref['sha256'],
                  'source_sha256': source, 'hap_path': hap_ref['path'], 'hap_sha256': hap_ref['sha256']}
        build_path = run / 'build.json'
        install_path = run / 'install.json'
        atomic_write(build_path, json_bytes({**common, 'kind': 'build', 'build_log': build_ref,
                                            'signature_log': _reference(root, sign_log)}))
        atomic_write(install_path, json_bytes({**common, 'kind': 'install', 'device_id': args.device,
            'bundle': bundle, 'version_code': version, 'install_log': _reference(root, install_log),
            'identity_log': _reference(root, identity_log)}))
        handoff = {'schema_version': 1, 'scope': scope_ref, 'build_receipt': _reference(root, build_path),
                   'install_receipt': _reference(root, install_path)}
        validate(root, handoff)
        atomic_write(handoff_path, json_bytes(handoff))
        return handoff


def hap_stamp(path):
    if not path.is_file():
        return None
    info = path.stat()
    return info.st_ino, info.st_mtime_ns, digest(path)


def validate(root, handoff):
    """Read-only replay for Verify, preserving the existing Stage-1 receipt shape."""
    if handoff.get('schema_version') != 1:
        raise ValueError('unsupported host Verify handoff')
    scope = json.loads(_read(root, handoff['scope']))
    source = source_digest(root)
    if scope.get('source_sha256') != source:
        raise ValueError('host Verify handoff is stale for current source')
    build, install = (json.loads(_read(root, handoff[key])) for key in ('build_receipt', 'install_receipt'))
    for kind, receipt in (('build', build), ('install', install)):
        expected = (kind, 'PASS', source, handoff['scope']['sha256'])
        if tuple(receipt.get(k) for k in ('kind', 'status', 'source_sha256', 'scope_sha256')) != expected:
            raise ValueError(f'{kind} receipt does not match the host Verify handoff')
    if any(build[key] != install[key] for key in ('hap_path', 'hap_sha256')):
        raise ValueError('build and installation refer to different HAPs')
    hap = _project_file(root, build['hap_path'])
    checked_artifact(hap, build['hap_sha256'])
    bundle, version = _identity(hap)
    if (install.get('bundle'), install.get('version_code')) != (bundle, version) or not install.get('device_id'):
        raise ValueError('installation does not match the HAP identity')
    from host_build_checkpoint import diagnose
    if diagnose(_read(root, build['build_log']).decode(errors='replace'), 0)['status'] != 'PASS':
        raise ValueError('host build log does not confirm successful compilation')
    if not SIGN_SUCCESS.search(_read(root, build['signature_log']).decode(errors='replace')):
        raise ValueError('host signature log does not confirm verification')
    if not INSTALL_SUCCESS.search(_read(root, install['install_log']).decode(errors='replace')):
        raise ValueError('host install log does not confirm installation')
    _observed_identity(_read(root, install['identity_log']).decode(errors='replace'), bundle, version)
    return {'hap_sha256': build['hap_sha256'].removeprefix('sha256:'), 'device': install['device_id'],
            'bundle': bundle, 'version_code': version}

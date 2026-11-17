#!/usr/bin/env python3
"""
Apply Writeback Manifest

用途: 应用 writeback manifest，将 closer 产出的修改落盘到项目中
"""

import argparse
import json
import re
import sys
from tempfile import NamedTemporaryFile
from pathlib import Path
from typing import Dict, List, Any

from lib.execute_claims import claim_problem, load_plan
from lib.ios_stage1_scope import load_inventory

# Structured writeback diagnostics are intentionally module-level: callers and
# tests can inspect what was applied, skipped, or warned without scraping CLI
# output.  They are reset by the caller between runs.
applied: list[str] = []
noops: list[str] = []
warns: list[str] = []


def _write_text_atomic(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(dir=path.parent, mode="w", encoding="utf-8", delete=False) as handle:
        tmp = Path(handle.name)
        try:
            handle.write(content)
            handle.close()
            tmp.replace(path)
        finally:
            tmp.unlink(missing_ok=True)


class WritebackApplier:
    """Writeback Manifest 应用器"""

    def __init__(self, project_root: str):
        self.project_root = Path(project_root)
        self.stats = {
            'total_operations': 0,
            'creates': 0,
            'modifies': 0,
            'deletes': 0,
            'fills': 0,
            'errors': 0
        }

    def apply_manifest(self, manifest_path: str) -> bool:
        """应用 writeback manifest"""
        manifest_file = Path(manifest_path)

        if not manifest_file.exists():
            print(f"❌ Manifest 文件不存在: {manifest_path}")
            return False

        print(f"📄 读取 Manifest: {manifest_path}")

        with open(manifest_file, 'r', encoding='utf-8') as f:
            manifest = json.load(f)

        # 验证 manifest 格式
        if not self._validate_manifest(manifest):
            return False

        # 应用所有操作
        operations = manifest.get('operations', [])
        self.stats['total_operations'] = len(operations)

        print(f"\n🔧 开始应用 {len(operations)} 个操作...")

        for i, operation in enumerate(operations, 1):
            op_type = operation.get('type')
            print(f"\n[{i}/{len(operations)}] 操作类型: {op_type}")

            try:
                if op_type == 'create':
                    self._apply_create(operation)
                elif op_type == 'modify':
                    self._apply_modify(operation)
                elif op_type == 'delete':
                    self._apply_delete(operation)
                elif op_type == 'fill_placeholder':
                    self._apply_fill_placeholder(operation)
                else:
                    print(f"⚠️  未知操作类型: {op_type}")
                    self.stats['errors'] += 1
            except Exception as e:
                print(f"❌ 操作失败: {e}")
                self.stats['errors'] += 1

        # 打印统计
        self._print_stats()

        return self.stats['errors'] == 0

    def _validate_manifest(self, manifest: Dict[str, Any]) -> bool:
        """验证 manifest 格式"""
        if 'version' not in manifest:
            print("❌ Manifest 缺少 version 字段")
            return False

        if 'operations' not in manifest:
            print("❌ Manifest 缺少 operations 字段")
            return False

        if not isinstance(manifest['operations'], list):
            print("❌ operations 字段必须是数组")
            return False

        print("✅ Manifest 格式验证通过")
        return True

    def _apply_create(self, operation: Dict[str, Any]):
        """应用 create 操作"""
        file_path = self.project_root / operation['file']
        content = operation['content']

        # 检查文件是否已存在
        if file_path.exists():
            print(f"⚠️  文件已存在，将覆盖: {file_path}")

        # 创建目录（如果不存在）
        file_path.parent.mkdir(parents=True, exist_ok=True)

        # 写入文件
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)

        print(f"✅ 创建文件: {operation['file']}")
        self.stats['creates'] += 1

    def _apply_modify(self, operation: Dict[str, Any]):
        """应用 modify 操作"""
        file_path = self.project_root / operation['file']

        if not file_path.exists():
            print(f"❌ 文件不存在: {file_path}")
            raise FileNotFoundError(f"文件不存在: {file_path}")

        # 读取文件
        with open(file_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()

        # 应用所有修改
        changes = operation.get('changes', [])

        for change in changes:
            line_range = change['line_range']
            old_content = change['old_content']
            new_content = change['new_content']

            start_line = line_range[0] - 1  # 转为 0-based
            end_line = line_range[1] - 1

            # 验证旧内容
            old_lines = ''.join(lines[start_line:end_line + 1])
            if old_content not in old_lines:
                print(f"⚠️  旧内容不匹配，跳过此修改")
                print(f"   期望: {old_content[:50]}...")
                print(f"   实际: {old_lines[:50]}...")
                continue

            # 替换内容
            lines[start_line:end_line + 1] = [new_content + '\n']

        # 写回文件
        with open(file_path, 'w', encoding='utf-8') as f:
            f.writelines(lines)

        print(f"✅ 修改文件: {operation['file']} ({len(changes)} 处修改)")
        self.stats['modifies'] += 1

    def _apply_delete(self, operation: Dict[str, Any]):
        """应用 delete 操作"""
        file_path = self.project_root / operation['file']

        if not file_path.exists():
            print(f"⚠️  文件不存在（已删除？）: {file_path}")
            return

        # 删除文件
        file_path.unlink()

        print(f"✅ 删除文件: {operation['file']}")
        self.stats['deletes'] += 1

    def _apply_fill_placeholder(self, operation: Dict[str, Any]):
        """应用 fill_placeholder 操作"""
        file_path = self.project_root / operation['file']

        if not file_path.exists():
            print(f"❌ 文件不存在: {file_path}")
            raise FileNotFoundError(f"文件不存在: {file_path}")

        # 读取文件
        with open(file_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()

        # 获取占位符信息
        line_range = operation['line_range']
        old_content = operation.get('old_content', '')
        new_content = operation['new_content']
        placeholder_id = operation.get('placeholder_id', 'unknown')

        start_line = line_range[0] - 1
        end_line = line_range[1] - 1

        # 验证旧内容（如果提供）
        if old_content:
            old_lines = ''.join(lines[start_line:end_line + 1])
            if old_content not in old_lines:
                print(f"⚠️  占位符内容不匹配，可能已被修改")
                print(f"   占位符 ID: {placeholder_id}")

        # 替换占位符
        lines[start_line:end_line + 1] = [new_content + '\n']

        # 写回文件
        with open(file_path, 'w', encoding='utf-8') as f:
            f.writelines(lines)

        print(f"✅ 回填占位符: {placeholder_id} in {operation['file']}")
        self.stats['fills'] += 1

    def _print_stats(self):
        """打印统计信息"""
        print("\n" + "=" * 60)
        print("📊 应用统计:")
        print("=" * 60)
        print(f"  总操作数: {self.stats['total_operations']}")
        print(f"  创建: {self.stats['creates']}")
        print(f"  修改: {self.stats['modifies']}")
        print(f"  删除: {self.stats['deletes']}")
        print(f"  回填占位符: {self.stats['fills']}")
        print(f"  错误: {self.stats['errors']}")
        print("=" * 60)

        if self.stats['errors'] == 0:
            print("✅ 所有操作成功完成")
        else:
            print(f"⚠️  有 {self.stats['errors']} 个操作失败")

def _section(manifest, name, keys):
    section = manifest.get(name, {})
    if not isinstance(section, dict) or section.keys() - keys:
        raise ValueError(f"{name}: expected fields {', '.join(sorted(keys))}")
    return section


def _ids(values, label):
    if not isinstance(values, list) or any(not isinstance(value, str) or not value.strip() for value in values):
        raise ValueError(f"{label}: expected a list of identifiers")
    return set(values)


def _project_path(root, relative, prefix):
    if not isinstance(relative, str):
        raise ValueError(f"expected a path under {prefix}")
    path = Path(relative)
    target = (root / path).resolve()
    if path.is_absolute() or '..' in path.parts or not target.is_relative_to(root / prefix):
        raise ValueError(f"expected a path under {prefix}: {relative}")
    return target


def _stage_registry(root, registry):
    resolved = _ids(registry.get('resolve', []), 'registry.resolve')
    retags = {}
    for row in registry.get('retag', []):
        pid, column, value = row['pid'], row['column'], row['value']
        if (column not in {'resolve_by', 'kind'} or not isinstance(value, str) or not value.strip()
                or any(char in value for char in '|\r\n') or (pid, column) in retags):
            raise ValueError(f"invalid registry retag: {row!r}")
        retags[pid, column] = value
    requested = resolved | {pid for pid, _ in retags}
    if not requested:
        return None
    path = _project_path(root, 'spec/placeholder-registry.md', 'spec')
    original = path.read_text(encoding='utf-8')
    columns, found, lines = {}, set(), []
    for line in original.splitlines(keepends=True):
        parts = line.split('|')
        if len(parts) > 2 and not parts[0].strip():
            key = parts[1].strip()
            if key == 'P-ID':
                columns = {name.strip(): index for index, name in enumerate(parts[1:-1], 1)}
            if key in requested:
                if key in found:
                    raise ValueError(f"duplicate registry row: {key}")
                found.add(key)
                changes = {column: value for (pid, column), value in retags.items() if pid == key}
                if key in resolved:
                    changes['status'] = 'resolved'
                for column, value in changes.items():
                    index = columns.get(column)
                    if index is None or index >= len(parts) - 1:
                        raise ValueError(f"{key}: missing registry column {column}")
                    if parts[index].strip() != value:
                        parts[index] = f' {value} '
                line = '|'.join(parts)
        lines.append(line)
    missing = requested - found
    if any(pid in missing for pid, _ in retags):
        raise ValueError(f"registry retag target missing: {', '.join(sorted(missing))}")
    noops.extend(sorted(missing))
    return path, original, ''.join(lines)


def _claims_main(path, manifest, root, dry):
    registry = _stage_registry(root, _section(manifest, 'registry', {'resolve', 'retag'}))
    ui = _ids(_section(manifest, 'ui_manifest', {'converted'}).get('converted', []), 'ui_manifest.converted')
    features = _ids(_section(manifest, 'feature_index', {'implemented'}).get('implemented', []),
                    'feature_index.implemented')
    if ui:
        _, inventory = load_inventory(root, None)
        aliases = {}
        for unit in inventory['units']:
            page = unit['page_id']
            seq = re.match(r'page_(\d+)_', page)
            for alias in (page, unit['unit_id'], *((seq[1], str(int(seq[1]))) if seq else ())):
                if alias in aliases and aliases[alias] != page:
                    raise ValueError(f"ambiguous approved page alias: {alias}")
                aliases[alias] = page
        if ui - aliases.keys():
            raise ValueError(f"unknown approved UI page: {', '.join(sorted(ui - aliases.keys()))}")
        ui = {aliases[alias] for alias in ui}
    brief = _section(manifest, 'brief', {'path', 'content'})
    staged = [registry] if registry else []
    if brief:
        brief_path = _project_path(root, brief.get('path'), 'spec/execution/briefs')
        content = brief.get('content')
        if brief_path.suffix != '.md' or not isinstance(content, str) or not content.strip():
            raise ValueError("brief requires a Markdown path and non-empty content")
        original = brief_path.read_text(encoding='utf-8') if brief_path.exists() else None
        staged.append((brief_path, original, content))
    if 'impl_claims' in manifest or ui or features:
        sections = [(path, manifest['impl_claims'])] if 'impl_claims' in manifest else []
        _write_claim_manifests(sections, root, dry, merge=False, converted=ui, implemented=features)
    if not dry:
        for target, original, content in staged:
            if original != content:
                _write_text_atomic(target, content)
    return 0


EVIDENCE_FIELDS = ("files", "symbols", "code_anchors", "verification_evidence")


def _claim_identity(claim):
    if not isinstance(claim, dict):
        raise ValueError("expected an object for each claim")
    requirement_id = claim.get("requirement_id")
    packet_id = claim.get("packet_id")
    attempt = claim.get("attempt", 1)
    if (not all(isinstance(value, str) and value.strip() for value in (requirement_id, packet_id))
            or type(attempt) is not int or attempt < 1):
        raise ValueError(f"invalid claim identity: {(requirement_id, packet_id, attempt)}")
    return requirement_id, packet_id, attempt


def _merge_evidence(previous, incoming, identity):
    digest = incoming.get("requirement_digest")
    if not isinstance(digest, str) or not digest.strip():
        raise ValueError(f"{identity}: requirement_digest is missing")
    if previous and previous.get("requirement_digest") != digest:
        raise ValueError(f"{identity}: conflicting requirement_digest")
    merged = dict(previous)
    for name, value in incoming.items():
        if name in EVIDENCE_FIELDS:
            existing = merged.get(name, [])
            if not isinstance(existing, list) or not isinstance(value, list):
                raise ValueError(f"{identity}: {name} must be a list")
            combined = list(existing)
            for item in value:
                if item not in combined:
                    combined.append(item)
            merged[name] = combined
        else:
            if name in merged and merged[name] != value:
                raise ValueError(f"{identity}: conflicting {name}")
            merged[name] = value
    return merged


def _write_claim_manifests(sections, root: Path, dry_run: bool, *, merge: bool,
                           converted=frozenset(), implemented=frozenset()):
    ledger_path = _project_path(root, 'spec/.i2h/impl-claims.json', 'spec/.i2h')
    ledger = (json.loads(ledger_path.read_text(encoding="utf-8")) if ledger_path.exists()
              else {"schema_version": 1, "claims": [], "executed_packets": []})
    plan = None
    claims = {}
    executed = set()
    for index, (path, section) in enumerate([(ledger_path, ledger), *sections]):
        try:
            if not isinstance(section, dict):
                raise ValueError("expected an object")
            if index != 0 and set(section) - {"claims", "executed_packets"}:
                raise ValueError("unsupported impl_claims fields")
            entries = section.get("claims", [])
            packets = section.get("executed_packets", [])
            if not isinstance(entries, list):
                raise ValueError("claims must be a list")
            if not isinstance(packets, list) or any(
                not isinstance(packet, str) or not packet.strip() for packet in packets
            ):
                raise ValueError("executed_packets must be a list of packet IDs")
            executed.update(packets)
            seen = set()
            for claim in entries:
                identity = _claim_identity(claim)
                if identity in seen:
                    raise ValueError(f"{identity}: duplicate claim identity")
                seen.add(identity)
                if index == 0:
                    claims[identity] = claim
                    continue
                if plan is None:
                    plan = load_plan(root)
                problem = claim_problem(root, *plan, claim)
                if problem:
                    raise ValueError(f"{identity}: {problem[0]}: {problem[1]}")
                if merge:
                    claim = _merge_evidence(claims.get(identity, {}), claim, identity)
                    problem = claim_problem(root, *plan, claim)
                    if problem:
                        raise ValueError(f"{identity}: merged evidence: {problem[0]}: {problem[1]}")
                claims[identity] = claim
            if index != 0:
                unsubstantiated = set(packets) - {identity[1] for identity in seen}
                if unsubstantiated:
                    raise ValueError(f"executed_packets without incoming claims: {', '.join(sorted(unsubstantiated))}")
        except ValueError as exc:
            raise ValueError(f"{path}: {exc}") from exc

    result = dict(ledger, claims=list(claims.values()), executed_packets=sorted(executed))
    if implemented:
        packets, requirements = plan or load_plan(root)
        needed = {feature: set() for feature in implemented}
        for packet_id, packet in packets.items():
            feature = packet.get('feature_id') or packet_id.rsplit('-', 1)[-1]
            if feature in needed:
                needed[feature].update((packet_id, ac) for ac in packet['requirement_ids'])
        candidate = set().union(*needed.values())
        valid = {(packet_id, ac) for ac, packet_id, attempt in claims
                 if (packet_id, ac) in candidate
                 and claim_problem(root, packets, requirements, claims[ac, packet_id, attempt]) is None}
        for feature, keys in needed.items():
            if not keys or keys - valid:
                raise ValueError(f"{feature}: feature closeout requires current claims for all planned ACs")
    if converted or implemented:
        closeout = dict(ledger.get('closeout', {}))
        for field, values in (('ui_converted', converted), ('features_implemented', implemented)):
            if values:
                closeout[field] = sorted(_ids(closeout.get(field, []), field) | values)
        result['closeout'] = closeout
    if not dry_run and result != ledger:
        _write_text_atomic(ledger_path, json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    if merge:
        action = "Would consolidate" if dry_run else "Consolidated"
        print(f"{action} {len(sections)} manifest(s), {len(claims)} ledger claims, {len(executed)} packets")
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", nargs="+", type=Path)
    parser.add_argument("--project-root", required=True, type=Path)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument("--merge-evidence", action="store_true",
                        help="Consolidate claim-only manifests into one ledger write")
    ns = parser.parse_args(argv)
    try:
        if ns.merge_evidence:
            sections = []
            for path in ns.manifest:
                manifest = json.loads(path.read_text(encoding="utf-8"))
                if not isinstance(manifest, dict) or set(manifest) != {"impl_claims"}:
                    raise ValueError(f"{path}: --merge-evidence accepts claim-only manifests")
                sections.append((path.resolve(), manifest["impl_claims"]))
            return _write_claim_manifests(sections, ns.project_root.resolve(), ns.dry_run, merge=True)
        if len(ns.manifest) != 1:
            parser.error("multiple manifests require --merge-evidence")
        path = ns.manifest[0]
        manifest = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(manifest, dict):
            raise ValueError(f"{path}: expected a manifest object")
        if 'operations' in manifest:
            if manifest.keys() & {'impl_claims', 'registry', 'ui_manifest', 'feature_index', 'brief'}:
                raise ValueError("legacy operations cannot be mixed with structured writeback")
            if ns.dry_run:
                if not WritebackApplier(ns.project_root)._validate_manifest(manifest):
                    return 1
                return 0
            return 0 if WritebackApplier(ns.project_root).apply_manifest(path) else 1
        supported = {'mode', 'id', 'registry', 'ui_manifest', 'feature_index', 'impl_claims', 'brief', 'notes'}
        if manifest.keys() - supported or not manifest.keys() & (supported - {'mode', 'id', 'notes'}):
            raise ValueError(f"unsupported structured writeback fields: {sorted(manifest.keys() - supported)}")
        return _claims_main(path, manifest, ns.project_root.resolve(), ns.dry_run)
    except (OSError, ValueError, TypeError, KeyError, AttributeError, RuntimeError) as exc:
        print(f"writeback: {exc}", file=sys.stderr)
        return 1

if __name__ == '__main__': sys.exit(main())

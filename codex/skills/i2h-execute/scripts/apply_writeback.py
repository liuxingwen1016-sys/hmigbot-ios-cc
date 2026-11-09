#!/usr/bin/env python3
"""
Apply Writeback Manifest

用途: 应用 writeback manifest，将 closer 产出的修改落盘到项目中
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, List, Any

# Structured writeback diagnostics are intentionally module-level: callers and
# tests can inspect what was applied, skipped, or warned without scraping CLI
# output.  They are reset by the caller between runs.
applied: list[str] = []
noops: list[str] = []
warns: list[str] = []


def _write_json_atomic(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def _apply_claims(manifest: dict, root: Path, dry_run: bool) -> int:
    """Apply the deterministic impl-claims section used by execute closers."""
    section = manifest.get("impl_claims")
    if not isinstance(section, dict):
        return 0
    path = root / "spec/.i2h/impl-claims.json"
    if path.exists():
        try:
            ledger = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            warns.append(f"malformed ledger preserved: {path}")
            return 1
        if not isinstance(ledger, dict) or not isinstance(ledger.get("claims", []), list):
            warns.append(f"malformed ledger preserved: {path}")
            return 1
    else:
        ledger = {"schema_version": 1, "claims": [], "executed_packets": []}
    claims = ledger.setdefault("claims", [])
    by_identity = {
        (c.get("requirement_id"), c.get("packet_id"), c.get("attempt", 1)): i
        for i, c in enumerate(claims) if isinstance(c, dict)
    }
    for claim in section.get("claims", []) or []:
        if not isinstance(claim, dict):
            warns.append("ignored non-object claim")
            continue
        identity = (claim.get("requirement_id"), claim.get("packet_id"), claim.get("attempt", 1))
        if identity in by_identity:
            claims[by_identity[identity]] = claim
            applied.append(f"claim:{identity[0]}:{identity[1]}:{identity[2]}")
        else:
            by_identity[identity] = len(claims)
            claims.append(claim)
            applied.append(f"claim:{identity[0]}:{identity[1]}:{identity[2]}")
    packets = ledger.setdefault("executed_packets", [])
    for packet in section.get("executed_packets", []) or []:
        if packet not in packets:
            packets.append(packet)
            applied.append(f"packet:{packet}")
        else:
            noops.append(f"packet:{packet}")
    if not dry_run:
        _write_json_atomic(path, ledger)
    return 0


def _apply_registry(manifest: dict, root: Path, dry_run: bool) -> int:
    section = manifest.get("registry")
    if not isinstance(section, dict) or not section.get("resolve"):
        return 0
    path = root / "spec/placeholder-registry.md"
    if not path.exists():
        warns.append(f"registry missing: {path}")
        return 0
    text = path.read_text(encoding="utf-8")
    requested = {str(v) for v in section.get("resolve", [])}
    seen: set[str] = set()
    lines = []
    for line in text.splitlines(keepends=True):
        if line.startswith("|"):
            cols = [c.strip() for c in line.strip().strip("|").split("|")]
            if cols and cols[0] in requested and len(cols) >= 4:
                seen.add(cols[0])
                # status is the fourth column for the canonical registry table.
                cols[3] = "resolved"
                newline = "| " + " | ".join(cols) + " |"
                line = newline + ("\n" if line.endswith("\n") else "")
                applied.append(f"registry:{cols[0]}")
            elif cols and cols[0] in requested:
                seen.add(cols[0])
        lines.append(line)
    for pid in sorted(requested - seen):
        noops.append(pid)
    if not dry_run:
        path.write_text("".join(lines), encoding="utf-8")
    return 0


def _structured_main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest")
    parser.add_argument("--project-root", default=".")
    parser.add_argument("--dry-run", action="store_true")
    ns = parser.parse_args(argv)
    try:
        manifest = json.loads(Path(ns.manifest).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        warns.append(str(exc))
        return 1
    root = Path(ns.project_root).resolve()
    code = _apply_claims(manifest, root, ns.dry_run)
    return code or _apply_registry(manifest, root, ns.dry_run)

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

def main():
    parser = argparse.ArgumentParser(
        description='应用 writeback manifest',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python3 apply_writeback.py spec/execution/writeback/batch-001-writeback.json --project-root .
  python3 apply_writeback.py spec/execution/writeback/group-001-writeback.json --project-root .
        """
    )

    parser.add_argument('manifest', help='Writeback manifest 文件路径')
    parser.add_argument('--project-root', required=True, help='项目根目录')
    parser.add_argument('--dry-run', action='store_true', help='仅显示将要执行的操作，不实际修改')
    parser.add_argument('--verbose', action='store_true', help='显示详细输出')

    args = parser.parse_args()

    print("=" * 60)
    print("🔧 Apply Writeback Manifest")
    print("=" * 60)
    print(f"Manifest: {args.manifest}")
    print(f"Project Root: {args.project_root}")
    if args.dry_run:
        print("模式: DRY RUN（不会实际修改文件）")
    print("=" * 60)

    # 创建应用器
    applier = WritebackApplier(args.project_root)

    # 应用 manifest
    if args.dry_run:
        print("\n⚠️  DRY RUN 模式暂未实现，将实际应用")

    success = applier.apply_manifest(args.manifest)

    if success:
        print("\n✅ Writeback 应用成功")
        return 0
    else:
        print("\n❌ Writeback 应用失败")
        return 1

# Importable reconciliation API used by i2h-execute tests and the Python fallback.
applied: list[str] = []
noops: list[str] = []
warns: list[str] = []

def _claims_main(manifest_path, project_root, dry=False):
    root=Path(project_root); manifest=json.loads(Path(manifest_path).read_text(encoding='utf-8'))
    if dry: return 0
    claims_doc=manifest.get('impl_claims')
    if claims_doc is not None:
        ledger=root/'spec/.i2h/impl-claims.json'; ledger.parent.mkdir(parents=True,exist_ok=True)
        if ledger.exists():
            try: current=json.loads(ledger.read_text(encoding='utf-8'))
            except Exception: return 1
        else: current={'claims':[],'executed_packets':[]}
        byid={(c.get('requirement_id'),c.get('packet_id'),c.get('attempt',1)):c for c in current.get('claims',[])}
        for c in claims_doc.get('claims',[]): byid[(c.get('requirement_id'),c.get('packet_id'),c.get('attempt',1))]=c; applied.append(c.get('requirement_id',''))
        current['claims']=list(byid.values()); current['executed_packets']=sorted(set(current.get('executed_packets',[]))|set(claims_doc.get('executed_packets',[])))
        ledger.write_text(json.dumps(current,ensure_ascii=False,indent=2),encoding='utf-8')
    registry=manifest.get('registry')
    if registry:
        path=root/'spec/placeholder-registry.md'
        if path.exists():
            text=path.read_text(encoding='utf-8'); ids=registry.get('resolve',[])
            found=set()
            lines=[]
            for line in text.splitlines():
                m=__import__('re').match(r'\|\s*(P-[^ |]+)\s*\|',line)
                if m and m.group(1) in ids:
                    found.add(m.group(1)); parts=line.split('|');
                    if len(parts)>4: parts[4]=' resolved '; line='|'.join(parts)
                lines.append(line)
            for ident in ids:
                if ident not in found: noops.append(ident)
            path.write_text('\n'.join(lines)+'\n',encoding='utf-8')
    return 0

def main(argv=None):
    parser=argparse.ArgumentParser(); parser.add_argument('manifest'); parser.add_argument('--project-root',required=True); parser.add_argument('--dry-run',action='store_true'); parser.add_argument('--verbose',action='store_true')
    ns=parser.parse_args(argv)
    if 'impl_claims' in json.loads(Path(ns.manifest).read_text(encoding='utf-8')) or 'registry' in json.loads(Path(ns.manifest).read_text(encoding='utf-8')):
        return _claims_main(ns.manifest,ns.project_root,ns.dry_run)
    return WritebackApplier(ns.project_root).apply_manifest(ns.manifest) and 0 or 1

if __name__ == '__main__': sys.exit(main())

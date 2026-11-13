"""Contract normalization and deterministic source fingerprints for Stage 1."""
from __future__ import annotations
import hashlib, json, os
from pathlib import Path
from typing import Any


def digest(path_or_bytes: Path | str | bytes) -> str:
    if isinstance(path_or_bytes, (str, Path)):
        data = Path(path_or_bytes).read_bytes()
    else:
        data = path_or_bytes
    return "sha256:" + hashlib.sha256(data).hexdigest()


def source_digest(root: Path | str) -> str:
    """Fingerprint production source and package inputs, excluding receipts and build output."""
    root = Path(root).resolve()
    excluded = {'.claude', '.git', '.hvigor', '.migbot', '.preview', 'build', 'node_modules', 'oh_modules', 'spec'}
    configs = {'build-profile.json5', 'hvigorfile.ts', 'local.properties', 'oh-package-lock.json5', 'oh-package.json5'}
    files = []
    for directory, folders, names in os.walk(root):
        folders[:] = [name for name in folders if name not in excluded and not name.startswith('.')]
        path = Path(directory)
        parts = path.relative_to(root).parts
        in_package = bool(parts and parts[0] in {'AppScope', 'hvigor'})
        in_module = any(parts[i:i + 2] == ('src', 'main') for i in range(len(parts) - 1))
        for name in names:
            file = path / name
            if in_package or in_module or name in configs or file.suffix == '.ets':
                if not file.resolve().is_relative_to(root):
                    raise ValueError(f'build input escapes project root: {file}')
                if file.is_file():
                    files.append(file)
    h = hashlib.sha256()
    for p in sorted(files):
        rel = p.relative_to(root).as_posix().encode()
        data = p.read_bytes()
        h.update(len(rel).to_bytes(8, "big")); h.update(rel)
        h.update(len(data).to_bytes(8, "big")); h.update(data)
    return "sha256:" + h.hexdigest()


def _safe_rel(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} is required")
    p = Path(value)
    if p.is_absolute() or ".." in p.parts:
        raise ValueError(f"{field} escapes project root")
    return p.as_posix()


def normalize(data: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise ValueError("contract must be an object")
    out = dict(data)
    raw_pages = data.get("pages")
    pages: list[dict[str, Any]]
    if raw_pages is not None:
        if not isinstance(raw_pages, list):
            raise ValueError("pages must be an array")
        pages = [dict(x) for x in raw_pages if isinstance(x, dict)]
        if len(pages) != len(raw_pages):
            raise ValueError("pages entries must be objects")
    elif data.get("page_ids") is not None:
        ids = data.get("page_ids") or []
        states = data.get("state_ids") or []
        outputs = data.get("page_outputs")
        if not isinstance(outputs, dict) or len(ids) != len(states):
            raise ValueError("legacy arrays require page_ids, state_ids and page_outputs")
        pages = []
        for i, page_id in enumerate(ids):
            if page_id not in outputs:
                raise ValueError(f"missing output mapping for {page_id}")
            pages.append({"page_id": page_id, "state_id": states[i], "output_file": outputs[page_id]})
    elif any(k in data for k in ("page_id", "state_id", "output_file")):
        if "page_id" not in data or "state_id" not in data or "output_file" not in data:
            raise ValueError("legacy singular contract requires explicit page binding")
        pages = [{"page_id": data["page_id"], "state_id": data["state_id"], "output_file": data["output_file"]}]
    else:
        pages = []
    seen: set[tuple[str, str]] = set(); outputs: set[str] = set()
    normalized = []
    for page in pages:
        page_id = page.get("page_id"); state_id = page.get("state_id")
        if not isinstance(page_id, str) or not page_id or not isinstance(state_id, str) or not state_id:
            raise ValueError("page_id and state_id are required")
        output_file = _safe_rel(page.get("output_file"), "output_file")
        key = (page_id, state_id)
        if key in seen or output_file in outputs:
            raise ValueError("duplicate page binding")
        seen.add(key); outputs.add(output_file)
        row = dict(page); row.update(page_id=page_id, state_id=state_id, output_file=output_file)
        normalized.append(row)
    out["pages"] = normalized
    if "entry_file" in out and out["entry_file"] is not None:
        out["entry_file"] = _safe_rel(out["entry_file"], "entry_file")
    if "preview_host_file" in out and out["preview_host_file"] is not None:
        out["preview_host_file"] = _safe_rel(out["preview_host_file"], "preview_host_file")
    if "target_files" in out:
        out["target_files"] = [_safe_rel(v, "target_file") for v in out.get("target_files", [])]
    return out


def read_contract(path: Path | str) -> dict[str, Any]:
    return normalize(json.loads(Path(path).read_text(encoding="utf-8")))

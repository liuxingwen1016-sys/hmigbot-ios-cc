"""Static validation of approved iOS UI delivery outputs and their receipts."""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path, PureWindowsPath

from .stage1_reachability import _resolve
from .stage1_wiring_checks import check_requirements


IDENTIFIER = r"[A-Za-z_$][\w$]*"
TRIVIA = re.compile(r"(?P<comment>//[^\r\n]*|/\*[\s\S]*?\*/)|(?P<string>\"(?:\\.|[^\"\\])*\"|'(?:\\.|[^'\\])*'|`(?:\\.|[^`\\])*`)")
COMPONENT = re.compile(rf"\b(?:struct|class)\s+({IDENTIFIER})\s*[^{{;]*\{{")
CONTAINERS = frozenset({
    "Blank", "Column", "Flex", "ForEach", "Grid", "GridItem", "LazyForEach", "List",
    "ListItem", "Navigation", "NavDestination", "RelativeContainer", "Repeat",
    "Row", "Scroll", "Stack", "Swiper", "TabContent", "Tabs", "WaterFlow",
})


def _code(text: str, *, keep_strings: bool = False) -> str:
    return TRIVIA.sub(
        lambda match: match[0] if keep_strings and match.lastgroup == "string"
        else re.sub(r"[^\r\n]", " ", match[0]),
        text,
    )


def _block(text: str, start: int) -> str | None:
    depth = 1
    for index in range(start, len(text)):
        depth += (text[index] == "{") - (text[index] == "}")
        if depth == 0:
            return text[start:index]
    return None


def _method(text: str, name: str) -> str | None:
    declaration = re.search(
        rf"(?<![\w.$]){re.escape(name)}\s*\([^)]*\)\s*(?::\s*[\w.<>,\[\] |]+)?\s*\{{",
        text,
    )
    return _block(text, declaration.end()) if declaration else None


def _component_bodies(text: str) -> dict[str, str]:
    return {
        match[1]: body for match in COMPONENT.finditer(text)
        if (body := _block(text, match.end())) is not None
    }


def _calls(body: str, *, methods: bool = False) -> set[str]:
    if methods:
        return set(re.findall(rf"\bthis\s*\.\s*({IDENTIFIER})(?![\w$])", body))
    return set(re.findall(r"(?<![\w.])([A-Z][\w$]*)\s*\(", body))


def _reachable(component: str, entry: str) -> dict[str, str]:
    pending = [entry]
    visited = {}
    while pending:
        name = pending.pop()
        if name in visited:
            continue
        body = _method(component, name)
        if body is not None:
            visited[name] = body
            pending.extend(_calls(body, methods=True) - visited.keys())
    return visited


def _renders(component: str, builder: str) -> bool:
    return any(_calls(body) - CONTAINERS for body in _reachable(component, builder).values())


def _project_file(root: Path, value: object) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("a project file path is required")
    path = (root / value).resolve()
    if not path.is_relative_to(root) or (PureWindowsPath(value).is_absolute() and not Path(value).is_absolute()):
        raise ValueError(f"file escapes project root: {value}")
    return path


def _read_object(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("JSON must contain an object")
    return value


def _states(rows: object) -> set[str]:
    if not isinstance(rows, list) or not rows:
        raise ValueError("required_states must contain at least one state")
    names = set()
    for row in rows:
        name = row.get("state_id") if isinstance(row, dict) else None
        if not isinstance(name, str) or not name.strip() or name in names:
            raise ValueError("each required state needs a unique state_id")
        names.add(name)
    return names


def _imports(root: Path, source: str, host: Path, output: Path, symbol: str) -> set[str]:
    names = set()
    pattern = r"^\s*import\s*\{([^}]*)\}\s*from\s*['\"]([^'\"]+)['\"]"
    for group, module in re.findall(pattern, _code(source, keep_strings=True), re.M):
        if _resolve(root, host, module) != output:
            continue
        for item in group.split(","):
            parts = item.strip().split()
            if parts and parts[0] == symbol:
                names.add(parts[-1])
    return names


def _host_is_bound(root: Path, output: Path, integration: dict, child: str) -> bool:
    host_file = _project_file(root, integration.get("host_file"))
    slot = integration.get("host_builder")
    if not isinstance(slot, str) or integration.get("child_symbol") != child:
        return False
    owner, _, builder = slot.rpartition(".")
    owner = owner or integration.get("host_symbol")
    source = host_file.read_text(encoding="utf-8")
    bindings = {child} if host_file == output else _imports(root, source, host_file, output, child)
    components = _component_bodies(_code(source))
    scopes = [components.get(owner, "")] if owner else components.values()
    matches = []
    for component in scopes:
        reachable = _reachable(component, "build")
        body = reachable.get(builder)
        if body is not None:
            mount = integration.get("mount")
            if mount in {"bindSheet", "bindContentCover"}:
                binding = rf"\.{mount}\s*\([^,]+,\s*this\s*\.\s*{re.escape(builder)}\b"
                if not any(re.search(binding, method) for method in reachable.values()):
                    continue
            matches.append(bool(bindings & _calls(body)))
    return matches == [True]


def host_slots(unit: dict) -> list:
    value = unit.get("integration")
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def _add(errors: list[dict], code: str, detail: str, *, root_cause: str = "product_defect", **fields) -> None:
    errors.append({"code": code, "detail": detail, "root_cause": root_cause, **fields})


def _read_packets(root: Path, inventory_path: Path, index: str | None, errors: list[dict]) -> dict:
    if not index:
        return {}
    try:
        path = _project_file(root, index)
        data = _read_object(path)
        if data.get("schema_version") != 2:
            raise ValueError("frozen inputs index must use schema_version 2")
        source = data.get("inventory_source")
        actual = hashlib.sha256(inventory_path.read_bytes()).hexdigest()
        if not isinstance(source, dict) or str(source.get("sha256")).removeprefix("sha256:") != actual:
            raise ValueError("inputs index is not bound to the approved inventory SHA-256")
        packets = data.get("packets")
        if not isinstance(packets, list) or not packets:
            raise ValueError("inputs index must contain at least one packet")
        result = {}
        for row in packets:
            name = row.get("unit_id") if isinstance(row, dict) else None
            if not isinstance(name, str) or not name or name in result:
                raise ValueError("inputs index contains a missing or duplicate unit_id")
            result[name] = row
        return result
    except FileNotFoundError:
        _add(errors, "inputs_index_missing", "frozen inputs index does not exist", root_cause="information_gap", path=index)
    except (OSError, ValueError, UnicodeError) as exc:
        _add(errors, "inputs_index_invalid", str(exc), root_cause="information_gap", path=index)
    return {}


def _check_report(root: Path, unit_id: str, states: set[str], packet: dict | None,
                  fields: dict, errors: list[dict], warnings: list[dict]) -> None:
    path = _project_file(root, f"spec/execution/conversion-reports/{unit_id}.json")
    try:
        report = _read_object(path)
    except FileNotFoundError:
        _add(errors, "conversion_report_missing", "required conversion report is absent",
             state_ids=sorted(states), **fields)
        return
    except (OSError, ValueError, UnicodeError) as exc:
        _add(errors, "conversion_report_invalid", str(exc), **fields)
        return
    if report.get("unit_id") != unit_id:
        _add(errors, "conversion_report_unit_mismatch", "conversion report names a different unit", **fields)
        return
    dispatch = report.get("dispatch_id")
    packet_hash = report.get("packet_sha256")
    if not isinstance(dispatch, str) or not dispatch.strip() or not isinstance(packet_hash, str) or not re.fullmatch(
        r"(?:sha256:)?[0-9a-fA-F]{64}", packet_hash
    ):
        _add(errors, "conversion_report_unbound", "conversion report requires dispatch_id and packet_sha256", **fields)
    if packet is not None:
        for key in ("dispatch_id", "packet_sha256"):
            expected = packet.get(key)
            received = report.get(key)
            if key == "packet_sha256" and isinstance(expected, str) and isinstance(received, str):
                expected, received = (value.removeprefix("sha256:").lower() for value in (expected, received))
            if expected and received != expected:
                _add(errors, "conversion_report_stale", f"conversion report does not match the frozen {key}", **fields)
        if "required_states" in packet and _states(packet["required_states"]) != states:
            _add(errors, "inputs_packet_state_mismatch", "frozen packet states differ from the approved unit",
                 root_cause="information_gap", **fields)
        def input_ids(rows):
            if not isinstance(rows, list):
                raise ValueError("input declarations must be arrays")
            return {item["input_id"] for item in rows
                    if isinstance(item, dict) and isinstance(item.get("input_id"), str)}

        required = input_ids(packet.get("required_inputs", []))
        applied = input_ids(report.get("input_applications", []))
        for name in sorted(required - applied):
            _add(errors, "required_input_missing", "conversion report omitted a required input", input_id=name, **fields)
    rows = report.get("state_implementations")
    if not isinstance(rows, list):
        rows = []
    by_id = {}
    for row in rows:
        name = row.get("state_id") if isinstance(row, dict) else None
        if not isinstance(name, str) or not name or name in by_id:
            _add(errors, "state_implementation_invalid", "state implementation has a missing or duplicate state_id", **fields)
            continue
        by_id[name] = row
    for name in sorted(states):
        if name not in by_id:
            _add(errors, "required_state_missing", "conversion report omitted a required state", state_id=name, **fields)
        elif not isinstance(by_id[name].get("symbol"), str) or not by_id[name]["symbol"].strip():
            warnings.append({"code": "diagnostic_state_symbol", "state_id": name, **fields})


def _check_unit(root: Path, unit: dict, packet: dict | None, errors: list[dict], warnings: list[dict], *, check_host: bool = True) -> None:
    unit_id = unit["unit_id"]
    output = unit.get("output")
    fields = {"unit_id": unit_id, "page_id": unit.get("page_id")}
    try:
        states = _states(unit.get("required_states"))
    except ValueError as exc:
        _add(errors, "required_states_invalid", str(exc), **fields)
        states = set()
    if not isinstance(output, dict):
        _add(errors, "output_missing", "unit has no declared output", **fields)
        return
    file = output.get("file")
    fields["file"] = file
    try:
        path = _project_file(root, file)
        source = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        _add(errors, "output_missing", "declared output file is absent", **fields)
        return
    except (OSError, ValueError, UnicodeError) as exc:
        _add(errors, "output_invalid", str(exc), **fields)
        return
    symbol, builder = output.get("symbol"), output.get("builder")
    if not isinstance(symbol, str) or not re.fullmatch(IDENTIFIER, symbol):
        _add(errors, "output_symbol_missing", "output must declare a valid component symbol", **fields)
        return
    component = _component_bodies(_code(source)).get(symbol)
    if component is None:
        _add(errors, "output_symbol_missing", "declared component is not defined in the output file", symbol=symbol, **fields)
        return
    role = unit.get("presentation_role")
    builders = unit.get("required_builders") or []
    if not isinstance(builders, list) or any(not isinstance(name, str) for name in builders):
        _add(errors, "required_builders_invalid", "required_builders must be an array of names", **fields)
        builders = []
    if role != "headless":
        reachable = _reachable(component, builder) if isinstance(builder, str) else {}
        for name in [builder, *builders]:
            if not isinstance(name, str) or name not in reachable or not _renders(component, name):
                _add(errors, "required_builder_empty", "declared builder is unreachable or does not render UI", builder=name, **fields)
    if role == "embedded" and re.search(r"\bNavDestination\s*\(", component):
        _add(errors, "embedded_navigation_wrapper", "embedded content cannot own a NavDestination", **fields)
    integrations = host_slots(unit) if check_host else []
    if check_host and not integrations and role in {"embedded", "hosted_destination"}:
        _add(errors, "required_host_slot_missing", "approved unit does not declare a host file and builder", **fields)
    for integration in integrations:
        try:
            bound = isinstance(integration, dict) and _host_is_bound(root, path, integration, symbol)
        except (OSError, ValueError, UnicodeError):
            bound = False
        if not bound:
            _add(errors, "required_host_slot_unbound", "required host slot does not mount this output from build",
                 host_file=integration.get("host_file") if isinstance(integration, dict) else None,
                 host_builder=integration.get("host_builder") if isinstance(integration, dict) else None, **fields)
    try:
        _check_report(root, unit_id, states, packet, fields, errors, warnings)
    except ValueError as exc:
        _add(errors, "conversion_report_invalid", str(exc), **fields)


def inspect_delivery(root: Path, inventory_path: Path, inventory: dict,
                     inputs_index: str | None, wiring_contract: str | None) -> dict:
    errors, warnings = [], []
    required, wired = [], []
    packets = _read_packets(root, inventory_path, inputs_index, errors)
    units = inventory.get("units")
    seen = set()
    if not isinstance(units, list) or not units:
        _add(errors, "no_selected_page_bindings", "approved inventory has no delivery units", root_cause="information_gap")
        units = []
    for unit in units:
        name = unit.get("unit_id") if isinstance(unit, dict) else None
        if not isinstance(name, str) or not re.fullmatch(r"[\w.-]+", name) or name in {".", ".."} or name in seen:
            _add(errors, "delivery_unit_invalid", "unit has a missing, unsafe or duplicate unit_id",
                 root_cause="information_gap", unit_id=name)
            continue
        seen.add(name)
        if unit.get("required") is False:
            continue
        required.append(name)
        before = len(errors)
        packet = packets.get(name)
        if inputs_index and packets and packet is None:
            _add(errors, "inputs_packet_missing", "frozen inputs index omits this required unit",
                 root_cause="information_gap", unit_id=name)
        _check_unit(root, unit, packet, errors, warnings)
        if len(errors) == before:
            wired.append(name)
    if units and not required and not errors:
        _add(errors, "no_selected_page_bindings", "approved inventory has no required delivery units", root_cause="information_gap")
    if wiring_contract:
        try:
            contract_path = _project_file(root, wiring_contract)
            if not contract_path.is_file():
                raise ValueError("wiring contract is missing")
            for error in check_requirements(root, contract_path)["errors"]:
                _add(errors, "required_wiring_unresolved", error["reason"], wiring_id=error["id"])
        except (OSError, ValueError, KeyError, TypeError, AttributeError, UnicodeError) as exc:
            _add(errors, "wiring_contract_invalid", str(exc), root_cause="information_gap")
    return {
        "schema_version": 2, "gate": "stage1_ui", "status": "BLOCKED" if errors else "PASS",
        "scope": inventory.get("scope"), "result_scope": "STRUCTURAL_ONLY", "stage1_complete": False,
        "visual_verified": False, "arrival_verified": False, "inventory": inventory_path.relative_to(root).as_posix(),
        "required_units": len(required), "delivered_units": len(wired), "wired_units": wired,
        "errors": errors, "warnings": warnings, "failure_findings": errors, "policy_gate": "execute.stage1-g1",
    }

"""
Ontology-backed validator for generated agent service YAML.

- Builds an OWL individual graph mirroring the YAML structure
- Runs an OWL reasoner to classify the Service as Valid/Invalid
- Performs procedural checks to generate explicit ConstraintViolations for usability

This module is standalone and does not modify existing project files.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

import yaml

try:
    # Lazy import to avoid hard dependency until the user installs it
    from owlready2 import (  # type: ignore
        onto_path,
        get_ontology,
        Thing,
        sync_reasoner,
        close_world,
    )
except Exception as exc:  # pragma: no cover - only triggers if not installed
    owlready2_import_error = exc
    get_ontology = None  # type: ignore


class OntologyValidationError(Exception):
    pass


def _find_return_step(obj: Any) -> bool:
    if isinstance(obj, dict):
        for key, value in obj.items():
            if key == "return":
                return True
            if _find_return_step(value):
                return True
    elif isinstance(obj, list):
        for item in obj:
            if _find_return_step(item):
                return True
    return False


def _collect_http_calls(steps: Dict[str, Any]) -> List[Tuple[str, str, Dict[str, Any]]]:
    """Collect entries that look like HTTP calls.

    A step is considered an HTTP call if it has `call: http.get` or `call: http.post`.
    Returns list of (step_name, call_type, http_args_dict)
    """
    http_calls: List[Tuple[str, str, Dict[str, Any]]] = []
    for step_name, step_body in steps.items():
        if not isinstance(step_body, dict):
            continue
        call_val = step_body.get("call")
        if isinstance(call_val, str) and call_val in ("http.get", "http.post"):
            args = step_body.get("args") or {}
            if isinstance(args, dict):
                http_calls.append((step_name, call_val, args))
    return http_calls


def _extract_steps(parsed_yaml: Dict[str, Any]) -> Dict[str, Any]:
    """Extract DSL steps from a YAML mapping.

    All top-level keys except the declaration block (keys 'declare' or 'declaration')
    are treated as steps when their values are mappings.
    """
    steps: Dict[str, Any] = {}
    for key, value in parsed_yaml.items():
        if key in ("declare", "declaration"):
            continue
        if isinstance(value, dict):
            steps[key] = value
    return steps


def _load_ontology(ontology_dir: Path) -> Any:
    if get_ontology is None:
        raise OntologyValidationError(
            "owlready2 is not installed. Please install Owlready2 and retry."
        )
    onto_path.append(str(ontology_dir))
    onto = get_ontology("agent_service.owl").load()
    return onto


CLASS_NAMES = [
    "Service",
    "Step",
    "HttpCall",
    "Return",
    "Declaration",
    "Template",
    "Assign",
    "Switch",
    "SwitchCase",
    "Mock",
    "FormatMessages",
    "DmapperHttpCall",
    "GET",
    "POST",
    "ConstraintViolation",
]

PROPERTY_NAMES = [
    "hasStep",
    "hasReturn",
    "hasHttpMethod",
    "hasUrl",
    "usesBody",
    "hasViolation",
    "hasDeclaration",
    "hasVersion",
    "hasDescription",
    "hasAccepts",
    "hasReturns",
    "hasNamespace",
    "hasTemplate",
    "hasRequestType",
    "hasResult",
    "hasSwitch",
    "hasNext",
    "hasResponse",
    "canBeSkipped",
    "canSleep",
    "canReloadDsl",
]


def _resolve_ontology_references(onto: Any) -> tuple[Dict[str, Any], Dict[str, Any]]:
    """Resolve required ontology classes and properties, raising if any are missing."""
    missing: List[str] = []
    class_refs: Dict[str, Any] = {}
    property_refs: Dict[str, Any] = {}

    for name in CLASS_NAMES:
        entity = getattr(onto, name, None)
        if entity is None:
            missing.append(name)
        else:
            class_refs[name] = entity

    for name in PROPERTY_NAMES:
        entity = getattr(onto, name, None)
        if entity is None:
            missing.append(name)
        else:
            property_refs[name] = entity

    if missing:
        missing_list = ", ".join(sorted(missing))
        raise OntologyValidationError(
            f"Ontology classes/properties missing. Ensure agent_service.owl is intact. Missing: {missing_list}"
        )

    return class_refs, property_refs


def _build_service_individual(
    onto: Any,
    class_refs: Dict[str, Any],
    service_name: str,
    declaration: Dict[str, Any],
    method_str: str,
    steps: Dict[str, Any],
    has_return: bool,
    violations: List[str],
) -> Any:
    """Create and populate the service individual with steps, declaration, and violations."""
    Service = class_refs["Service"]
    DeclarationClass = class_refs["Declaration"]
    TemplateClass = class_refs["Template"]
    AssignClass = class_refs["Assign"]
    SwitchClass = class_refs["Switch"]
    SwitchCaseClass = class_refs["SwitchCase"]
    MockClass = class_refs["Mock"]
    StepClass = class_refs["Step"]
    HttpCall = class_refs["HttpCall"]
    DmapperHttpCallClass = class_refs["DmapperHttpCall"]
    ReturnClass = class_refs["Return"]
    GETClass = class_refs["GET"]
    POSTClass = class_refs["POST"]
    ConstraintViolation = class_refs["ConstraintViolation"]

    service_ind = Service(service_name, namespace=onto)

    if declaration:
        declaration_ind = DeclarationClass(f"{service_name}_declaration", namespace=onto)
        service_ind.hasDeclaration.append(declaration_ind)
        if declaration.get("version"):
            declaration_ind.hasVersion.append(declaration.get("version"))
        if declaration.get("description"):
            declaration_ind.hasDescription.append(declaration.get("description"))
        if declaration.get("accepts"):
            declaration_ind.hasAccepts.append(declaration.get("accepts"))
        if declaration.get("returns"):
            declaration_ind.hasReturns.append(declaration.get("returns"))
        if declaration.get("namespace"):
            declaration_ind.hasNamespace.append(declaration.get("namespace"))

    if method_str == "GET":
        method_ind = GETClass(f"{service_name}_method", namespace=onto)
        service_ind.hasHttpMethod.append(method_ind)
    elif method_str == "POST":
        method_ind = POSTClass(f"{service_name}_method", namespace=onto)
        service_ind.hasHttpMethod.append(method_ind)

    for step_name, step_body in steps.items():
        step_data = step_body if isinstance(step_body, dict) else {}

        if "template" in step_data:
            step_ind = TemplateClass(step_name, namespace=onto)
            if step_data.get("template"):
                step_ind.hasTemplate.append(step_data.get("template"))
            if step_data.get("requestType"):
                step_ind.hasRequestType.append(step_data.get("requestType"))
            if step_data.get("result"):
                step_ind.hasResult.append(step_data.get("result"))
        elif "assign" in step_data:
            step_ind = AssignClass(step_name, namespace=onto)
        elif "switch" in step_data:
            step_ind = SwitchClass(step_name, namespace=onto)
            switch_cases = step_data.get("switch")
            if isinstance(switch_cases, list):
                for i, _ in enumerate(switch_cases):
                    case_ind = SwitchCaseClass(f"{step_name}_case_{i}", namespace=onto)
                    step_ind.hasSwitch.append(case_ind)
        elif step_data.get("call") == "reflect.mock":
            step_ind = MockClass(step_name, namespace=onto)
            response = step_data.get("args", {}).get("response")
            if response is not None:
                step_ind.hasResponse.append(str(response))
        else:
            call_val = step_data.get("call")
            is_http = isinstance(call_val, str) and call_val in ("http.get", "http.post")
            if is_http:
                call_payload: Dict[str, Any] = step_data.get("args") or {}
                url_val = call_payload.get("url")
                if isinstance(url_val, str) and "[#DMAPPER]" in url_val:
                    step_ind = DmapperHttpCallClass(step_name, namespace=onto)
                else:
                    step_ind = HttpCall(step_name, namespace=onto)
                if isinstance(url_val, str) and url_val.strip():
                    step_ind.hasUrl = [url_val]
                uses_body = False
                if isinstance(call_payload, dict):
                    if "body" in call_payload or "plaintext" in call_payload:
                        uses_body = True
                    ct = call_payload.get("contentType")
                    if isinstance(ct, str) and ct.lower() in ("formdata", "plaintext"):
                        uses_body = True
                step_ind.usesBody = [bool(uses_body)]
            else:
                step_ind = StepClass(step_name, namespace=onto)

        if isinstance(step_data, dict):
            skip_val = step_data.get("skip")
            if skip_val is not None:
                step_ind.canBeSkipped.append(skip_val)
            sleep_val = step_data.get("sleep")
            if sleep_val is not None:
                step_ind.canSleep.append(sleep_val)
            reload_val = step_data.get("reloadDsl")
            if reload_val is not None:
                step_ind.canReloadDsl.append(reload_val)

        service_ind.hasStep.append(step_ind)

    if has_return:
        ret_ind = ReturnClass(f"{service_name}_return", namespace=onto)
        service_ind.hasReturn.append(ret_ind)

    for idx, msg in enumerate(violations, start=1):
        violation_ind = ConstraintViolation(f"{service_name}_violation_{idx}", namespace=onto)
        violation_ind.label = [msg]
        service_ind.hasViolation.append(violation_ind)

    return service_ind


def validate_service_with_ontology(yaml_text: str, ontology_dir: Path | None = None) -> Dict[str, Any]:
    """Validate a service YAML using the ontology and simple procedural checks.

    Returns a dict with fields:
      - valid: bool
      - classification: "Valid" | "Invalid" | "Unknown"
      - violations: List[str]
    """
    parsed = yaml.safe_load(yaml_text)
    if not isinstance(parsed, dict):
        raise OntologyValidationError("Top-level YAML must be a mapping/dict")

    declaration = parsed.get("declaration", {}) or {}
    service_name: str = declaration.get("name") or "unnamed_service"
    method_str: str = (
        declaration.get("httpMethod")
        or declaration.get("http_method")
        or declaration.get("method")
        or ""
    ).upper()

    steps = parsed.get("steps") or {}
    if not isinstance(steps, dict) or not steps:
        steps = _extract_steps(parsed)

    http_calls = _collect_http_calls(steps)
    has_return = _find_return_step(parsed)

    violations: List[str] = []
    if not declaration:
        violations.append("No 'declaration' block found")
    if not has_return:
        violations.append("No 'return' step found")
    if not declaration.get("version"):
        violations.append("Declaration is missing 'version' field")
    if not declaration.get("description"):
        violations.append("Declaration is missing 'description' field")
    if not declaration.get("accepts"):
        violations.append("Declaration is missing 'accepts' field")
    if not declaration.get("returns"):
        violations.append("Declaration is missing 'returns' field")
    if not declaration.get("namespace"):
        violations.append("Declaration is missing 'namespace' field")

    for step_name, step_body in steps.items():
        if not isinstance(step_body, dict):
            continue
        if "template" in step_body:
            if "requestType" not in step_body:
                violations.append(f"Template step '{step_name}' is missing 'requestType' field")
            if "result" not in step_body:
                violations.append(f"Template step '{step_name}' is missing 'result' field")
        if "switch" in step_body:
            if not isinstance(step_body["switch"], list):
                violations.append(f"Switch step '{step_name}' must have a list of cases")
        if step_body.get("call") == "reflect.mock":
            if "args" not in step_body:
                violations.append(f"Mock step '{step_name}' is missing 'args' field")
            elif "response" not in step_body.get("args", {}):
                violations.append(f"Mock step '{step_name}' is missing 'response' field in 'args'")
        if "skip" in step_body and not isinstance(step_body["skip"], bool):
            violations.append(f"Step '{step_name}' has non-boolean skip value")
        if "sleep" in step_body and not isinstance(step_body["sleep"], int):
            violations.append(f"Step '{step_name}' has non-integer sleep value")
        if "reloadDsl" in step_body and not isinstance(step_body["reloadDsl"], bool):
            violations.append(f"Step '{step_name}' has non-boolean reloadDsl value")

    for step_name, call_type, payload in http_calls:
        url = payload.get("url")
        if not isinstance(url, str) or not url.strip():
            violations.append(f"Step '{step_name}' missing or empty url")
        if isinstance(url, str) and "[#DMAPPER]" in url and call_type != "http.post":
            violations.append(f"Step '{step_name}' is an HTTP GET call to DMAPPER, which is not allowed.")
        if isinstance(url, str) and "[#DMAPPER]" in url and call_type == "http.post" and step_name != "formatMessages":
            violations.append(f"Step '{step_name}' is an HTTP POST call to DMAPPER, but it is not the formatMessages step.")
        if isinstance(url, str) and "${serviceInput}" in url:
            violations.append(f"Step '{step_name}' should not embed 'serviceInput' directly in the request URL.")
        if call_type == "http.get" and ("body" in payload or "plaintext" in payload):
            violations.append(f"GET step '{step_name}' should not define a body")
        if call_type == "http.post" and ("body" not in payload and "plaintext" not in payload):
            violations.append(f"POST step '{step_name}' should define a body or plaintext")
        query_payload = payload.get("query")
        if isinstance(query_payload, dict):
            for key, value in query_payload.items():
                if isinstance(value, str) and "${serviceInput}" in value:
                    violations.append(f"Query parameter '{key}' in step '{step_name}' should not reference 'serviceInput'.")

    # Formatting checks
    for idx, line in enumerate(yaml_text.splitlines(), start=1):
        if line.strip() == "" and line != "":
            violations.append(f"Line {idx} contains whitespace-only characters; remove the stray spaces.")

    ordered_step_names = list(steps.keys())
    for step_name in ordered_step_names[1:]:
        if not re.search(rf"\n\n{re.escape(step_name)}:", yaml_text):
            violations.append(f"Step '{step_name}' should be separated from the previous step by an empty line.")

    prepare_block = parsed.get("prepare") or {}
    prepare_assign = prepare_block.get("assign") if isinstance(prepare_block, dict) else {}
    if not isinstance(prepare_assign, dict):
        prepare_assign = {}

    uses_api_url_variable = any("${apiUrl}" in str(step_body) for step_body in steps.values())
    if uses_api_url_variable and "apiUrl" not in prepare_assign:
        violations.append("The workflow references '${apiUrl}' but no 'apiUrl' value is assigned in the prepare block.")

    if ontology_dir is None:
        ontology_dir = Path(__file__).resolve().parent.parent / "ontology"

    onto = _load_ontology(ontology_dir)
    class_refs, property_refs = _resolve_ontology_references(onto)
    service_ind = _build_service_individual(
        onto=onto,
        class_refs=class_refs,
        service_name=service_name,
        declaration=declaration,
        method_str=method_str,
        steps=steps,
        has_return=has_return,
        violations=violations,
    )

    close_world(
        service_ind,
        Properties=[
            property_refs["hasDeclaration"],
            property_refs["hasReturn"],
            property_refs["hasStep"],
            property_refs["hasHttpMethod"],
        ],
        recursive=True,
    )

    with onto:
        try:
            sync_reasoner()
        except Exception:
            pass

    Valid_Service = onto.search_one(iri="*Valid_Service")
    Invalid_Service = onto.search_one(iri="*Invalid_Service")

    classification = "Unknown"
    if Valid_Service and service_ind in Valid_Service.instances():
        classification = "Valid"
    elif Invalid_Service and service_ind in Invalid_Service.instances():
        classification = "Invalid"

    is_valid = len(violations) == 0 and classification in ("Valid", "Unknown")

    return {
        "valid": is_valid,
        "classification": classification,
        "violations": violations,
    }


def main(argv: List[str]) -> int:
    if len(argv) < 2:
        print("Usage: python -m validator.ontology_validator <path_to_yaml>")
        return 2
    yaml_path = Path(argv[1])
    if not yaml_path.exists():
        print(f"File not found: {yaml_path}")
        return 2
    yaml_text = yaml_path.read_text(encoding="utf-8")
    try:
        result = validate_service_with_ontology(yaml_text)
    except OntologyValidationError as e:
        print(f"Validation error: {e}")
        return 1
    print("Ontology validation result:")
    print(f"  valid: {result['valid']}")
    print(f"  classification: {result['classification']}")
    if result["violations"]:
        print("  violations:")
        for v in result["violations"]:
            print(f"    - {v}")
    else:
        print("  violations: none")
    return 0 if result["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))

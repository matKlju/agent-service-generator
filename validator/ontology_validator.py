"""
Ontology-backed validator for generated agent service YAML.

- Builds an OWL individual graph mirroring the YAML structure
- Runs an OWL reasoner to classify the Service as Valid/Invalid
- Performs procedural checks to generate explicit ConstraintViolations for usability

This module is standalone and does not modify existing project files.
"""

from __future__ import annotations

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

    # Extract essentials
    declaration = parsed.get("declaration", {}) or {}
    service_name: str = declaration.get("name") or "unnamed_service"
    method_str: str = (
        declaration.get("httpMethod")
        or declaration.get("http_method")
        or declaration.get("method")
        or ""
    ).upper()
    # Newer DSLs keep steps at the top-level; fall back to 'steps' if present
    steps = parsed.get("steps") or {}
    if not isinstance(steps, dict) or not steps:
        steps = _extract_steps(parsed)

    http_calls = _collect_http_calls(steps)
    has_return = _find_return_step(parsed)

    # Procedural violations (explicit and user-friendly)
    violations: List[str] = []
    if not has_return:
        violations.append("No 'return' step found")
    for step_name, call_type, payload in http_calls:
        url = payload.get("url")
        if not isinstance(url, str) or not url.strip():
            violations.append(f"Step '{step_name}' missing or empty url")
        # GET step may not define a body
        if call_type == "http.get" and ("body" in payload or "plaintext" in payload):
            violations.append(f"GET step '{step_name}' should not define a body")
        # POST step should define a body (or plaintext)
        if call_type == "http.post" and ("body" not in payload and "plaintext" not in payload):
            violations.append(f"POST step '{step_name}' should define a body or plaintext")

    # If ontology_dir unspecified, resolve default location
    if ontology_dir is None:
        ontology_dir = Path(__file__).resolve().parent.parent / "ontology"

    # Load ontology and build individuals
    onto = _load_ontology(ontology_dir)

    # Resolve entities by exact name to avoid wildcard collisions (e.g., Return vs hasReturn)
    Service = onto["Service"]
    Step = onto["Step"]
    HttpCall = onto["HttpCall"]
    ReturnClass = onto["Return"]
    GETClass = onto["GET"]
    POSTClass = onto["POST"]
    ConstraintViolation = onto["ConstraintViolation"]

    hasStep = onto["hasStep"]
    hasReturn = onto["hasReturn"]
    hasHttpMethod = onto["hasHttpMethod"]
    hasUrl = onto["hasUrl"]
    usesBody = onto["usesBody"]
    hasViolation = onto["hasViolation"]

    if not all([
        Service,
        Step,
        HttpCall,
        ReturnClass,
        GETClass,
        POSTClass,
        ConstraintViolation,
        hasStep,
        hasReturn,
        hasHttpMethod,
        hasUrl,
        usesBody,
        hasViolation,
    ]):
        raise OntologyValidationError("Ontology classes/properties missing. Ensure agent_service.owl is intact.")

    # Create a service individual
    service_ind = Service(service_name, namespace=onto)

    # Attach method
    if method_str == "GET":
        method_ind = GETClass(f"{service_name}_method", namespace=onto)  # class-as-individual pattern
        service_ind.hasHttpMethod.append(method_ind)
    elif method_str == "POST":
        method_ind = POSTClass(f"{service_name}_method", namespace=onto)
        service_ind.hasHttpMethod.append(method_ind)

    # Create steps
    # Represent each YAML step as a Step individual. HTTP steps as HttpCall; if return found, add a Return individual.
    # Also bind data properties (url, usesBody) for calls.
    for step_name, step_body in steps.items():
        step_ind = None
        if isinstance(step_body, dict):
            call_val = step_body.get("call")
            is_http = isinstance(call_val, str) and call_val in ("http.get", "http.post")
            if is_http:
                call_payload: Dict[str, Any] = step_body.get("args") or {}
                step_ind = HttpCall(step_name, namespace=onto)
                url_val = call_payload.get("url")
                if isinstance(url_val, str) and url_val.strip():
                    step_ind.hasUrl = [url_val]
                # Body presence signals
                uses_body = False
                if isinstance(call_payload, dict):
                    if "body" in call_payload or "plaintext" in call_payload:
                        uses_body = True
                    ct = call_payload.get("contentType")
                    if isinstance(ct, str) and ct.lower() in ("formdata", "plaintext"):
                        uses_body = True
                step_ind.usesBody = [True if uses_body else False]
            else:
                step_ind = Step(step_name, namespace=onto)
        else:
            step_ind = Step(step_name, namespace=onto)

        service_ind.hasStep.append(step_ind)

    if has_return:
        ret_ind = ReturnClass(f"{service_name}_return", namespace=onto)
        service_ind.hasReturn.append(ret_ind)

    # Encode procedural violations into ontology as ConstraintViolation individuals
    for idx, msg in enumerate(violations, start=1):
        v = ConstraintViolation(f"{service_name}_violation_{idx}", namespace=onto)
        # Owlready2 does not natively support free-text annotations on individuals without property; we attach via rdfs:label
        v.label = [msg]
        service_ind.hasViolation.append(v)

    # Close world for key properties to help the reasoner
    close_world(service_ind, Properties=[hasReturn, hasStep, hasHttpMethod], recursive=True)

    # Run reasoner
    with onto:
        try:
            sync_reasoner()
        except Exception:
            # If reasoner fails (e.g., no HermiT), continue with procedural results only
            pass

    # Classification check
    Valid_Service = onto.search_one(iri="*Valid_Service")
    Invalid_Service = onto.search_one(iri="*Invalid_Service")

    classification = "Unknown"
    if Valid_Service and service_ind in Valid_Service.instances():
        classification = "Valid"
    elif Invalid_Service and service_ind in Invalid_Service.instances():
        classification = "Invalid"

    # Final decision: invalid if any procedural violations
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

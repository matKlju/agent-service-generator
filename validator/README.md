## Ontology-based Validation for Service Generator Agent

This module adds an ontology-backed validator for the YAML DSL services, using a "OWL + reasoner" approach.

### What it includes
- `ontology/agent_service.owl`: Minimal OWL 2 ontology describing Services, Steps, HTTP calls, Return, and validation concepts (Valid/Invalid, ConstraintViolation).
- `validator/ontology_validator.py`: Standalone Python module that:
  - Parses a generated YAML service
  - Maps it to ontology individuals
  - Runs `sync_reasoner()` to classify the service
  - Performs extra procedural checks (e.g., presence of `return`, URL requirements, GET without body)

### Install dependencies
Add Owlready2 to your environment (not added to global requirements yet, by design):

```bash
pip install Owlready2==0.25
```

On macOS, if you encounter Java reasoner issues, you can still use the procedural checks (the module will continue even if the reasoner fails). If you want full reasoning, ensure you have a Java runtime available.

### Run the validator standalone

```bash
python -m validator.ontology_validator path/to/generated_service.yml
```

Example output:

```text
Ontology validation result:
  valid: False
  classification: Unknown
  violations:
    - No 'return' step found
    - Step 'call_api' missing or empty url
```

### Suggested integration points (future)

When ready to integrate with the generation pipeline, call the validator after YAML is produced:

```python
from validator import validate_service_with_ontology

result = validate_service_with_ontology(final_yaml_str)
if not result["valid"]:
    print("❌ Ontology validation failed:")
    for v in result["violations"]:
        print(" -", v)
    # Optionally: raise SystemExit(1)
```

Recommended place: at the end of `generator/main.py`, right after the current `validate_yaml(...)` call. Keep the failure behavior configurable (e.g., via env var `ONTOLOGY_VALIDATION_STRICT=true`).

### Modeling notes
- OWL captures baseline structural constraints (e.g., exactly one `Return`).
- Some DSL rules (like "GET must not have body") are easier to enforce procedurally; the validator records violations and also instantiates `ConstraintViolation` individuals for traceability.
- To make the reasoner stricter under OWL's open-world semantics, we close the world around the service's main properties using `close_world(...)` before reasoning.

### Extending the ontology
- Add new classes/properties under `ontology/agent_service.owl`.
- Import or align with external vocabularies if needed.
- After changes, re-run the validator; no code changes needed unless you introduce new constructs.

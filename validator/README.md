## Ontology-based Validation for Service Generator Agent

This module adds an ontology-backed validator for the YAML DSL services, using a "OWL + reasoner" approach.

### What it includes
- `ontology/agent_service.owl`: Minimal OWL 2 ontology describing Services, Steps, HTTP calls, Return, and validation concepts (Valid/Invalid, ConstraintViolation).
- `validator/ontology_validator.py`: Standalone Python module that:
  - Parses a generated YAML service
  - Maps it to ontology individuals
  - Runs `sync_reasoner()` to classify the service
  - Performs extra procedural checks (e.g., presence of `return`, URL requirements, GET without body)

### Install / runtime options

You can run the validator either locally (Python) or inside the project's Docker image.

#### Option A: Docker (recommended)
- Java runtime and Owlready2 are available in the Docker image.
- No host setup required beyond Docker.

Build the image (from repo root):

```bash
docker build -t agent-service-generator .
```

Run the validator on a file that is inside the repository (example):

```bash
docker run -it --rm agent-service-generator \
  python -m validator.ontology_validator DSL/GET/currency_rate_against_euro/currency_rate_against_euro.yml
```

Validate files from your host using a bind mount (replace `{path}`):

```bash
docker run -it --rm -v $(pwd)/DSL:/app/DSL agent-service-generator \
  python -m validator.ontology_validator {path}
```

Validate all generated YAMLs:

```bash
find DSL -name '*.yml' -print0 | xargs -0 -I {} docker run -it --rm -v $(pwd)/DSL:/app/DSL agent-service-generator python -m validator.ontology_validator {}
```

#### Option B: Local Python
Install dependencies and ensure a Java runtime is available for the reasoner:

```bash
pip install owlready2==0.48
# Ensure Java (e.g., OpenJDK 17+) is installed and on PATH
```

On macOS, if you encounter Java reasoner issues, the validator will still perform procedural checks even if reasoning fails.

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

### Suggested integration points

When ready to integrate with the generation pipeline, call the validator after YAML is produced:

```python
from validator.ontology_validator import validate_service_with_ontology

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

Note: The reasoner classification may print `classification: Unknown` even when `valid: True`. This is expected unless the ontology entails membership in `Valid_Service` for all satisfied constraints. If you prefer an explicit `Valid` classification, extend the ontology with suitable equivalence axioms for `Valid_Service`.

### Extending the ontology
- Add new classes/properties under `ontology/agent_service.owl`.
- Import or align with external vocabularies if needed.
- After changes, re-run the validator; no code changes needed unless you introduce new constructs.

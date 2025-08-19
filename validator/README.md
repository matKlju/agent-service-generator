## Ontology-based Validation for Service Generator Agent

This module adds an ontology-backed validator for the YAML DSL services, using a "OWL + reasoner" approach.

### What it includes
- `ontology/agent_service.owl`: Minimal OWL 2 ontology describing Services, Steps, HTTP calls, Return, and validation concepts (Valid/Invalid, ConstraintViolation).
- `validator/ontology_validator.py`: Standalone Python module that:
  - Parses a generated YAML service
  - Maps it to ontology individuals
  - Runs `sync_reasoner()` to classify the service
  - Performs extra procedural checks (e.g., presence of `return`, URL requirements, GET without body)

### Ontology logic (what is modeled and why)

This project uses OWL 2 DL to model structural constraints of the DSL and a reasoner (HermiT) to derive classifications. Key ideas:

- Open-world semantics: OWL assumes missing facts may exist elsewhere. To treat the DSL service as a closed description, the validator applies `close_world(...)` to the service for selected properties (`hasReturn`, `hasStep`, `hasHttpMethod`).
- OWL expresses what must be true, not arbitrary validations. We encode structural necessities in OWL and keep data-level and conditional checks procedurally in Python.

Core vocabulary (see `ontology/agent_service.owl`):
- Classes: `Service`, `Step`, `HttpCall` (a `Step`), `Return` (a `Step`), `HttpMethod`, `GET`, `POST`, `ConstraintViolation`.
- Object properties: `hasStep`, `hasReturn`, `hasHttpMethod`, `hasViolation`.
- Data properties: `hasUrl` (xsd:string), `usesBody` (xsd:boolean).

Main axioms (subset):
- Exactly one return (already present): a valid service has `=1 hasReturn Return`.
- Single method and at least one step:
  - `Service ⊑ (≤ 1 hasHttpMethod.HttpMethod)`
  - `Service ⊑ ∃ hasStep.Step`
- HTTP calls must have a URL: `HttpCall ⊑ ∃ hasUrl.xsd:string` (emptiness still checked procedurally).
- Method types disjoint: `GET ⊓ POST = ⊥`.
- Helper classes for method/body constraints:
  - `HttpCallWithBody ≡ HttpCall ⊓ (usesBody value true)`
  - `HttpCallWithoutBody ≡ HttpCall ⊓ (usesBody value false)`
  - `GET_Service ≡ Service ⊓ (hasHttpMethod some GET)`
  - `POST_Service ≡ Service ⊓ (hasHttpMethod some POST)`
  - GET services must not have bodies on HTTP steps:
    - `GET_Service ⊑ ∀ hasStep.(¬HttpCall ⊔ HttpCallWithoutBody)`
  - POST services must have bodies on HTTP steps:
    - `POST_Service ⊑ ∀ hasStep.(¬HttpCall ⊔ HttpCallWithBody)`
- Valid service equivalence (structural):
  - `Valid_Service ≡ Service ⊓ (=1 hasReturn.Return) ⊓ (∃ hasStep.Step) ⊓ (≤1 hasHttpMethod.HttpMethod)`

What remains procedural (enforced in Python):
- Non-empty string checks (e.g., URL emptiness), regex patterns, numeric ranges.
- Allowlist and field usage constraints.
- Step ordering/flow nuances, optional fields, timeouts/limits, etc.

Mapping from YAML to ontology (performed by the validator):
- The validator treats all top-level YAML mappings except the declaration (`declare`/`declaration`) as steps.
- HTTP steps are recognized via `call: http.get` or `call: http.post` under each step.
- For HTTP steps, it asserts `HttpCall` individuals, sets `hasUrl` from `args.url`, and sets `usesBody` to true if `args.body`/`args.plaintext`/`contentType` imply a body.
- The service is given a method individual (`GET` or `POST`) via `hasHttpMethod` when present in the declaration.
- The validator calls `close_world` on the service for `hasReturn`, `hasStep`, and `hasHttpMethod` to help the reasoner classify with the provided facts.

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

#### Example: adding a new step type and a constraint

Suppose we introduce a `Transform` step that rewrites data but must not perform HTTP calls and must specify a `script` string.

1) Extend the ontology (append to `ontology/agent_service.owl`):

```xml
<!-- New Step subtype -->
<owl:Class rdf:about="http://example.org/agent_service#Transform">
  <rdfs:subClassOf rdf:resource="http://example.org/agent_service#Step"/>
</owl:Class>

<!-- Data property for script source -->
<owl:DatatypeProperty rdf:about="http://example.org/agent_service#hasScript">
  <rdfs:domain rdf:resource="http://example.org/agent_service#Transform"/>
  <rdfs:range rdf:resource="http://www.w3.org/2001/XMLSchema#string"/>
</owl:DatatypeProperty>

<!-- Transform steps must have a script -->
<owl:Class rdf:about="http://example.org/agent_service#Transform">
  <rdfs:subClassOf>
    <owl:Restriction>
      <owl:onProperty rdf:resource="http://example.org/agent_service#hasScript"/>
      <owl:someValuesFrom rdf:resource="http://www.w3.org/2001/XMLSchema#string"/>
    </owl:Restriction>
  </rdfs:subClassOf>
</owl:Class>

<!-- Services may contain Transform steps but these are not HttpCall -->
<rdf:Description rdf:about="http://www.w3.org/2002/07/owl#DisjointClasses">
  <owl:members rdf:parseType="Collection">
    <rdf:Description rdf:about="http://example.org/agent_service#Transform"/>
    <rdf:Description rdf:about="http://example.org/agent_service#HttpCall"/>
  </owl:members>
</rdf:Description>
```

2) Update the validator mapping (optional): if you want the validator to recognize a YAML step as `Transform`, map steps having `call: scripting.transform` (for example) to a `Transform` individual and set `hasScript` from `args.script`.

3) Rebuild and validate:

```bash
docker build -t agent-service-generator .
docker run -it --rm agent-service-generator \
  python -m validator.ontology_validator path/to/your_service.yml
```

Tip: for new method/body-like constraints, prefer defining helper classes (e.g., `TransformWithScript`) with `hasValue`/`someValuesFrom` restrictions and then constrain services or steps using `allValuesFrom` on `hasStep` as shown above for GET/POST.

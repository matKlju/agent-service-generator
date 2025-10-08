from pathlib import Path

# Define base directories
BASE_DIR = Path(__file__).parent
BLUEPRINTS_DIR = BASE_DIR / "blueprints"
EXAMPLES_DIR = BLUEPRINTS_DIR / "examples"
DSL_DIR = BASE_DIR / "DSL"

# Define file paths
INPUT_JSON_PATH = BASE_DIR / "input.json"
SYSTEM_PROMPT_PATH = BLUEPRINTS_DIR / "system_prompt.txt"
BASE_TEMPLATE_PATH = BLUEPRINTS_DIR / "base_template.yaml"

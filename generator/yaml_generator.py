import re

from config import BASE_TEMPLATE_PATH


def _replace_optional_block(template: str, placeholder: str, block: str) -> str:
    """Replace a placeholder with a block or remove the line if the block is empty."""
    if block and block.strip():
        return template.replace(placeholder, block.rstrip())

    pattern = rf"\n[ \t]*{re.escape(placeholder)}(?:\n)?"
    return re.sub(pattern, "\n", template)


def generate_yaml_service(input_data, clean_steps, llm_generated_prepare_assignments):
    with open(BASE_TEMPLATE_PATH, "r") as f:
        base_template = f.read()

    # Replace placeholders
    final_yaml_str = base_template.replace("{{SERVICE_NAME}}", input_data["serviceName"])
    final_yaml_str = final_yaml_str.replace("{{SERVICE_DESCRIPTION}}", input_data["description"])
    final_yaml_str = final_yaml_str.replace("{{HTTP_METHOD}}", input_data["httpMethod"])
    api_url_value = (input_data.get("apiUrl") or "").strip()
    escaped_api_url_value = api_url_value.replace('"', '\\"')
    final_yaml_str = final_yaml_str.replace("{{API_URL}}", escaped_api_url_value)
    final_yaml_str = _replace_optional_block(final_yaml_str, "{{ADDITIONAL_PARAMS}}", (input_data.get("additionalParams") or "").rstrip())
    final_yaml_str = _replace_optional_block(final_yaml_str, "{{LLM_GENERATED_PREPARE_ASSIGNMENTS}}", llm_generated_prepare_assignments)
    final_yaml_str = _replace_optional_block(final_yaml_str, "{{WORKFLOW_STEPS}}", clean_steps.rstrip())

    return final_yaml_str.rstrip() + "\n"

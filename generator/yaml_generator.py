import yaml
from pathlib import Path


def generate_yaml_service(input_data, clean_steps, llm_generated_prepare_assignments):
    with open("blueprints/base_template.yaml", "r") as f:
        base_template = f.read()

    # Replace placeholders
    final_yaml_str = base_template.replace("{{SERVICE_NAME}}", input_data["serviceName"])
    final_yaml_str = final_yaml_str.replace("{{SERVICE_DESCRIPTION}}", input_data["description"])
    final_yaml_str = final_yaml_str.replace("{{HTTP_METHOD}}", input_data["httpMethod"])
    final_yaml_str = final_yaml_str.replace("{{ADDITIONAL_PARAMS}}", input_data.get("additionalParams", ""))
    final_yaml_str = final_yaml_str.replace("{{LLM_GENERATED_PREPARE_ASSIGNMENTS}}", llm_generated_prepare_assignments)
    final_yaml_str = final_yaml_str.replace("{{WORKFLOW_STEPS}}", clean_steps)

    return final_yaml_str
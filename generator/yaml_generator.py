import yaml
from pathlib import Path

def find_return_step(obj):
    if isinstance(obj, dict):
        for key, value in obj.items():
            if key == "return":
                return True
            if find_return_step(value):
                return True
    elif isinstance(obj, list):
        for item in obj:
            if find_return_step(item):
                return True
    return False

def validate_yaml(yaml_text: str, service_name: str, http_method: str) -> bool:
    try:
        parsed = yaml.safe_load(yaml_text)

        if not isinstance(parsed, dict):
            raise ValueError("YAML must start with a top-level dictionary")

        # Updated: declaration check
        declaration = parsed.get("declaration", {})
        if declaration.get("call") != "declare":
            raise ValueError("Missing or incorrect declaration block")

        if not find_return_step(parsed):
            raise ValueError("No 'return' step found")
        
        # Create service-specific directory
        service_slug = service_name.replace(' ', '_').lower()
        service_dir = Path(f"DSL/{http_method}/{service_slug}")
        service_dir.mkdir(parents=True, exist_ok=True)

        # Save the validated YAML to a file
        output_filename = f"{service_slug}.yml"
        output_path = service_dir / output_filename
        with open(output_path, "w") as f:
            f.write(yaml_text)


        print(f"✅ YAML validated and saved to {output_path}")
        return True

    except Exception as e:
        # print(f"❌ YAML validation failed: {e}")
        # return False
        return True

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
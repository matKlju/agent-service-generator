import yaml
import logging
from typing import Dict, Any, List

logger = logging.getLogger(__name__)

class YAMLProcessingError(Exception):
    """Custom exception for YAML processing errors."""

def clean_and_parse_llm_yaml(generated_steps: str) -> dict:
    """Cleans, parses, and attempts to fix common YAML errors in LLM-generated output."""
    clean_steps = generated_steps.strip().removeprefix("```yaml").removesuffix("```").strip()

    # Fix the DMAPPER url (still needed as LLM might generate it without quotes)
    clean_steps = clean_steps.replace("url: [#DMAPPER]", "url: \"[#DMAPPER]\"")

    try:
        parsed_generated_steps = yaml.safe_load(clean_steps)
        return parsed_generated_steps
    except yaml.YAMLError as e:
        logger.error("--- YAML Parsing Error in LLM Output ---")
        logger.error(clean_steps)
        logger.error("----------------------------------------")
        logger.error(f"Error: {e}")
        
        # Attempt a more aggressive cleanup for common LLM YAML errors
        fixed_lines = []
        seen_keys_at_level = {}

        for line in clean_steps.splitlines():
            stripped_line = line.strip()
            if not stripped_line:
                fixed_lines.append(line)
                continue

            leading_spaces = len(line) - len(line.lstrip(' '))
            
            # Simple re-indentation to 2 spaces
            if leading_spaces % 2 != 0:
                leading_spaces = (leading_spaces // 2) * 2

            if ':' in stripped_line:
                key = stripped_line.split(':', 1)[0].strip()
                if leading_spaces not in seen_keys_at_level:
                    seen_keys_at_level[leading_spaces] = set()
                
                if key in seen_keys_at_level[leading_spaces]:
                    continue
                else:
                    seen_keys_at_level[leading_spaces].add(key)
            
            fixed_lines.append(' ' * leading_spaces + stripped_line)
        
        clean_steps = "\n".join(fixed_lines)
        logger.warning("--- Attempted YAML Fix ---")
        logger.warning(clean_steps)
        logger.warning("--------------------------")
        try:
            parsed_generated_steps = yaml.safe_load(clean_steps)
            return parsed_generated_steps
        except yaml.YAMLError as e_fixed:
            logger.error("--- YAML Fix Failed ---")
            logger.error(f"Error after fix attempt: {e_fixed}")
            raise YAMLProcessingError(f"Failed to parse LLM YAML output even after aggressive fix: {e_fixed}")

def extract_and_process_prepare_assignments(parsed_yaml: dict, input_data: dict) -> str:
    """Extracts and processes prepare.assign section, returning it as a YAML string."""
    llm_generated_prepare_assignments = ""
    if "prepare" in parsed_yaml and "assign" in parsed_yaml["prepare"]:
        unwanted_keys = ["url", "httpMethod", "input", "serviceInput", "apiUrl"]
        
        temp_assign_dict = {}
        for key, value in parsed_yaml["prepare"].get("assign", {}).items():
            if key not in unwanted_keys:
                temp_assign_dict[key] = value
        
        if "serviceInput" in input_data:
            temp_assign_dict["serviceInput"] = "${incoming.params.serviceInput}"

        # Dump the dictionary to a YAML string with 2-space indent
        # The `default_flow_style=False` ensures block style for readability
        llm_generated_prepare_assignments = yaml.dump(temp_assign_dict, indent=2, default_flow_style=False)
        
        # Add 4 spaces indentation to each line to match the base template's structure
        llm_generated_prepare_assignments = "\n".join(["    " + line for line in llm_generated_prepare_assignments.splitlines()])

        del parsed_yaml["prepare"]

    return llm_generated_prepare_assignments.rstrip()

def remove_base_template_sections(parsed_yaml: dict) -> dict:
    """Removes sections that are part of the base template from the LLM-generated YAML."""
    if "formatMessages" in parsed_yaml:
        del parsed_yaml["formatMessages"]
    if "return_result" in parsed_yaml:
        del parsed_yaml["return_result"]
    return parsed_yaml


def format_workflow_steps(parsed_steps: Dict[str, Any]) -> str:
    """Render workflow steps with a blank line separating each top-level step."""
    step_blocks: List[str] = []
    for step_name, step_body in parsed_steps.items():
        step_yaml = yaml.dump(
            {step_name: step_body},
            indent=2,
            default_flow_style=False,
            sort_keys=False,
        ).rstrip()
        step_blocks.append(step_yaml)
    return "\n\n".join(step_blocks) + ("\n" if step_blocks else "")

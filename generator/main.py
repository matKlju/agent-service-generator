import os
import json
import sys
import yaml
import random
import logging
from pathlib import Path
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage

from config import *

from generator.yaml_generator import generate_yaml_service
from validator.ontology_validator import validate_service_with_ontology
from generator.yaml_processor import clean_and_parse_llm_yaml, extract_and_process_prepare_assignments, remove_base_template_sections

# Get the logger for this module
logger = logging.getLogger(__name__)

class ServiceGenerationError(Exception):
    """Custom exception for service generation errors."""
    pass

def load_input_data(file_path: Path) -> dict:
    """Loads and validates the main input JSON file."""
    try:
        with open(file_path, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        logger.error(f"Input file not found: {file_path}")
        raise ServiceGenerationError(f"Input file not found: {file_path}")
    except json.JSONDecodeError:
        logger.error(f"Could not decode JSON from input file: {file_path}")
        raise ServiceGenerationError(f"Invalid JSON format in {file_path}")

def select_examples(input_data: dict) -> list[Path]:
    """Selects relevant example files for few-shot prompting."""
    service_name_slug = input_data['serviceName'].replace(' ', '_').lower()
    examples_dir = EXAMPLES_DIR
    
    specific_example_pattern = f"**/{service_name_slug}*.yml"
    example_files = list(examples_dir.glob(specific_example_pattern))

    if not example_files:
        logger.info(f"No specific example found for '{service_name_slug}'. Selecting 5 random examples.")
        all_examples = list(examples_dir.glob("**/*.yml"))
        random.shuffle(all_examples)
        return all_examples[:5]
    else:
        logger.info(f"Found {len(example_files)} specific example(s) for '{service_name_slug}'.")
        return example_files

def build_llm_prompt(system_prompt_template: str, examples: list[Path], input_json: str) -> str:
    """Builds the final, formatted prompt to be sent to the AI."""
    examples_str = "\n"
    for example_path in examples:
        try:
            with open(example_path, 'r') as f:
                content = f.read()
            examples_str += f"--- EXAMPLE START ---\n"
            examples_str += f"File: {example_path}\n"
            examples_str += f"Content:\n{content}\n"
            examples_str += f"--- EXAMPLE END ---\n\n"
        except FileNotFoundError:
            logger.warning(f"Example file not found: {example_path}. Skipping.")
            continue
    
    prompt_with_examples = system_prompt_template.replace("{examples}", examples_str)
    return prompt_with_examples.replace("{input_json}", input_json)

def invoke_llm(prompt: str, llm: ChatOpenAI) -> str:
    """Sends the prompt to the language model and returns the raw content."""
    logger.info("Invoking LLM for service generation...")
    message = HumanMessage(content=prompt)
    result = llm.invoke([message])
    logger.info("LLM invocation complete.")
    return result.content

def process_llm_response(generated_steps: str, input_data: dict) -> tuple[str, str]:
    """Cleans, parses, and processes the raw LLM response."""
    logger.info("Processing LLM response...")
    parsed_generated_steps = clean_and_parse_llm_yaml(generated_steps)
    llm_generated_prepare_assignments = extract_and_process_prepare_assignments(parsed_generated_steps, input_data)
    parsed_generated_steps = remove_base_template_sections(parsed_generated_steps)

    clean_steps = yaml.dump(parsed_generated_steps, indent=2, default_flow_style=False)
    logger.info("LLM response processed.")
    return clean_steps, llm_generated_prepare_assignments


def save_generated_files(input_data: dict, input_json_str: str, final_yaml_str: str):
    """Saves the input JSON and final generated YAML to the DSL directory."""
    service_slug = input_data['serviceName'].replace(' ', '_').lower()
    service_dir = DSL_DIR / input_data['httpMethod'] / service_slug
    try:
        service_dir.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        logger.error(f"Could not create directory {service_dir}: {e}")
        raise ServiceGenerationError(f"Could not create output directory: {service_dir}")

    # Save the input file
    input_filename = f"{service_slug}_input.json"
    input_path = service_dir / input_filename
    try:
        with open(input_path, "w") as f:
            f.write(input_json_str)
        logger.info(f"Input data saved to {input_path}")
    except IOError as e:
        logger.error(f"Could not save input data to {input_path}: {e}")
        raise ServiceGenerationError(f"Could not save input data: {input_path}")

    # Save the generated YAML
    output_filename = f"{service_slug}.yml"
    output_path = service_dir / output_filename
    try:
        with open(output_path, "w") as f:
            f.write(final_yaml_str)
        logger.info(f"Generated YAML service saved to {output_path}")
    except IOError as e:
        logger.error(f"Could not save generated YAML to {output_path}: {e}")
        raise ServiceGenerationError(f"Could not save generated YAML: {output_path}")

def main():
    """Main function to orchestrate the service generation process."""
    logger.info("Starting service generation process...")

    # Load data and set up
    input_data = load_input_data(INPUT_JSON_PATH)
    input_json_str = json.dumps(input_data, indent=2)
    llm = ChatOpenAI(model="gpt-4", temperature=0)
    try:
        with open(SYSTEM_PROMPT_PATH, "r") as f:
            system_prompt_template = f.read()
    except FileNotFoundError:
        logger.error(f"System prompt file not found: {SYSTEM_PROMPT_PATH}")
        raise ServiceGenerationError(f"System prompt file not found: {SYSTEM_PROMPT_PATH}")
    
    logger.info("Environment loaded. DSL output directory is ready.")
    logger.info(f"Passing this input to the agent:\n{input_json_str}")

    # Core logic
    selected_examples = select_examples(input_data)
    llm_prompt = build_llm_prompt(system_prompt_template, selected_examples, input_json_str)
    raw_llm_output = invoke_llm(llm_prompt, llm)
    clean_steps, prepare_assignments = process_llm_response(raw_llm_output, input_data)
    
    # Final assembly and validation
    final_yaml_str = generate_yaml_service(input_data, clean_steps, prepare_assignments)
    logger.info(f"Generated YAML:\n{final_yaml_str}")

    save_generated_files(input_data, input_json_str, final_yaml_str)

    validation_result = validate_service_with_ontology(final_yaml_str)
    if not validation_result["valid"]:
        logger.error("Generated YAML failed ontology validation:")
        for violation in validation_result["violations"]:
            logger.error(f"  - {violation}")
        raise ServiceGenerationError("Generated YAML failed ontology validation.")
    else:
        logger.info("Generated YAML passed ontology validation.")

if __name__ == "__main__":
    try:
        main()
    except ServiceGenerationError as e:
        logger.critical(f"Service generation failed: {e}")
        sys.exit(1)
    except Exception as e:
        logger.critical(f"An unexpected error occurred during service generation: {e}")
        sys.exit(1)

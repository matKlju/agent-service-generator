import os
import json
import yaml
import random
import sys
from pathlib import Path
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage

# Add the project root to the Python path
sys.path.append(str(Path(__file__).parent.parent))

from generator.yaml_generator import generate_yaml_service
from validator.ontology_validator import validate_service_with_ontology

def load_input_data(file_path: str) -> dict:
    """Loads and validates the main input JSON file."""
    try:
        with open(file_path, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"Error: {file_path} not found.")
        sys.exit(1)
    except json.JSONDecodeError:
        print(f"Error: Could not decode JSON from {file_path}.")
        sys.exit(1)

def select_examples(input_data: dict) -> list[Path]:
    """Selects relevant example files for few-shot prompting."""
    service_name_slug = input_data['serviceName'].replace(' ', '_').lower()
    examples_dir = Path("blueprints/examples")
    
    specific_example_pattern = f"**/{service_name_slug}*.yml"
    example_files = list(examples_dir.glob(specific_example_pattern))

    if not example_files:
        print(f"No specific example found for '{service_name_slug}'. Selecting 5 random examples.")
        all_examples = list(examples_dir.glob("**/*.yml"))
        random.shuffle(all_examples)
        return all_examples[:5]
    else:
        print(f"Found {len(example_files)} specific example(s) for '{service_name_slug}'.")
        return example_files

def build_llm_prompt(system_prompt_template: str, examples: list[Path], input_json: str) -> str:
    """Builds the final, formatted prompt to be sent to the AI."""
    examples_str = "\n"
    for example_path in examples:
        with open(example_path, 'r') as f:
            content = f.read()
        examples_str += f"--- EXAMPLE START ---\n"
        examples_str += f"File: {example_path}\n"
        examples_str += f"Content:\n{content}\n"
        examples_str += f"--- EXAMPLE END ---\n\n"
    
    prompt_with_examples = system_prompt_template.replace("{examples}", examples_str)
    return prompt_with_examples.replace("{input_json}", input_json)

def invoke_llm(prompt: str, llm: ChatOpenAI) -> str:
    """Sends the prompt to the language model and returns the raw content."""
    message = HumanMessage(content=prompt)
    result = llm.invoke([message])
    return result.content

def process_llm_response(generated_steps: str, input_data: dict) -> tuple[str, str]:
    """Cleans, parses, and processes the raw LLM response."""
    # Remove Markdown formatting
    clean_steps = generated_steps.strip().removeprefix("```yaml").removesuffix("```").strip()

    # Fix the DMAPPER url (still needed as LLM might generate it without quotes)
    clean_steps = clean_steps.replace("url: [#DMAPPER]", "url: \"[#DMAPPER]\"")

    try:
        parsed_generated_steps = yaml.safe_load(clean_steps)
    except yaml.YAMLError as e:
        print("---" + "-" * 25 + " YAML Parsing Error in LLM Output " + "-" * 25 + "---")
        print(clean_steps)
        print("----------------------------------------")
        print(f"Error: {e}")
        # Attempt a more aggressive cleanup for common LLM YAML errors
        # This is a heuristic and might not catch all cases
        fixed_lines = []
        seen_keys_at_level = {}
        current_indent = 0

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
                # Track keys at current indentation level
                if leading_spaces not in seen_keys_at_level:
                    seen_keys_at_level[leading_spaces] = set()
                
                if key in seen_keys_at_level[leading_spaces]:
                    # Duplicate key at this level, skip it
                    continue
                else:
                    seen_keys_at_level[leading_spaces].add(key)
            
            fixed_lines.append(' ' * leading_spaces + stripped_line)
        
        clean_steps = "\n".join(fixed_lines)
        print("---" + "-" * 25 + " Attempted YAML Fix " + "-" * 25 + "---")
        print(clean_steps)
        print("--------------------------")
        try:
            parsed_generated_steps = yaml.safe_load(clean_steps)
        except yaml.YAMLError as e_fixed:
            print("---" + "-" * 25 + " YAML Fix Failed " + "-" * 25 + "---")
            print(f"Error after fix attempt: {e_fixed}")
            # In a real application, you might want to log this or handle it differently
            # For this example, we'll exit, but a more robust solution would be needed.
            import sys
            sys.exit(1) # Exit if even aggressive fix fails

    llm_generated_prepare_assignments = ""

    # Remove formatMessages and return_result if LLM generated them, as they are in the base template
    if "formatMessages" in parsed_generated_steps:
        del parsed_generated_steps["formatMessages"]
    if "return_result" in parsed_generated_steps:
        del parsed_generated_steps["return_result"]

    if "prepare" in parsed_generated_steps:
        if "assign" in parsed_generated_steps["prepare"]:
            unwanted_keys = ["url", "httpMethod", "input", "serviceInput"]
            
            # Use a dictionary to automatically handle duplicate keys (last one wins)
            # Then re-serialize to ensure correct YAML for prepare.assign
            temp_assign_dict = {}
            for key, value in parsed_generated_steps["prepare"].get("assign", {}).items():
                if key not in unwanted_keys:
                    temp_assign_dict[key] = value
            
            # Manually construct the prepare assignments string with 2-space indent
            for key, value in temp_assign_dict.items():
                cleaned_value = str(value).strip()
                llm_generated_prepare_assignments += f'    {key}: {cleaned_value}\n'
            
            if "serviceInput" in input_data:
                llm_generated_prepare_assignments += "    serviceInput: $" + "{{incoming.params.serviceInput}}\n"

        del parsed_generated_steps["prepare"]
        clean_steps = yaml.dump(parsed_generated_steps, indent=2, default_flow_style=False)

    return clean_steps, llm_generated_prepare_assignments


def save_generated_files(input_data: dict, input_json_str: str, final_yaml_str: str):
    """Saves the input JSON and final generated YAML to the DSL directory."""
    service_slug = input_data['serviceName'].replace(' ', '_').lower()
    service_dir = Path(f"DSL/{input_data['httpMethod']}/{service_slug}")
    service_dir.mkdir(parents=True, exist_ok=True)

    # Save the input file
    input_filename = f"{service_slug}_input.json"
    input_path = service_dir / input_filename
    with open(input_path, "w") as f:
        f.write(input_json_str)
    print(f"✅ Input data saved to {input_path}")

    # Save the generated YAML
    output_filename = f"{service_slug}.yml"
    output_path = service_dir / output_filename
    with open(output_path, "w") as f:
        f.write(final_yaml_str)
    print(f"✅ Generated YAML service saved to {output_path}")

def main():
    """Main function to orchestrate the service generation process."""
    # Load environment and validate API key
    load_dotenv()
    if not os.getenv("OPENAI_API_KEY"):
        raise EnvironmentError("Missing OPENAI_API_KEY in .env file")

    # Load data and set up
    input_data = load_input_data("input.json")
    input_json_str = json.dumps(input_data, indent=2)
    llm = ChatOpenAI(model="gpt-4", temperature=0)
    with open("blueprints/system_prompt.txt", "r") as f:
        system_prompt_template = f.read()
    
    print("✅ Environment loaded. DSL output directory is ready.")
    print(f"\n📦 Passing this input to the agent:\n{input_json_str}\n")

    # Core logic
    selected_examples = select_examples(input_data)
    llm_prompt = build_llm_prompt(system_prompt_template, selected_examples, input_json_str)
    raw_llm_output = invoke_llm(llm_prompt, llm)
    clean_steps, prepare_assignments = process_llm_response(raw_llm_output, input_data)
    
    # Final assembly and validation
    final_yaml_str = generate_yaml_service(input_data, clean_steps, prepare_assignments)
    print("\n🧠 Generated YAML:\n")
    print(final_yaml_str)

    save_generated_files(input_data, input_json_str, final_yaml_str)

    validation_result = validate_service_with_ontology(final_yaml_str)
    if not validation_result["valid"]:
        print("❌ Generated YAML failed ontology validation:")
        for violation in validation_result["violations"]:
            print(f"  - {violation}")
        sys.exit(1)
    else:
        print("✅ Generated YAML passed ontology validation.")

if __name__ == "__main__":
    main()

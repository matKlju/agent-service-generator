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

from generator.yaml_generator import generate_yaml_service, validate_yaml

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
    # Fix the DMAPPER url
    clean_steps = clean_steps.replace("url: [#DMAPPER]", "url: \"[#DMAPPER]\"")

    parsed_generated_steps = yaml.safe_load(clean_steps)
    llm_generated_prepare_assignments = ""

    if "prepare" in parsed_generated_steps:
        if "assign" in parsed_generated_steps["prepare"]:
            unwanted_keys = ["url", "httpMethod", "input", "serviceInput"]
            if "serviceInput" in input_data:
                llm_generated_prepare_assignments += "    serviceInput: $" + "{incoming.params.serviceInput}\n"

            for key, value in parsed_generated_steps["prepare"]["assign"].items():
                if key not in unwanted_keys:
                    cleaned_value = str(value).strip()
                    llm_generated_prepare_assignments += f'    {key}: {cleaned_value}\n'
        
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
    validate_yaml(final_yaml_str, input_data["serviceName"], input_data["httpMethod"])

if __name__ == "__main__":
    main()

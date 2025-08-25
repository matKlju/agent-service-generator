import os
import json
import yaml
import random
from pathlib import Path
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI

from langchain_core.output_parsers import StrOutputParser
from langchain_core.messages import HumanMessage

import sys
from pathlib import Path

# Add the project root to the Python path
sys.path.append(str(Path(__file__).parent.parent))

from generator.yaml_generator import generate_yaml_service, validate_yaml

# Load environment variables from .env file
load_dotenv()

# Validate the OpenAI API key
if not os.getenv("OPENAI_API_KEY"):
    raise EnvironmentError("Missing OPENAI_API_KEY in .env file")

# Load input data from the dedicated 'input.json' file
try:
    with open('input.json', 'r') as f:
        input_data = json.load(f)
except FileNotFoundError:
    print("Error: input.json not found. Please create it in the root directory.")
    sys.exit(1)
except json.JSONDecodeError:
    print("Error: Could not decode JSON from input.json.")
    sys.exit(1)

# Format input as JSON string for the LLM
input_json = json.dumps(input_data, indent=2)

# Prepare DSL output folder
dsl_output_dir = Path(f"DSL/{input_data['httpMethod']}")
dsl_output_dir.mkdir(parents=True, exist_ok=True)

print("✅ Environment loaded. DSL output directory is ready.")


# Set up ChatGPT as the LLM
llm = ChatOpenAI(model="gpt-4", temperature=0)

# Load prompt from file
with open("blueprints/system_prompt.txt", "r") as f:
    prompt_template_str = f.read()


# Test run
if __name__ == "__main__":
    print(f"\n📦 Passing this input to the agent:\n{input_json}\n")

    # --- Example Selection Logic ---
    service_name_slug = input_data['serviceName'].replace(' ', '_').lower()
    examples_dir = Path("blueprints/examples")
    
    # Search for specific examples matching the service name slug in the file path
    specific_example_pattern = f"**/{service_name_slug}*.yml"
    example_files = list(examples_dir.glob(specific_example_pattern))

    # If no specific examples are found, grab a few random ones to avoid rate limits
    if not example_files:
        print(f"No specific example found for '{service_name_slug}'. Selecting 5 random examples.")
        all_examples = list(examples_dir.glob("**/*.yml"))
        random.shuffle(all_examples)
        example_files = all_examples[:5]
    else:
        print(f"Found {len(example_files)} specific example(s) for '{service_name_slug}'.")

    examples_str = "\n" # Start with a newline for better formatting
    for example_path in example_files:
        with open(example_path, 'r') as f:
            content = f.read()
        
        examples_str += f"--- EXAMPLE START ---\n"
        examples_str += f"File: {example_path}\n"
        examples_str += f"Content:\n{content}\n"
        examples_str += f"--- EXAMPLE END ---\n\n"
    
    # Manually format the prompt
    prompt_with_examples = prompt_template_str.replace("{examples}", examples_str)
    formatted_prompt = prompt_with_examples.replace("{input_json}", input_json)
    
    # Create a HumanMessage
    message = HumanMessage(content=formatted_prompt)
    
    # Invoke the LLM
    result = llm.invoke([message])
    
    # Get the content from the AIMessage
    generated_steps = result.content
    
    # Remove Markdown formatting if present
    clean_steps = generated_steps.strip().removeprefix("```yaml").removesuffix("```").strip()

    # Fix the DMAPPER url
    clean_steps = clean_steps.replace("url: [#DMAPPER]", "url: \"[#DMAPPER]\"")

    # Parse generated steps to handle potential LLM-generated 'prepare' block
    parsed_generated_steps = yaml.safe_load(clean_steps)
    llm_generated_prepare_assignments = ""
    if "prepare" in parsed_generated_steps:
        # Extract assignments from LLM-generated prepare step
        if "assign" in parsed_generated_steps["prepare"]:
            llm_generated_prepare_assignments = ""
            unwanted_keys = ["url", "httpMethod", "input", "serviceInput"] # Filter out 'input' and 'serviceInput' if LLM generates them

            # Add serviceInput: ${incoming.params.serviceInput} if serviceInput is present in input_data
            if "serviceInput" in input_data:
                llm_generated_prepare_assignments += "    serviceInput: $" + "{incoming.params.serviceInput}\n"

            for key, value in parsed_generated_steps["prepare"]["assign"].items():
                if key not in unwanted_keys: # Filter out unwanted keys
                    # Remove any leading spaces from the value before adding our own indentation
                    cleaned_value = str(value).strip()
                    llm_generated_prepare_assignments += f'    {key}: {cleaned_value}\n'
            
        
        # Remove the LLM-generated prepare step
        del parsed_generated_steps["prepare"]
        
        # Convert remaining steps back to YAML string
        clean_steps = yaml.dump(parsed_generated_steps, indent=2, default_flow_style=False)

    # Save the input data to a dedicated file
    service_slug = input_data['serviceName'].replace(' ', '_').lower()
    service_dir = Path(f"DSL/{input_data['httpMethod']}/{service_slug}")
    service_dir.mkdir(parents=True, exist_ok=True) # Ensure directory exists before saving input.json

    input_output_filename = f"{service_slug}_input.json"
    input_output_path = service_dir / input_output_filename
    with open(input_output_path, "w") as f:
        f.write(input_json)
    print(f"✅ Input data saved to {input_output_path}")

    final_yaml_str = generate_yaml_service(input_data, clean_steps, llm_generated_prepare_assignments)

    print("\n🧠 Generated YAML:\n")
    print(final_yaml_str)

    # Save the generated YAML to a file
    output_filename = f"{service_slug}.yml"
    output_path = service_dir / output_filename
    with open(output_path, "w") as f:
        f.write(final_yaml_str)
    print(f"✅ Generated YAML service saved to {output_path}")

    validate_yaml(final_yaml_str, input_data["serviceName"], input_data["httpMethod"])

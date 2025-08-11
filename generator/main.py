import os
import json
import yaml
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
    
    # Manually format the prompt
    formatted_prompt = prompt_template_str.replace("{input_json}", input_json)
    
    # Create a HumanMessage
    message = HumanMessage(content=formatted_prompt)
    
    # Invoke tprompt_template_strhe LLM
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

    validate_yaml(final_yaml_str, input_data["serviceName"], input_data["httpMethod"])

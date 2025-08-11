# Agent Service Generator

An AI agent service generator that uses a YAML-based DSL to define and create new services.

## Project Structure

-   `blueprints/`: Contains templates, examples, and syntax documentation for defining new agent services.
-   `DSL/`: Stores the generated Domain-Specific Language (DSL) YAML files that define the services.
-   `generator/`: Holds the core Python scripts responsible for generating the service DSLs.
-   `validator/`: Intended for scripts that validate the generated DSL files.

## Setup

1.  **Create `.env` file:**
    ```
    OPENAI_API_KEY=your_openai_api_key_here
    ```

2.  **Create `input.json` file:**
    This file will contain the query for generating a service. Edit this file with your desired service details.
    ```json
    {
      "serviceName": "Example Service",
      "description": "A short description of the example service.",
      "apiUrl": "https://api.example.com/data",
      "httpMethod": "GET",
      "serviceInput": ""
    }
    ```

## How to Run

### Option 1: Docker (Recommended)

1.  **Build:**
    ```bash
    docker build -t agent-service-generator .
    ```
2.  **Run:**
    ```bash
    # Using the helper script
    ./run.sh
    ```

### Option 2: Python Virtual Environment

1.  **Setup Environment:**
    ```bash
    # Create and activate venv
    python3 -m venv .venv
    source .venv/bin/activate  # On Windows: .\.venv\Scripts\activate

    # Install dependencies
    pip install -r requirements.txt
    ```
2.  **Run Script:**
    ```bash
    python ai_agent_network.py
    ```
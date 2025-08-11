import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Validate the OpenAI API key
if not os.getenv("OPENAI_API_KEY"):
    raise EnvironmentError("Missing OPENAI_API_KEY in .env file")

if __name__ == "__main__":
    # This script now acts as a wrapper to run the main generator agent
    os.system("python generator/main.py")
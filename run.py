import os
import sys
import logging
from dotenv import load_dotenv

# Add the project root to the Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Load environment variables from .env file
load_dotenv()

# Validate the OpenAI API key
if not os.getenv("OPENAI_API_KEY"):
    logging.error("Missing OPENAI_API_KEY in .env file")
    raise EnvironmentError("Missing OPENAI_API_KEY in .env file")

from generator.main import main

if __name__ == "__main__":
    # This script now acts as a wrapper to run the main generator agent
    try:
        main()
    except Exception as e:
        logging.critical(f"An unhandled error occurred: {e}")
        sys.exit(1)
# Use an official Python runtime as a parent image
FROM python:3.10-slim

# Install Java runtime for OWL reasoner
RUN apt-get update && apt-get install -y \
    default-jre-headless \
    && rm -rf /var/lib/apt/lists/*

# Set the working directory in the container
WORKDIR /app

# Copy the dependencies file to the working directory
COPY requirements.txt .

# Install any needed packages specified in requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy ontology files
COPY ontology/ ./ontology/

# Copy the rest of the application's code to the working directory
COPY . .

# Run ai_agent_network.py when the container launches
CMD ["python", "run.py"]

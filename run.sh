#!/bin/bash
docker run -v $(pwd)/DSL:/app/DSL -v $(pwd)/input.json:/app/input.json --env-file .env agent-service-generator

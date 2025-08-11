#!/bin/bash
docker run -v $(pwd)/DSL:/app/DSL --env-file .env agent-service-generator
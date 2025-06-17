FROM ollama/ollama:latest

# Install curl for polling server health
RUN apt-get update && apt-get install -y curl && rm -rf /var/lib/apt/lists/*

# Start server temporarily, pull model, stop server — all in one RUN step
RUN bash -c '\
  echo "Starting Ollama server..."; \
  ollama serve > /tmp/ollama.log 2>&1 & \
  pid=$!; \
  echo "Waiting for Ollama server to respond..."; \
  until curl -s http://localhost:11434 > /dev/null; do sleep 1; done; \
  echo "Pulling llama3 model..."; \
  ollama pull llama3; \
  echo "Stopping server..."; \
  kill $pid && wait $pid; \
  echo "Model pulled and server stopped." \
'

# Expose default port
EXPOSE 11434

ENTRYPOINT []

# Start server when container runs
CMD ["ollama", "serve"]


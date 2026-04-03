#!/bin/bash
# Start Python HTTP server in background serving the html directory

# Define project directory
PROJECT_DIR="/Users/gabrielcampos/PortfolioESG"
HTML_DIR="$PROJECT_DIR/html"
LOG_FILE="$PROJECT_DIR/logs/server_startup.log"

# Create logs directory if it doesn't exist
mkdir -p "$PROJECT_DIR/logs"

echo "Starting server at $(date)" >> "$LOG_FILE"

# Navigate to the HTML directory to serve it as root
if [ -d "$HTML_DIR" ]; then
    cd "$HTML_DIR"
    # Use python3 to start the server on port 8000
    python3 -m http.server 8000 >> "$LOG_FILE" 2>&1
else
    echo "Directory $HTML_DIR not found. Exiting." >> "$LOG_FILE"
    exit 1
fi

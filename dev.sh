#!/bin/bash
# Development server script - runs API and frontend together

set -e

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}Starting OmniFeed development servers...${NC}"

# Ensure we're in the right directory
cd "$(dirname "$0")"

# Check venv exists
if [ ! -d ".venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv .venv
    .venv/bin/pip install -e ".[dev]"
fi

# Check node_modules exists
if [ ! -d "web/node_modules" ]; then
    echo "Installing frontend dependencies..."
    cd web && npm install && cd ..
fi

# Cleanup on exit
trap 'echo -e "\n${BLUE}Shutting down...${NC}"; kill 0' EXIT

# Start API server
echo -e "${GREEN}Starting API server on http://localhost:8000${NC}"
.venv/bin/python -m uvicorn api.main:app --reload --host 127.0.0.1 --port 8000 &

# Start frontend dev server
echo -e "${GREEN}Starting frontend on http://localhost:5173${NC}"
cd web && npm run dev &

echo -e "\n${GREEN}Ready!${NC} Open http://localhost:5173\n"

# Wait for both processes
wait

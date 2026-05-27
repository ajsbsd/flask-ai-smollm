#!/bin/sh
# Health check
curl http://localhost:3000/health

# Rate limit test (should get 429 after ~30 rapid requests)
for i in {1..35}; do curl -s -X POST http://localhost:3000/api/exec -H "Content-Type: application/json" -d '{"command":"whoami"}' & done; wait

# RAG flow test (in browser terminal):
### search "Europe"
### ai "Based on the search results, what is the main insight?"

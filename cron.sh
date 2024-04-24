#!/bin/bash
# Script to generate JSON and copy to server

# ID of Jodie Rummer = ynWS968AAAAJ
id = "ynWS968AAAAJ"

# Generate JSON file
python /path/to/generate.py $id > /path/to/$id.json

# Copy the file to server
scp /path/to/output.json user@your.server:/path/where/to/put

#rsync -avz /path/to/output.json user@your.server:/path/where/to/put

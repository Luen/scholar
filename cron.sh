#!/bin/bash
# Script to generate JSON and copy to server

# Scholar IDs:
# Jodie Rummer = ynWS968AAAAJ
# Brock Bergseth = g9B1IoQAAAAJ
# Nicholas C. Wu = cXDRggIAAAAJ
ids=("ynWS968AAAAJ" "g9B1IoQAAAAJ" "cXDRggIAAAAJ")

# Generate JSON files (one per scholar; main.py writes to scholar_data/$id.json)
for id in "${ids[@]}"; do
  python /path/to/main.py "$id" >> /var/log/app.log 2>&1
done

# Copy the file to server
scp /path/to/output.json user@your.server:/path/where/to/put

#rsync -avz /path/to/output.json user@your.server:/path/where/to/put

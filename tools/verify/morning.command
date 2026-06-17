#!/bin/bash
# Double-click in the morning to turn the fetched passages into notes + rebuild.
cd "$(dirname "$0")"
clear
echo "============================================================"
echo "  Vienna Vivarium — write up the verified notes"
echo "============================================================"
echo ""
if [ ! -d .venv ]; then echo "Run start.command first (nothing fetched yet)."; read -p "Return to close. " _; exit 1; fi
source .venv/bin/activate

echo "Paste your Claude API key, then press Return."
echo "(It will NOT show on screen as you paste — that's normal.)"
read -s KEY
export ANTHROPIC_API_KEY="$KEY"
echo ""
if [ -z "$ANTHROPIC_API_KEY" ]; then echo "No key entered. Aborting."; read -p "Return to close. " _; exit 1; fi

echo "Writing notes from the real passages..."
python3 2_write_notes.py || { read -p "Stopped. Return to close. " _; exit 1; }
echo ""
echo "Merging into the site and rebuilding..."
python3 3_merge.py
echo ""
echo "------------------------------------------------------------"
echo "  Done. Tell Claude 'morning is done' and I'll commit, push,"
echo "  and confirm the green 'verified from source' badges went live."
echo "------------------------------------------------------------"
read -p "Press Return to close this window. " _

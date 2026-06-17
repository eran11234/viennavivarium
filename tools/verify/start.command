#!/bin/bash
# Double-click this file to run the overnight citation verifier.
cd "$(dirname "$0")"
clear
echo "============================================================"
echo "  Vienna Vivarium — overnight citation verifier"
echo "============================================================"
echo ""

CHROME="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
if [ ! -x "$CHROME" ]; then
  echo "Could not find Google Chrome at:"
  echo "  $CHROME"
  echo "If Chrome is installed somewhere else, tell Claude and I'll adjust this."
  read -p "Press Return to close. " _ ; exit 1
fi

echo "Step 1 of 2 — opening a dedicated Chrome window for your library login..."
"$CHROME" --remote-debugging-port=9222 --user-data-dir="$HOME/bva-verify-chrome" >/dev/null 2>&1 &
sleep 3
echo ""
echo ">>> In the Chrome window that just opened (it looks empty — that's normal):"
echo "      1) sign into your UNIVERSITY LIBRARY / proxy the way you normally do"
echo "      2) open this link in that window to check it works — you should see the"
echo "         FULL article, not a 'Get Access / \$' wall:"
echo ""
echo "         https://onlinelibrary.wiley.com/doi/10.1002/jez.b.22845"
echo ""
read -p "When you are logged in and that article opens in full, press Return here... " _

echo ""
echo "Step 2 of 2 — setting up (first time only, ~1 minute) and starting..."
if [ ! -d .venv ]; then python3 -m venv .venv || { echo "Python 3 not found. Run:  xcode-select --install"; read -p "Return to close. " _; exit 1; }; fi
source .venv/bin/activate
pip install -q --upgrade pip >/dev/null 2>&1
pip install -q -r requirements.txt || { echo "Install failed — check your internet."; read -p "Return to close. " _; exit 1; }

echo ""
echo "------------------------------------------------------------"
echo "  Running. Leave this window open; keep the Mac plugged in."
echo "  It does about one paper every 30 seconds (slow on purpose)."
echo "  To stop anytime: press  Control + C."
echo "------------------------------------------------------------"
echo ""
caffeinate -d python3 1_fetch_contexts.py

echo ""
echo "Finished (or stopped). Your progress is saved in contexts.jsonl."
read -p "Press Return to close this window. " _

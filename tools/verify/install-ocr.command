#!/bin/bash
# Double-click this ONCE to add OCR support (so the tool can read scanned papers).
clear
echo "============================================================"
echo "  Installing OCR support (one-time)"
echo "============================================================"
echo ""
echo "This can take 10-20 minutes. It may ask for your Mac login"
echo "password — type it (it won't show on screen) and press Return."
echo ""
read -p "Press Return to begin... " _

# 1) Homebrew (the standard macOS installer for tools like Tesseract)
BREW=""
for b in /opt/homebrew/bin/brew /usr/local/bin/brew "$(command -v brew 2>/dev/null)"; do
  [ -n "$b" ] && [ -x "$b" ] && BREW="$b" && break
done
if [ -z "$BREW" ]; then
  echo ""
  echo "Homebrew not found — installing it first..."
  /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
  for b in /opt/homebrew/bin/brew /usr/local/bin/brew "$(command -v brew 2>/dev/null)"; do
    [ -n "$b" ] && [ -x "$b" ] && BREW="$b" && break
  done
fi
if [ -z "$BREW" ]; then
  echo ""
  echo "Homebrew didn't finish installing. Take a screenshot of any red text and tell Claude."
  read -p "Press Return to close. " _ ; exit 1
fi

# 2) Tesseract OCR + language data
echo ""
echo "Installing Tesseract OCR + languages (this is the long part)..."
"$BREW" install tesseract tesseract-lang

# 3) Confirm
echo ""
if command -v tesseract >/dev/null 2>&1 || [ -x /opt/homebrew/bin/tesseract ] || [ -x /usr/local/bin/tesseract ]; then
  echo "============================================================"
  echo "  ✓ OCR is installed."
  echo "  Now just run start.command — it will read scanned papers"
  echo "  too, and retry the ones it skipped before."
  echo "============================================================"
else
  echo "Tesseract did not install cleanly. Take a screenshot and tell Claude."
fi
echo ""
read -p "Press Return to close this window. " _

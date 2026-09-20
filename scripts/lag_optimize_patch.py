# -*- coding: utf-8 -*-
"""Latency optimization: skip Tag detection + policy inference while keyboard control is active;
throttle frontend keydown/keyup so holding a key sends one POST, not a burst."""
import sys

F = "web_vis_board.py"
with open(F, "r", encoding="utf-8") as fh:
    c = fh.read()

fails = []

def rep(old, new, tag):
    global c
    if old not in c:
        fails.append(tag)
        return
    if c.count(old) > 1:
        fails.append(tag + " (multiple matches)")
        return
    c = c.replace(old, new)
    print(f"[ok] {tag}")

# 1. Skip Tag detection while keyboard control active
rep(
    """            if tag_detector is not None and color_image is not None:
                try:
                    # Apply CLAHE for IR overexposure compensation""",
    """            if tag_detector is not None and color_image is not None and not key_active:
                try:
                    # Apply CLAHE for IR overexposure compensation""",
    "skip tag detection when key_active",
)

# 2. Skip policy inference while keyboard control active
rep(
    """            if policy:
                try:
                    # Continuous carrot""",
    """            if policy and not key_active:
                try:
                    # Continuous carrot""",
    "skip policy inference when key_active",
)

# 3. Frontend: keydown throttled (only send on state change)
rep(
    """  if (['w','a','s','d',' ','q'].includes(k)) {
    keys[k] = true;
    sendKeyUpdate();
    updateKeyIndicator();
    e.preventDefault();
  }
});""",
    """  if (['w','a','s','d',' ','q'].includes(k)) {
    if (!keys[k]) {
      keys[k] = true;
      sendKeyUpdate();
      updateKeyIndicator();
    }
    e.preventDefault();
  }
});""",
    "keydown throttle",
)

# 4. Frontend: keyup throttled
rep(
    """  if (['w','a','s','d',' ','q'].includes(k)) {
    keys[k] = false;
    sendKeyUpdate();
    updateKeyIndicator();
    e.preventDefault();
  }
});""",
    """  if (['w','a','s','d',' ','q'].includes(k)) {
    if (keys[k]) {
      keys[k] = false;
      sendKeyUpdate();
      updateKeyIndicator();
    }
    e.preventDefault();
  }
});""",
    "keyup throttle",
)

if fails:
    print("FAILED PATCHES:", fails)
    sys.exit(1)

with open(F, "w", encoding="utf-8", newline="\n") as fh:
    fh.write(c)
print("Done. Patched file written.")

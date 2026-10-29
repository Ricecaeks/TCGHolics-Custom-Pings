#!/bin/sh
# Headed Chrome needs a display; start a virtual one unless running headless.
# (xvfb-run hangs as PID 1 in Docker, so Xvfb is started directly.)
if [ "${BROWSER_HEADLESS:-false}" != "true" ] && [ -z "$DISPLAY" ] && { [ "$1" = "run" ] || [ "$1" = "probe" ]; }; then
  Xvfb :99 -screen 0 1366x768x24 -nolisten tcp >/dev/null 2>&1 &
  export DISPLAY=:99
fi
exec python -m tcgpings "$@"

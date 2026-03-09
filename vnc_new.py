
Start vnc


#!/usr/bin/env bash
set -euo pipefail

DISPLAY_NUM="${DISPLAY:-:99}"
SCREEN_WIDTH="${SCREEN_WIDTH:-1280}"
SCREEN_HEIGHT="${SCREEN_HEIGHT:-720}"
SCREEN_DEPTH="${SCREEN_DEPTH:-24}"
VNC_PORT="${VNC_PORT:-5900}"
NOVNC_PORT="${NOVNC_PORT:-7900}"
NOVNC_WEB_DIR="${NOVNC_WEB_DIR:-/usr/share/novnc}"
SCENARIO="${DEMO_SCENARIO:-todomvc}"
DISPLAY_ID="${DISPLAY_NUM#:}"
XVFB_LOG="/tmp/xvfb.log"

cleanup() {
  pkill -P $$ || true
}
trap cleanup EXIT

wait_for_display() {
  local attempts=50
  local delay=0.2
  local i
  for ((i = 1; i <= attempts; i++)); do
    if xdpyinfo -display "${DISPLAY}" >/dev/null 2>&1; then
      return 0
    fi
    sleep "${delay}"
  done
  return 1
}

export DISPLAY="${DISPLAY_NUM}"
echo "[INFO] DISPLAY=${DISPLAY}"

LOCK_FILE="/tmp/.X${DISPLAY_ID}-lock"
SOCKET_FILE="/tmp/.X11-unix/X${DISPLAY_ID}"

if [[ -f "${LOCK_FILE}" || -S "${SOCKET_FILE}" ]]; then
  if ! xdpyinfo -display "${DISPLAY}" >/dev/null 2>&1; then
    echo "[INFO] Removing stale X artifacts for ${DISPLAY}"
    rm -f "${LOCK_FILE}" "${SOCKET_FILE}"
  fi
fi

if ! xdpyinfo -display "${DISPLAY}" >/dev/null 2>&1; then
  Xvfb "${DISPLAY}" -screen 0 "${SCREEN_WIDTH}x${SCREEN_HEIGHT}x${SCREEN_DEPTH}" -ac +extension GLX +render -noreset >"${XVFB_LOG}" 2>&1 &
fi

if ! wait_for_display; then
  echo "[ERROR] X display ${DISPLAY} did not become ready"
  [[ -f "${XVFB_LOG}" ]] && tail -n 50 "${XVFB_LOG}" || true
  exit 1
fi

fluxbox >/tmp/fluxbox.log 2>&1 &
x11vnc -display "${DISPLAY}" -rfbport "${VNC_PORT}" -forever -shared -nopw -xkb >/tmp/x11vnc.log 2>&1 &
websockify --web="${NOVNC_WEB_DIR}" "${NOVNC_PORT}" "localhost:${VNC_PORT}" >/tmp/novnc.log 2>&1 &

echo "[INFO] noVNC: http://localhost:${NOVNC_PORT}/vnc.html?autoconnect=1&resize=scale"
echo "[INFO] Running scenario: ${SCENARIO}"
python /app/demo_executor.py --scenario "${SCENARIO}"


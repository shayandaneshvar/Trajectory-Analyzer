#!/usr/bin/env bash
#
# Start / stop the Trajectory Analyzer Streamlit app.
#
# Usage:
#   ./run.sh start     # launch the app in the background
#   ./run.sh stop      # stop the running app
#   ./run.sh restart   # stop then start
#   ./run.sh status     # show whether it's running
#
# Override the port with PORT=1234 ./run.sh start
set -euo pipefail

cd "$(dirname "$0")"

PORT="${PORT:-8501}"
PID_FILE=".streamlit.pid"
LOG_FILE="streamlit.log"

is_running() {
  [[ -f "$PID_FILE" ]] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null
}

start() {
  if is_running; then
    echo "Already running (pid $(cat "$PID_FILE")) on port $PORT."
    return 0
  fi
  echo "Starting Trajectory Analyzer on http://localhost:$PORT ..."
  nohup streamlit run app.py \
    --server.headless true \
    --server.port "$PORT" \
    > "$LOG_FILE" 2>&1 &
  echo $! > "$PID_FILE"

  # Wait until it's serving (or the process dies).
  for _ in $(seq 1 40); do
    if grep -q "You can now view" "$LOG_FILE" 2>/dev/null; then
      echo "Started (pid $(cat "$PID_FILE")). Logs: $LOG_FILE"
      return 0
    fi
    if ! is_running; then
      echo "Failed to start. Last log lines:"
      tail -n 20 "$LOG_FILE"
      rm -f "$PID_FILE"
      return 1
    fi
    sleep 0.5
  done
  echo "Started (pid $(cat "$PID_FILE")), but readiness not confirmed. Check $LOG_FILE."
}

stop() {
  if ! is_running; then
    echo "Not running."
    rm -f "$PID_FILE"
    return 0
  fi
  local pid
  pid="$(cat "$PID_FILE")"
  echo "Stopping (pid $pid) ..."
  kill "$pid" 2>/dev/null || true
  for _ in $(seq 1 20); do
    kill -0 "$pid" 2>/dev/null || break
    sleep 0.25
  done
  kill -9 "$pid" 2>/dev/null || true
  rm -f "$PID_FILE"
  echo "Stopped."
}

status() {
  if is_running; then
    echo "Running (pid $(cat "$PID_FILE")) on port $PORT."
  else
    echo "Not running."
  fi
}

case "${1:-}" in
  start)   start ;;
  stop)    stop ;;
  restart) stop; start ;;
  status)  status ;;
  *)
    echo "Usage: $0 {start|stop|restart|status}" >&2
    exit 1
    ;;
esac

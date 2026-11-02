#!/usr/bin/env bash
# Install SHARP as boot services on the Raspberry Pi. Run ONCE, on the Pi:
#
#   cd ~/SHARP-HEMS && bash hardware/install_services.sh
#
# Afterwards the Pi agent, runtime bridge and scenario service start at every
# boot, restart if they stop, and keep retrying until the broker answers.
# Nothing has to be run over SSH again; scenarios are chosen on the dashboard.
#
# Logs:     journalctl -u sharp-pi-agent -f
# Restart:  sudo systemctl restart sharp-pi-agent sharp-runtime-bridge sharp-scenario
# Remove:   sudo systemctl disable --now sharp-pi-agent sharp-runtime-bridge sharp-scenario

set -euo pipefail

DIR="$(cd "$(dirname "$0")/.." && pwd)"
USER_NAME="$(id -un)"
PY="$DIR/.venv/bin/python"
UNITS="sharp-pi-agent sharp-runtime-bridge sharp-scenario"

fail() { echo "❌ $*" >&2; exit 1; }

echo "SHARP services → $DIR (user $USER_NAME)"

[ -x "$PY" ] || fail "No virtualenv at $DIR/.venv. Create it first:
   python3 -m venv .venv && .venv/bin/pip install -r hardware/requirements_pi.txt"

[ -f "$DIR/.env" ] || fail "No $DIR/.env with the broker settings (MQTT_HOST, MQTT_USER, MQTT_PASS, HOUSE_ID)."

grep -q '^MQTT_HOST=.' "$DIR/.env" || fail "MQTT_HOST is empty in $DIR/.env."

# The scripts default to secure WebSockets (port 8884). WebSockets sent to the
# plain MQTT port 8883 never connect.
TRANSPORT="$(sed -n 's/^MQTT_TRANSPORT=//p' "$DIR/.env" | tail -1 | tr -d '\r ')"
PORT="$(sed -n 's/^MQTT_PORT=//p' "$DIR/.env" | tail -1 | tr -d '\r ')"
if [ "${TRANSPORT:-websockets}" = "websockets" ] && [ "$PORT" = "8883" ]; then
  fail "$DIR/.env uses WebSockets but MQTT_PORT=8883. Fix it with:
   sed -i 's/^MQTT_PORT=.*/MQTT_PORT=8884/' $DIR/.env"
fi

"$PY" -c "import numpy, paho.mqtt.client, dotenv" 2>/dev/null \
  || fail "Python packages missing. Run: $PY -m pip install -r $DIR/hardware/requirements_pi.txt"

for script in pi_agent.py runtime_bridge.py scenario_service.py mock_rl_state.py; do
  [ -f "$DIR/hardware/$script" ] || fail "hardware/$script is missing. Update the code first (git pull)."
done

# Copies started by hand (nohup, a terminal) would answer every command twice.
echo "Stopping any copies started by hand..."
pkill -f "hardware/pi_agent.py" 2>/dev/null || true
pkill -f "hardware/runtime_bridge.py" 2>/dev/null || true
pkill -f "hardware/scenario_service.py" 2>/dev/null || true

for unit in $UNITS; do
  sed -e "s|__USER__|$USER_NAME|g" -e "s|__DIR__|$DIR|g" \
    "$DIR/hardware/systemd/$unit.service" \
    | sudo tee "/etc/systemd/system/$unit.service" > /dev/null
  echo "  installed $unit.service"
done

sudo systemctl daemon-reload
# shellcheck disable=SC2086
sudo systemctl enable --now $UNITS

sleep 3
echo
for unit in $UNITS; do
  printf '  %-22s %s\n' "$unit" "$(systemctl is-active "$unit" || true)"
done
echo
echo "✅ Done. They now start at every boot."
echo "   Watch the agent connect: journalctl -u sharp-pi-agent -f"

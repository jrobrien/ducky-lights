#!/bin/sh
# Install and start the background service. With no saved pattern it follows the
# current Omarchy theme (the default).
# The unit points at wherever this repo lives, so clone it anywhere.
set -e
dir=$(cd "$(dirname "$0")" && pwd)
mkdir -p ~/.config/systemd/user
sed "s#@DIR@#$dir#" "$dir/ducky-lights.service" > ~/.config/systemd/user/ducky-lights.service
systemctl --user daemon-reload
systemctl --user enable --now ducky-lights.service
systemctl --user status ducky-lights.service --no-pager | head -5
echo "Startup pattern: follows the Omarchy theme (default). Open the panel to change it."

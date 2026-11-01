#!/bin/sh
# Install and start the background service that holds your startup pattern.
set -e
mkdir -p ~/.config/systemd/user
cp "$(dirname "$0")/ducky-lights.service" ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now ducky-lights.service
systemctl --user status ducky-lights.service --no-pager | head -5

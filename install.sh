#!/bin/sh
# One-time: grant your user access to the keyboard's hidraw node.
set -e
sudo install -m644 "$(dirname "$0")/70-ducky.rules" /etc/udev/rules.d/70-ducky.rules
sudo udevadm control --reload
sudo udevadm trigger --subsystem-match=hidraw --action=change
echo "done; if the panel still reports permission denied, replug the keyboard"

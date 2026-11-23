#!/usr/bin/env bash
# Builds Homework11/stock-watch-kit.zip for Muse. The HW11 answer sheet is left out so the agent cannot see it.
set -eu
cd "$(dirname "$0")/.."
rm -f stock-watch-kit.zip
zip -qr stock-watch-kit.zip stock-watch -x '*/.DS_Store' 'stock-watch/state/*' 'stock-watch/digests/*' \
  'stock-watch/golden/gold_hw11.json' '*/__pycache__/*'
unzip -l stock-watch-kit.zip | tail -1

#!/system/bin/sh

MODDIR=${0%/*}
if [ -f "$MODDIR/logs/daemon.pid" ]; then
  kill -9 "$(cat "$MODDIR/logs/daemon.pid")" 2>/dev/null
  rm -f "$MODDIR/logs/daemon.pid"
fi
pkill -f "$MODDIR/bin/lanota-token-daemon" 2>/dev/null
pm uninstall com.desom.lanotachinatokenuploader >/dev/null 2>&1

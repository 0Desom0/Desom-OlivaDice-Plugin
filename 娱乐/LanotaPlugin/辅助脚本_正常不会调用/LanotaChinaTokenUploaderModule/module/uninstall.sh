#!/system/bin/sh

MODDIR=${0%/*}
pkill -f "$MODDIR/bin/lanota-token-daemon" 2>/dev/null
pm uninstall com.desom.lanotachinatokenuploader >/dev/null 2>&1

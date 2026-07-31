#!/system/bin/sh

MODDIR=${0%/*}
mkdir -p "$MODDIR/logs" "$MODDIR/state"
chmod 0700 "$MODDIR/logs" "$MODDIR/state"
chmod 0600 "$MODDIR/config.conf"
if ! pm path com.desom.lanotachinatokenuploader >/dev/null 2>&1; then
  pm install -r -d "$MODDIR/app/LanotaControl.apk" >/dev/null 2>&1
fi

# Root capture daemon stays alive on its own; the control app is optional.
if [ ! -f "$MODDIR/logs/daemon.pid" ] || ! kill -0 "$(cat "$MODDIR/logs/daemon.pid")" 2>/dev/null; then
  (
    while true; do
      "$MODDIR/bin/lanota-token-daemon" -config "$MODDIR/config.conf" -command auto \
        >>"$MODDIR/logs/daemon.log" 2>&1
      sleep 5
    done
  ) &
  echo $! > "$MODDIR/logs/daemon.pid"
fi

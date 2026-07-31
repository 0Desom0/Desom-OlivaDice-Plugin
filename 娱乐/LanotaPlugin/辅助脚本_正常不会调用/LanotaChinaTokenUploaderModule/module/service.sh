#!/system/bin/sh

MODDIR=${0%/*}
mkdir -p "$MODDIR/logs" "$MODDIR/state"
chmod 0700 "$MODDIR/logs" "$MODDIR/state"
chmod 0600 "$MODDIR/config.conf"
# Scanning and uploading are started explicitly from the control app.
if ! pm path com.desom.lanotachinatokenuploader >/dev/null 2>&1; then
  pm install -r -d "$MODDIR/app/LanotaControl.apk" >/dev/null 2>&1
fi

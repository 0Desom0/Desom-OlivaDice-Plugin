#!/system/bin/sh

ui_print "- Installing Lanota China Token Uploader"

if grep -q "CHANGE_ME" "$MODPATH/config.conf" 2>/dev/null; then
  abort "! config.conf is not configured. Build with config.local.conf first."
fi

ABI="$(getprop ro.product.cpu.abi)"
case "$ABI" in
  arm64-v8a)
    DAEMON_SOURCE="$MODPATH/bin/lanota-token-daemon-arm64"
    ;;
  armeabi-v7a|armeabi)
    DAEMON_SOURCE="$MODPATH/bin/lanota-token-daemon-arm"
    ;;
  *)
    abort "! Unsupported Android ABI: $ABI"
    ;;
esac

mv "$DAEMON_SOURCE" "$MODPATH/bin/lanota-token-daemon"
rm -f "$MODPATH/bin/lanota-token-daemon-arm64" "$MODPATH/bin/lanota-token-daemon-arm"
mkdir -p "$MODPATH/logs" "$MODPATH/state"

set_perm_recursive "$MODPATH" 0 0 0755 0644
set_perm "$MODPATH/service.sh" 0 0 0755
set_perm "$MODPATH/action.sh" 0 0 0755
set_perm "$MODPATH/uninstall.sh" 0 0 0755
set_perm "$MODPATH/bin/lanota-token-daemon" 0 0 0755
set_perm "$MODPATH/config.conf" 0 0 0600

if [ -f "$MODPATH/app/LanotaControl.apk" ]; then
  ui_print "- Installing Lanota Control app"
  pm install -r -d "$MODPATH/app/LanotaControl.apk" >/dev/null 2>&1
  if [ "$?" -ne 0 ]; then
    ui_print "! App install failed; install the APK manually"
  fi
fi

ui_print "- ABI: $ABI"
ui_print "- Root capture starts automatically; control app is optional"

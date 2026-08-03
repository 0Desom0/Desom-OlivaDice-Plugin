@echo off
set "SEVENZIP=C:/Program Files\7-Zip\7z.exe"
set "SRC=%~dp0"

for %%f in ("%SRC%*.opk") do (
    "%SEVENZIP%" a -tzip "%%~dpnf.zip" "%%f"
)

echo All done. Each .opk is now packed into its own .zip.
pause


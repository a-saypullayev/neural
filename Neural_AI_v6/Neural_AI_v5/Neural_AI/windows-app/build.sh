#!/bin/sh
# Rebuild the Windows launcher (needs mingw-w64: sudo apt install mingw-w64).
# Output goes to app/downloads/, where the /download/NeuralAI.exe endpoint serves it.
set -e
cd "$(dirname "$0")"
x86_64-w64-mingw32-windres launcher.rc -O coff -o launcher_res.o
x86_64-w64-mingw32-gcc -Os -s -mwindows -static -o ../app/downloads/NeuralAI.template.exe launcher.c launcher_res.o -lshell32
rm -f launcher_res.o
echo "Built app/downloads/NeuralAI.template.exe"

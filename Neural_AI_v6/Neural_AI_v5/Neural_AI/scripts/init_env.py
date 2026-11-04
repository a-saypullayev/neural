"""Create .env from .env.example if missing and make sure APP_SECRET is a real random value. Used by start.bat."""
import os
import secrets
import shutil

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
env, example = os.path.join(ROOT, ".env"), os.path.join(ROOT, ".env.example")

if not os.path.exists(env) and os.path.exists(example):
    shutil.copyfile(example, env)
lines = open(env, encoding="utf-8").read().splitlines() if os.path.exists(env) else []
found = False
for i, line in enumerate(lines):
    if line.startswith("APP_SECRET="):
        found = True
        value = line.split("=", 1)[1].strip()
        if not value or value.startswith("replace-with"):
            lines[i] = "APP_SECRET=" + secrets.token_urlsafe(48)
            print("Generated a new APP_SECRET in .env")
if not found:
    lines.append("APP_SECRET=" + secrets.token_urlsafe(48))
    print("Added APP_SECRET to .env")
open(env, "w", encoding="utf-8").write("\n".join(lines) + "\n")

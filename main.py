import os
import asyncio
import importlib
import threading
from flask import Flask

# ===== ENV PRINT (optional debug) =====
print("BOT1_TOKEN:", os.getenv("BOT1_TOKEN"))
print("BOT2_TOKEN:", os.getenv("INFORMATION_TICKET"))
print("BOT3_TOKEN:", os.getenv("BOT3_ADVERTISE"))

# ===== FLASK APP =====
app = Flask(__name__)

@app.route("/")
def ping():
    return "Bots running!"

def run_flask():
    port = int(os.environ.get("PORT", 10000))  # Render or other hosting
    app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)

# Start Flask in a background thread
threading.Thread(target=run_flask, daemon=True).start()

# ===== DISCORD BOTS =====
BOT_MODULES = ["bot1", "bot2", "bot3"]

async def start_bots():
    tasks = []

    for module_name in BOT_MODULES:
        try:
            module = importlib.import_module(module_name)
            if hasattr(module, "run_bot"):
                print(f"[INFO] Starting {module_name}...")
                tasks.append(asyncio.create_task(module.run_bot()))
            else:
                print(f"[WARNING] {module_name} does not have a run_bot() function.")
        except Exception as e:
            print(f"[ERROR] Failed to import {module_name}: {e}")

    if tasks:
        await asyncio.gather(*tasks)

if __name__ == "__main__":
    try:
        asyncio.run(start_bots())
    except KeyboardInterrupt:
        print("Shutting down bots...")

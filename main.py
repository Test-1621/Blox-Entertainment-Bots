import os
print("BOT1_TOKEN:", os.getenv("BOT1_TOKEN"))
print("BOT2_TOKEN:", os.getenv("INFORMATION_TICKET"))
print("BOT3_TOKEN:", os.getenv("BOT3_ADVERTISE"))

import asyncio
import importlib

# List of your bot files without the .py extension
BOT_MODULES = ["bot1", "bot2", "bot3"]

async def start_bots():
    tasks = []
    for module_name in BOT_MODULES:
        try:
            module = importlib.import_module(module_name)
            if hasattr(module, "run_bot"):
                tasks.append(asyncio.create_task(module.run_bot()))
            else:
                print(f"[WARNING] {module_name} does not have a run_bot() function.")
        except Exception as e:
            print(f"[ERROR] Failed to load {module_name}: {e}")

    if tasks:
        await asyncio.gather(*tasks)

if __name__ == "__main__":
    asyncio.run(start_bots())
from flask import Flask
import threading
import os

app = Flask(__name__)

@app.route("/")
def ping():
    return "Bot running!"

# Run Flask in a separate thread so it doesn't block your bots
def run_flask():
    port = int(os.environ.get("PORT", 10000))  # Render assigns a port in PORT env
    app.run(host="0.0.0.0", port=port)

threading.Thread(target=run_flask).start()

# Your existing Discord bot code here
# Example:
# import bot1
# import bot2
# import bot3

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

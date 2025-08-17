import random
import aiohttp
import json
import os
import asyncio
from roblox_api import RobloxAPI
from config import Config
import discord
from datetime import datetime

class VerificationManager:
    def __init__(self, bot):
        self.bot = bot
        self.codes = {}  # discord_id: code
        self.roblox_usernames = {}  # discord_id: roblox_username
        self.data_file = Config.VERIFICATION_DATA_FILE
        os.makedirs("data", exist_ok=True)
        if not os.path.exists(self.data_file):
            with open(self.data_file, "w") as f:
                json.dump({}, f)

        self.roblox_api = RobloxAPI()

    async def start_verification(self, ctx, roblox_username):
        code = str(random.randint(10**(Config.CODE_LENGTH-1), 10**Config.CODE_LENGTH -1))
        self.codes[ctx.author.id] = code
        self.roblox_usernames[ctx.author.id] = roblox_username

        message = (
            f" **Blox Entertainment Verification** \n\n"
            f"Hello **{ctx.author.name}**!\n\n"
            f"We are verifying a Roblox user named **{roblox_username}**.\n\n"
            f"**Step 1:** Go to your Roblox profile and place this code in your *About* section:\n"
            f"`{code}`\n\n"
            f"**Step 2:** Once you’ve saved the bio, return here and type:\n"
            f"`!check`\n\n"
            f"This code will expire in {Config.CODE_EXPIRY_MINUTES} minutes."
        )

        try:
            await ctx.author.send(message)
            print(f"[START_VERIF] Sent DM instructions to {ctx.author}")
            await ctx.reply("📬 Check your DMs for verification instructions!", mention_author=True)
        except Exception as e:
            print(f"[START_VERIF] Failed to send DM to {ctx.author}: {e}")
            await ctx.reply("❌ I couldn't DM you. Please enable DMs from server members and try again.", mention_author=True)

        asyncio.create_task(self.expire_code(ctx.author.id, Config.CODE_EXPIRY_MINUTES * 60))

    async def expire_code(self, discord_id, delay_seconds):
        await asyncio.sleep(delay_seconds)
        if discord_id in self.codes:
            print(f"[EXPIRE] Expiring verification code for Discord ID {discord_id}")
            self.codes.pop(discord_id, None)
            self.roblox_usernames.pop(discord_id, None)

    async def check_verification(self, ctx):
        discord_id = ctx.author.id
        code = self.codes.get(discord_id)
        roblox_username = self.roblox_usernames.get(discord_id)
        if not code or not roblox_username:
            print(f"[CHECK_VERIF] No pending verification for user {ctx.author}")
            return False, None, None

        print(f"[CHECK_VERIF] Checking Roblox username '{roblox_username}' for code '{code}' for user {ctx.author}")
        user_data = await self.roblox_api.get_user_by_username(roblox_username)
        if not user_data:
            print(f"[CHECK_VERIF] Roblox user '{roblox_username}' not found.")
            return False, None, None

        bio = await self.roblox_api.get_user_bio(user_data['id'])
        if bio is None:
            print(f"[CHECK_VERIF] Could not fetch bio for Roblox user ID {user_data['id']}")
            return False, None, None

        print(f"[CHECK_VERIF] Roblox bio for '{roblox_username}': {bio}")

        if code in bio:
            print(f"[CHECK_VERIF] Code found in bio! Verification successful.")
            self.save_verification(discord_id, roblox_username)
            self.codes.pop(discord_id, None)
            self.roblox_usernames.pop(discord_id, None)
            return True, roblox_username, user_data['id']
        else:
            print(f"[CHECK_VERIF] Code NOT found in bio.")
            return False, None, None

    def save_verification(self, discord_id, roblox_username):
        try:
            with open(self.data_file, "r") as f:
                data = json.load(f)
        except Exception as e:
            print(f"[SAVE_VERIF] Failed to read data file: {e}")
            data = {}

        if not isinstance(roblox_username, str):
            roblox_username = str(roblox_username)

        # Save as dictionary with verified_at timestamp
        data[str(discord_id)] = {
            "roblox_username": roblox_username,
            "verified_at": datetime.utcnow().isoformat()
        }

        try:
            with open(self.data_file, "w") as f:
                json.dump(data, f, indent=2)
            print(f"[SAVE_VERIF] Saved verification: Discord ID {discord_id} -> Roblox '{roblox_username}'")
        except Exception as e:
            print(f"[SAVE_VERIF] Failed to write data file: {e}")

    async def revoke_verification(self, guild, target, verified_role_name):
        print(f"[REVOKE_VERIF] Attempting to revoke verification for target '{target}'")

        try:
            with open(self.data_file, "r") as f:
                data = json.load(f)
        except Exception as e:
            print(f"[REVOKE_VERIF] Failed to read data file: {e}")
            return False, None, None

        affected_discord_user = None
        affected_roblox_username = None

        # Discord mention check
        if target.startswith("<@") and target.endswith(">"):
            try:
                discord_id = int(target.strip("<@!>"))
                if str(discord_id) in data:
                    affected_roblox_username = data.pop(str(discord_id)).get("roblox_username")
                    member = guild.get_member(discord_id)
                    if member is None:
                        try:
                            member = await guild.fetch_member(discord_id)
                        except Exception:
                            member = None
                    if member:
                        affected_discord_user = member
                    await self.remove_verified_role(guild, discord_id, verified_role_name)
                    with open(self.data_file, "w") as f:
                        json.dump(data, f, indent=2)
                    print(f"[REVOKE_VERIF] Revoked verification for Discord ID {discord_id}")
                    return True, affected_discord_user, affected_roblox_username
            except Exception as e:
                print(f"[REVOKE_VERIF] Error processing Discord mention: {e}")
                return False, None, None

        # Roblox username lookup (case insensitive)
        lowered_target = target.lower()
        for discord_id, record in list(data.items()):
            if isinstance(record, dict) and record.get("roblox_username", "").lower() == lowered_target:
                try:
                    affected_roblox_username = data.pop(discord_id).get("roblox_username")
                    member = guild.get_member(int(discord_id))
                    if member is None:
                        try:
                            member = await guild.fetch_member(int(discord_id))
                        except Exception:
                            member = None
                    if member:
                        affected_discord_user = member
                    await self.remove_verified_role(guild, int(discord_id), verified_role_name)
                    with open(self.data_file, "w") as f:
                        json.dump(data, f, indent=2)
                    print(f"[REVOKE_VERIF] Revoked verification for Roblox username '{target}'")
                    return True, affected_discord_user, affected_roblox_username
                except Exception as e:
                    print(f"[REVOKE_VERIF] Error processing Roblox username: {e}")
                    return False, None, None

        print(f"[REVOKE_VERIF] No verification record found for target '{target}'")
        return False, None, None

    async def remove_verified_role(self, guild, discord_id, verified_role_name):
        member = guild.get_member(discord_id)
        if member is None:
            try:
                member = await guild.fetch_member(discord_id)
            except Exception:
                print(f"[REMOVE_ROLE] Could not find member with ID {discord_id}")
                return
        role = discord.utils.get(guild.roles, name=verified_role_name)
        if role and role in member.roles:
            try:
                await member.remove_roles(role, reason="Verification revoked")
                print(f"[REMOVE_ROLE] Removed role '{verified_role_name}' from {member}")
            except Exception as e:
                print(f"[REMOVE_ROLE] Failed to remove role: {e}")
        else:
            print(f"[REMOVE_ROLE] Role '{verified_role_name}' not found on member {member}")

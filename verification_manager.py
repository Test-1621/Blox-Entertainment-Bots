import random
import aiohttp
import asyncio
import discord
from datetime import datetime
import asyncpg
from roblox_api import RobloxAPI
from config import Config

class VerificationManager:
    def __init__(self, bot):
        self.bot = bot
        self.db = None
        self.codes = {}  # discord_id: code
        self.roblox_usernames = {}  # discord_id: roblox_username
        self.roblox_api = RobloxAPI()

    # -------------------- Database Connection --------------------
    async def connect_db(self, DATABASE_URL):
        try:
            self.db = await asyncpg.connect(DATABASE_URL)
            print("✅ Connected to Supabase database!")
        except Exception as e:
            print(f"❌ Failed to connect to database: {e}")

    # -------------------- Verification Start --------------------
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

    # -------------------- Check Verification --------------------
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
            await self.save_verification(discord_id, roblox_username)
            self.codes.pop(discord_id, None)
            self.roblox_usernames.pop(discord_id, None)
            return True, roblox_username, user_data['id']
        else:
            print(f"[CHECK_VERIF] Code NOT found in bio.")
            return False, None, None

    # -------------------- Save Verification --------------------
    async def save_verification(self, discord_id, roblox_username):
        query = """
            INSERT INTO verifications(discord_id, roblox_username, verified_at, BEcredits)
            VALUES($1, $2, NOW(), 5)
            ON CONFLICT (discord_id) DO UPDATE
            SET roblox_username = $2, verified_at = NOW()
        """
        try:
            await self.db.execute(query, discord_id, roblox_username)
            print(f"[SAVE_VERIF] Saved verification: Discord ID {discord_id} -> Roblox '{roblox_username}' with 5 BEcredits")
        except Exception as e:
            print(f"[SAVE_VERIF] Failed to save to database: {e}")

    # -------------------- Revoke Verification --------------------
    async def revoke_verification(self, guild, target, verified_role_name):
        discord_id = None
        roblox_username = None

        # Discord mention check
        if target.startswith("<@") and target.endswith(">"):
            discord_id = int(target.strip("<@!>"))

        # Lookup by Roblox username if no mention
        if discord_id is None:
            try:
                result = await self.db.fetchrow(
                    "SELECT discord_id, roblox_username FROM verifications WHERE LOWER(roblox_username) = LOWER($1)",
                    target
                )
                if result:
                    discord_id = result["discord_id"]
                    roblox_username = result["roblox_username"]
            except Exception as e:
                print(f"[REVOKE_VERIF] Database lookup failed: {e}")
                return False, None, None

        if discord_id is None:
            return False, None, None

        # Remove role from Discord member
        member = guild.get_member(discord_id) or await guild.fetch_member(discord_id)
        if member:
            role = discord.utils.get(guild.roles, name=verified_role_name)
            if role and role in member.roles:
                try:
                    await member.remove_roles(role, reason="Verification revoked")
                    print(f"[REMOVE_ROLE] Removed role '{verified_role_name}' from {member}")
                except Exception as e:
                    print(f"[REMOVE_ROLE] Failed to remove role: {e}")

        # Delete from database
        try:
            await self.db.execute("DELETE FROM verifications WHERE discord_id = $1", discord_id)
            print(f"[REVOKE_VERIF] Revoked verification for Discord ID {discord_id}")
        except Exception as e:
            print(f"[REVOKE_VERIF] Failed to delete from database: {e}")
            return False, member, roblox_username

        return True, member, roblox_username

    # -------------------- BEcredits Management --------------------
    async def adjust_becredits(self, discord_id, amount):
        """Increase or decrease BEcredits. Can be negative to deduct."""
        try:
            await self.db.execute(
                "UPDATE verifications SET BEcredits = GREATEST(BEcredits + $1, 0) WHERE discord_id = $2",
                amount, discord_id
            )
        except Exception as e:
            print(f"[BEcredits] Failed to adjust credits for {discord_id}: {e}")

    async def get_becredits(self, discord_id):
        try:
            row = await self.db.fetchrow("SELECT BEcredits FROM verifications WHERE discord_id = $1", discord_id)
            return row["BEcredits"] if row else 0
        except Exception as e:
            print(f"[BEcredits] Failed to fetch credits for {discord_id}: {e}")
            return 0

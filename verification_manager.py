import random
import aiohttp
import os
import asyncio
import discord
import asyncpg
from datetime import datetime
from roblox_api import RobloxAPI
from config import Config

class VerificationManager:
    def __init__(self, bot):
        self.bot = bot
        self.codes = {}  # discord_id: code
        self.roblox_usernames = {}  # discord_id: roblox_username
        self.data_file = Config.VERIFICATION_DATA_FILE
        os.makedirs("data", exist_ok=True)
        if not os.path.exists(self.data_file):
            with open(self.data_file, "w") as f:
                f.write("{}")

        self.roblox_api = RobloxAPI()
        self.db_url = os.getenv("DATABASE_URL")
        self.pool = None
        asyncio.create_task(self.init_db())

    async def init_db(self):
        if not self.db_url:
            print("❌ DATABASE_URL not set. Supabase/Postgres connection failed.")
            return
        self.pool = await asyncpg.create_pool(self.db_url)
        async with self.pool.acquire() as conn:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS verifications (
                    discord_id BIGINT PRIMARY KEY,
                    roblox_username TEXT,
                    verified_at TIMESTAMP,
                    BEcredits INT DEFAULT 5
                )
            """)
        print("✅ Connected to database and ensured verifications table exists.")

    async def start_verification(self, ctx, roblox_username):
        code = str(random.randint(10**(Config.CODE_LENGTH-1), 10**Config.CODE_LENGTH -1))
        self.codes[ctx.author.id] = code
        self.roblox_usernames[ctx.author.id] = roblox_username

        message = (
            f"**Blox Entertainment Verification**\n\n"
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
            print(f"[START_VERIF] Failed to DM {ctx.author}: {e}")
            await ctx.reply("❌ I couldn't DM you. Please enable DMs and try again.", mention_author=True)

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
            print(f"[CHECK_VERIF] No pending verification for {ctx.author}")
            return False, None, None

        print(f"[CHECK_VERIF] Checking Roblox username '{roblox_username}' for code '{code}' for {ctx.author}")
        user_data = await self.roblox_api.get_user_by_username(roblox_username)
        if not user_data:
            return False, None, None

        bio = await self.roblox_api.get_user_bio(user_data['id'])
        if bio is None:
            return False, None, None

        if code in bio:
            print(f"[CHECK_VERIF] Code found in bio! Verification successful.")
            await self.save_verification(discord_id, roblox_username)
            self.codes.pop(discord_id, None)
            self.roblox_usernames.pop(discord_id, None)
            return True, roblox_username, user_data['id']
        return False, None, None

    async def save_verification(self, discord_id, roblox_username):
        timestamp = datetime.utcnow()
        try:
            async with self.pool.acquire() as conn:
                # Upsert: if user exists, keep BEcredits, else default 5
                await conn.execute("""
                    INSERT INTO verifications(discord_id, roblox_username, verified_at)
                    VALUES($1, $2, $3)
                    ON CONFLICT(discord_id) DO UPDATE
                    SET roblox_username = EXCLUDED.roblox_username,
                        verified_at = EXCLUDED.verified_at
                """, discord_id, roblox_username, timestamp)
            print(f"[SAVE_VERIF] Saved verification for {discord_id} -> {roblox_username}")
        except Exception as e:
            print(f"[SAVE_VERIF] DB error: {e}")

    async def revoke_verification(self, guild, target, verified_role_name):
        affected_discord_user = None
        affected_roblox_username = None
        discord_id = None

        # Handle Discord mention
        if target.startswith("<@") and target.endswith(">"):
            discord_id = int(target.strip("<@!>"))

        # Otherwise, look up by Roblox username
        async with self.pool.acquire() as conn:
            if discord_id:
                record = await conn.fetchrow("SELECT * FROM verifications WHERE discord_id=$1", discord_id)
            else:
                record = await conn.fetchrow("SELECT * FROM verifications WHERE LOWER(roblox_username)=$1", target.lower())
                if record:
                    discord_id = record['discord_id']

            if not record:
                return False, None, None

            affected_roblox_username = record['roblox_username']
            member = guild.get_member(discord_id)
            if member is None:
                try:
                    member = await guild.fetch_member(discord_id)
                except Exception:
                    member = None
            if member:
                affected_discord_user = member

            # Remove DB entry
            await conn.execute("DELETE FROM verifications WHERE discord_id=$1", discord_id)
            # Remove role
            await self.remove_verified_role(guild, discord_id, verified_role_name)
            return True, affected_discord_user, affected_roblox_username

    async def remove_verified_role(self, guild, discord_id, verified_role_name):
        member = guild.get_member(discord_id)
        if member is None:
            try:
                member = await guild.fetch_member(discord_id)
            except Exception:
                return
        role = discord.utils.get(guild.roles, name=verified_role_name)
        if role and role in member.roles:
            try:
                await member.remove_roles(role, reason="Verification revoked")
            except Exception as e:
                print(f"[REMOVE_ROLE] Failed: {e}")

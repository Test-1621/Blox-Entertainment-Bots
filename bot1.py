import os
import discord
from discord.ext import commands
from datetime import datetime
import aiohttp
from verification_manager import VerificationManager  # updated version using Supabase

# ===== TOKEN (Render Secret) =====
TOKEN = os.getenv("BOT1_TOKEN")  # Set in Render > Environment > Secrets
DATABASE_URL = os.getenv("DATABASE_URL")  # Supabase Postgres URL

if TOKEN:
    print("✅ Token loaded from Render secret BOT1_TOKEN.")
else:
    print("❌ No token found. Set BOT1_TOKEN in Render Environment secrets.")

if DATABASE_URL:
    print("✅ Database URL loaded from Render secret DATABASE_URL.")
else:
    print("❌ No DATABASE_URL found. Set DATABASE_URL in Render Environment secrets.")

# ===== CONFIG (update IDs/names to your server) =====
GUILD_ID = 1406058084484518021
VERIFY_CHANNEL_ID = 1406090150953615372
VERIFIED_ROLE_NAME = "Verified"
OWNER_ROLE_NAME = "Blox Entertainment Staff"
VERIFICATION_LOG_CHANNEL_ID = 1406142661752131634
ADMIN_LOG_CHANNEL_ID = 1406145134558711920

# ===== BOT SETUP =====
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)
verification_manager = VerificationManager(bot)

# ===== ROBLOX HELPERS =====
ROBLOX_HEADSHOT = "https://thumbnails.roblox.com/v1/users/avatar-headshot"
ROBLOX_PROFILE_FMT = "https://www.roblox.com/users/{}/profile"

async def fetch_roblox_id(username: str) -> int | None:
    url = "https://users.roblox.com/v1/usernames/users"
    payload = {"usernames": [username], "excludeBannedUsers": True}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, timeout=10) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json()
                if not data.get("data"):
                    return None
                return int(data["data"][0]["id"])
    except Exception:
        return None

async def fetch_headshot_url(user_id: int) -> str | None:
    params = {
        "userIds": str(user_id),
        "size": "150x150",
        "format": "Png",
        "isCircular": "true",
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(ROBLOX_HEADSHOT, params=params, timeout=10) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json()
                items = data.get("data") or []
                if not items:
                    return None
                return items[0].get("imageUrl")
    except Exception:
        return None

def roblox_profile_url(user_id: int | None) -> str | None:
    return ROBLOX_PROFILE_FMT.format(user_id) if user_id else None

# ===== UTIL: format verification timestamp =====
def format_verified_at(raw_value) -> str:
    """Handles both UNIX timestamps (float/int) and ISO string."""
    if not raw_value:
        return "Unknown"
    try:
        if isinstance(raw_value, (int, float)):
            return datetime.utcfromtimestamp(raw_value).strftime("%Y-%m-%d %H:%M:%S UTC")
        elif isinstance(raw_value, str):
            dt = datetime.fromisoformat(raw_value)
            return dt.strftime("%Y-%m-%d %H:%M:%S UTC")
        else:
            return "Unknown"
    except Exception:
        return "Unknown"

# ===== EVENTS =====
@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}")
    if DATABASE_URL:
        await verification_manager.connect_db(DATABASE_URL)

@bot.event
async def on_message(message: discord.Message):
    if message.author == bot.user:
        return

    if message.content.startswith("!verify"):
        if message.guild is None or message.channel.id != VERIFY_CHANNEL_ID:
            await message.channel.send("❌ Please use !verify only in the verify channel.")
            return

    if message.content.startswith("!check"):
        if message.guild is not None:
            await message.channel.send("❌ Please use !check only in DMs.")
            return

    await bot.process_commands(message)

# ===== COMMANDS =====
@bot.command()
async def verify(ctx: commands.Context, roblox_username: str = None):
    if ctx.guild is None or ctx.channel.id != VERIFY_CHANNEL_ID:
        await ctx.reply("❌ Please use this command only in the verify channel.", mention_author=True)
        return
    if roblox_username is None:
        await ctx.reply("❌ Please provide your Roblox username. Example: `!verify Builderman`", mention_author=True)
        return
    await verification_manager.start_verification(ctx, roblox_username)

@bot.command()
async def check(ctx: commands.Context):
    if ctx.guild is not None:
        await ctx.reply("❌ Please use this command only in DMs.", mention_author=True)
        return

    verified, roblox_user, roblox_user_id = await verification_manager.check_verification(ctx)
    if not verified:
        await ctx.send("❌ Verification failed or you have not completed verification yet. Please make sure you've added the code to your Roblox bio.")
        return

    guild = bot.get_guild(GUILD_ID) or await bot.fetch_guild(GUILD_ID)
    try:
        member = guild.get_member(ctx.author.id) or await guild.fetch_member(ctx.author.id)
    except discord.NotFound:
        await ctx.send("❌ Could not find your member record in the server.")
        return

    role = discord.utils.get(guild.roles, name=VERIFIED_ROLE_NAME)
    if role is None:
        await ctx.send(f"❌ The role '{VERIFIED_ROLE_NAME}' does not exist.")
        return

    try:
        await member.add_roles(role, reason="User verified successfully")
    except discord.Forbidden:
        await ctx.send("❌ I don't have permission to give you that role. Please contact an admin.")
        return

    await ctx.send(f"✅ You are now verified as **{roblox_user}** and have been given the '{VERIFIED_ROLE_NAME}' role!")

    # Build rich log
    log_channel = bot.get_channel(VERIFICATION_LOG_CHANNEL_ID)
    if log_channel:
        profile_url = roblox_profile_url(roblox_user_id)
        avatar_url = await fetch_headshot_url(roblox_user_id) if roblox_user_id else None

        embed = discord.Embed(
            title="User Verified",
            color=discord.Color.green(),
            timestamp=datetime.utcnow()
        )
        embed.add_field(name="Discord User", value=f"{ctx.author} ({ctx.author.id})", inline=False)
        embed.add_field(name="Roblox Username", value=roblox_user, inline=True)
        embed.add_field(name="Roblox User ID", value=str(roblox_user_id), inline=True)
        embed.add_field(name="🕒 Verified at", value=format_verified_at(datetime.utcnow()), inline=False)
        if profile_url:
            embed.add_field(name="Roblox Profile", value=f"[View Profile]({profile_url})", inline=False)
            embed.url = profile_url
        if avatar_url:
            embed.set_thumbnail(url=avatar_url)
        await log_channel.send(embed=embed)

# ===== INFO COMMAND =====
@bot.command()
async def info(ctx: commands.Context, target: str = None):
    if OWNER_ROLE_NAME not in [role.name for role in getattr(ctx.author, "roles", [])]:
        await ctx.reply("❌ You do not have permission to use this command.", mention_author=True)
        return
    if not target:
        await ctx.reply("❌ Please provide a Roblox username or Discord mention.", mention_author=True)
        return

    discord_id = None
    member = None
    guild = bot.get_guild(GUILD_ID) or await bot.fetch_guild(GUILD_ID)

    if target.startswith("<@") and target.endswith(">"):
        discord_id = int(target.replace("<@", "").replace(">", "").replace("!", ""))
        member = guild.get_member(discord_id) or await guild.fetch_member(discord_id)
    else:
        try:
            result = await verification_manager.db.fetchrow(
                "SELECT discord_id, roblox_username FROM verifications WHERE LOWER(roblox_username) = LOWER($1)",
                target
            )
            if result:
                discord_id = result["discord_id"]
                member = guild.get_member(discord_id) or await guild.fetch_member(discord_id)
        except Exception:
            pass

    if discord_id is None or not member:
        await ctx.reply(f"❌ No verification record found for {target}.", mention_author=True)
        return

    roblox_username = result["roblox_username"] if result else "Unknown"
    roblox_user_id = await fetch_roblox_id(roblox_username) if roblox_username else None
    profile_url = roblox_profile_url(roblox_user_id)
    avatar_url = await fetch_headshot_url(roblox_user_id) if roblox_user_id else None

    embed = discord.Embed(
        title="Blox Entertainment Verification",
        color=discord.Color.blue(),
        timestamp=datetime.utcnow()
    )
    embed.add_field(name="Discord User", value=f"{member} ({member.id})", inline=False)
    embed.add_field(name="Discord ID", value=str(member.id), inline=False)
    embed.add_field(name="Roblox Username", value=roblox_username, inline=True)
    embed.add_field(name="Roblox User ID", value=str(roblox_user_id), inline=True)
    if profile_url:
        embed.add_field(name="Roblox Profile", value=f"[View Profile]({profile_url})", inline=False)
    if avatar_url:
        embed.set_thumbnail(url=avatar_url)
    embed.add_field(name="🕒 Verified at", value=format_verified_at(datetime.utcnow()), inline=False)

    await ctx.reply(embed=embed)

    log_channel = bot.get_channel(ADMIN_LOG_CHANNEL_ID)
    if log_channel:
        log_embed = discord.Embed(
            title="Info Command Executed",
            color=discord.Color.blue(),
            timestamp=datetime.utcnow()
        )
        log_embed.add_field(name="Admin", value=f"{ctx.author} ({ctx.author.id})", inline=False)
        log_embed.add_field(name="Target Queried", value=target, inline=False)
        log_embed.add_field(name="Result - Roblox Username", value=roblox_username, inline=True)
        log_embed.add_field(name="Result - Roblox User ID", value=str(roblox_user_id), inline=True)
        if profile_url:
            log_embed.add_field(name="Roblox Profile", value=f"[View Profile]({profile_url})", inline=False)
            log_embed.url = profile_url
        if avatar_url:
            log_embed.set_thumbnail(url=avatar_url)
        await log_channel.send(embed=log_embed)

# ===== REVOKE COMMAND =====
@bot.command()
async def revoke(ctx: commands.Context, target: str = None):
    if target is None:
        await ctx.reply("❌ Please provide a Roblox username or Discord mention. Example: `!revoke Builderman` or `!revoke @User`", mention_author=True)
        return
    if OWNER_ROLE_NAME not in [role.name for role in getattr(ctx.author, "roles", [])]:
        await ctx.reply("❌ You do not have permission to use this command.", mention_author=True)
        return

    guild = bot.get_guild(GUILD_ID) or await bot.fetch_guild(GUILD_ID)

    removed, affected_discord_user, affected_roblox_username = await verification_manager.revoke_verification(
        guild, target, VERIFIED_ROLE_NAME
    )

    if not removed:
        await ctx.reply(f"❌ Could not find any verification record for `{target}`.", mention_author=True)
        return

    await ctx.reply(f"✅ Verification revoked for `{target}` and role removed if applicable.", mention_author=True)

# ===== PURGE COMMAND =====
@bot.command()
@commands.has_role(OWNER_ROLE_NAME)
async def purge(ctx: commands.Context, amount: int):
    if amount < 1:
        await ctx.reply("❌ Please specify a number greater than 0.", mention_author=True)
        return

    deleted = await ctx.channel.purge(limit=amount + 1)
    await ctx.send(f"✅ Purged {len(deleted) - 1} messages.", delete_after=5)

# ===== RUNNER =====
async def run_bot():
    if not TOKEN:
        print("❌ bot1: No token — not starting.")
        return
    await bot.start(TOKEN)

if __name__ == "__main__":
    import asyncio
    asyncio.run(run_bot())

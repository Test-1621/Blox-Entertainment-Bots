import discord
from discord.ext import commands, tasks
from discord.ui import View, Select
import os
import json
from datetime import datetime
from verification_manager import VerificationManager  # keep your existing verification manager

# ===== TOKEN HANDLING (robust) =====
TOKEN = (
    os.getenv("BOT3_ADVERTISE")
    or os.getenv("BOT3_TOKEN")
    or os.getenv("DISCORD_BOT3_TOKEN")
)

if TOKEN:
    print("✅ Token loaded (BOT3_ADVERTISE / BOT3_TOKEN / DISCORD_BOT3_TOKEN).")
else:
    raise ValueError("❌ No token found. Set BOT3_ADVERTISE, BOT3_TOKEN, or DISCORD_BOT3_TOKEN in Secrets/Env.")

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)
verif_manager = VerificationManager(bot)

# ===== STAFF ROLE =====
ROLE_ID_STAFF = 1406082203393462403  # Blox Entertainment Staff

# ===== PERSISTENCE (Advertisement Requests) =====
AD_DB_FILE = "advertisement_requests.json"

def _load_ads():
    try:
        with open(AD_DB_FILE, "r") as f:
            return json.load(f)
    except Exception:
        return []

def _save_ads(data):
    try:
        with open(AD_DB_FILE, "w") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        print(f"[AD_DB] Save failed: {e}")

def _append_ad(item):
    data = _load_ads()
    data.append(item)
    _save_ads(data)

def _update_ad(ad_id, updater):
    data = _load_ads()
    for rec in data:
        if rec.get("id") == ad_id:
            updater(rec)
            break
    _save_ads(data)

def _guild_pending_ads(guild_id):
    return [a for a in _load_ads() if a.get("guild_id") == guild_id and a.get("status") == "pending"]

# ===== COMMAND: !advertise =====
@bot.command()
async def advertise(ctx):
    if ctx.channel.name != "advertise-here":
        await ctx.reply("❌ You can only use this command in #advertise-here.", mention_author=True)
        return

    user_id_str = str(ctx.author.id)

    # Load verified users
    try:
        with open(verif_manager.data_file, "r") as f:
            VERIFICATIONS = json.load(f)
    except Exception:
        VERIFICATIONS = {}

    if user_id_str not in VERIFICATIONS:
        await ctx.reply("❌ You must verify your Roblox account before submitting an advertisement.", mention_author=True)
        return

    roblox_username = VERIFICATIONS[user_id_str]

    # Ask for advertisement text via DM
    try:
        dm = await ctx.author.create_dm()
        await dm.send(
            f"Hello! Your verified Roblox username: {roblox_username}\n"
            "📢 Please type your advertisement message here. You have 5 minutes to respond."
        )

        def _ad_check(m: discord.Message):
            return m.author.id == ctx.author.id and isinstance(m.channel, discord.DMChannel)

        msg = await bot.wait_for("message", check=_ad_check, timeout=300)
        ad_text = msg.content.strip()

    except discord.Forbidden:
        await ctx.reply("❌ I couldn't DM you! Please enable DMs from server members.", mention_author=True)
        return
    except Exception:
        await ctx.reply("⏱️ Advertisement cancelled (no message provided).", mention_author=True)
        return

    # Save advertisement request
    ad_id = f"{ctx.guild.id}-{ctx.author.id}-{int(datetime.utcnow().timestamp())}"
    record = {
        "id": ad_id,
        "guild_id": ctx.guild.id,
        "user_id": ctx.author.id,
        "username": str(ctx.author),
        "roblox_username": roblox_username,
        "ad_text": ad_text,
        "status": "pending",
        "submitted_at": datetime.utcnow().isoformat() + "Z",
        "processed_by": None,
        "decision": None,
        "comments": None
    }
    _append_ad(record)

    # Log to #advertisement-requests
    ad_log_channel = discord.utils.get(ctx.guild.text_channels, name="advertisement-requests")
    if ad_log_channel:
        emb = discord.Embed(
            title="New Advertisement Request (Pending)",
            description=(
                f"**User:** {ctx.author} ({ctx.author.id})\n"
                f"**Roblox Username:** {roblox_username}\n"
                f"**Advertisement:** {ad_text}\n"
                f"**Request ID:** `{ad_id}`"
            ),
            color=discord.Color.yellow(),
            timestamp=datetime.utcnow()
        )
        try:
            await ad_log_channel.send(embed=emb)
        except Exception as e:
            print(f"[AD_LOG] Failed to send embed: {e}")

    await ctx.reply("✅ Your advertisement request has been submitted! You’ll receive a DM when it’s reviewed.", mention_author=True)
# ===== COMMAND: !advertisement_requests =====
def _is_staff(member: discord.Member) -> bool:
    return any(r.id == ROLE_ID_STAFF for r in member.roles)

class AdSelect(Select):
    def __init__(self, pending_records, guild: discord.Guild):
        options = []
        for rec in pending_records:
            user = guild.get_member(rec["user_id"])
            label = user.name if user else rec["username"]
            options.append(discord.SelectOption(
                label=label,
                value=rec["id"],
                description=f"Submitted at {rec['submitted_at']}"
            ))
        super().__init__(placeholder="Select a pending advertisement", options=options, min_values=1, max_values=1)

class DecisionSelect(Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="Approve", emoji="✅"),
            discord.SelectOption(label="Deny", emoji="❌"),
        ]
        super().__init__(placeholder="Decision", options=options, min_values=1, max_values=1)

@bot.command()
async def advertisement_requests(ctx):
    """Process pending advertisements (Staff only)."""
    if ctx.channel.name != "staff-commands":
        await ctx.reply("❌ Use this command in #staff-commands.", mention_author=True)
        return

    if not isinstance(ctx.author, discord.Member) or not _is_staff(ctx.author):
        await ctx.reply("❌ You must be **Blox Entertainment Staff** to use this command.", mention_author=True)
        return

    pending = _guild_pending_ads(ctx.guild.id)
    if not pending:
        await ctx.reply("📭 No pending advertisement requests.", mention_author=True)
        return

    # Step 1: select request
    selector = AdSelect(pending, ctx.guild)
    view1 = View(timeout=90)
    view1.add_item(selector)
    msg1 = await ctx.reply("🗂️ Select a **pending advertisement request**:", view=view1, mention_author=True)

    def _sel_done(i: discord.Interaction):
        return i.user.id == ctx.author.id and i.data.get("component_type") == 3

    try:
        inter1 = await bot.wait_for("interaction", check=_sel_done, timeout=90)
        await inter1.response.defer()
        ad_id = selector.values[0]
    except Exception:
        await msg1.edit(content="⏱️ Timed out. Try `!advertisement_requests` again.", view=None)
        return

    chosen = next((r for r in _guild_pending_ads(ctx.guild.id) if r["id"] == ad_id), None)
    if not chosen:
        await ctx.send("⚠️ That advertisement request is no longer pending.")
        return

    # Step 2: decision dropdown
    dec_select = DecisionSelect()
    view2 = View(timeout=60)
    view2.add_item(dec_select)
    msg2 = await ctx.send(
        f"📌 Selected: **{chosen['username']}** — Advertisement preview:\n{chosen['ad_text']}\nChoose a decision:",
        view=view2
    )

    def _dec_done(i: discord.Interaction):
        return i.user.id == ctx.author.id and i.data.get("component_type") == 3

    try:
        inter2 = await bot.wait_for("interaction", check=_dec_done, timeout=60)
        await inter2.response.defer()
        decision = dec_select.values[0]  # "Approve" or "Deny"
    except Exception:
        await msg2.edit(content="⏱️ Timed out. Decision not recorded.", view=None)
        return

    # Step 3: comments (optional)
    await ctx.send("💬 Enter any **comments** for this decision (or type `none`). You have 2 minutes.")

    def _comment_check(m: discord.Message):
        return m.author.id == ctx.author.id and m.channel.id == ctx.channel.id

    try:
        comment_msg = await bot.wait_for("message", check=_comment_check, timeout=120)
        comments = comment_msg.content.strip()
        if comments.lower() == "none":
            comments = ""
    except Exception:
        comments = ""

    # Update record (status + processor info)
    status_val = "approved" if decision == "Approve" else "denied"
    _update_ad(ad_id, lambda r: r.update({
        "status": status_val,
        "processed_by": str(ctx.author),
        "decision": decision.lower(),
        "comments": comments,
        "processed_at": datetime.utcnow().isoformat() + "Z"
    }))
    final = next((r for r in _load_ads() if r["id"] == ad_id), None)

    # If approved, post the advertisement
    if final and status_val == "approved":
        ad_channel = discord.utils.get(ctx.guild.text_channels, name="approved-ads")
        if ad_channel:
            try:
                await ad_channel.send(f"📣 Advertisement by **{final['username']}** ({final['roblox_username']}):\n{final['ad_text']}")
            except Exception as e:
                await ctx.send(f"⚠️ Failed to post advertisement: {e}")

    # Log to #advertisement-logs
    log_channel = discord.utils.get(ctx.guild.text_channels, name="advertisement-logs")
    if final:
        c = discord.Color.green() if final["status"] == "approved" else discord.Color.red()
        emb = discord.Embed(
            title=f"Advertisement Request {final['status'].title()}",
            description=(
                f"**User:** {final['username']} ({final['user_id']})\n"
                f"**Roblox Username:** {final['roblox_username']}\n"
                f"**Advertisement:** {final['ad_text']}\n"
                f"**Decision:** {final['status'].title()}\n"
                f"**Comments:** {final['comments'] or '(none)'}\n"
                f"**Processed by:** {final['processed_by']}\n"
                f"**Request ID:** `{final['id']}`"
            ),
            color=c,
            timestamp=datetime.utcnow()
        )
        try:
            if log_channel:
                await log_channel.send(embed=emb)
            else:
                await ctx.send("⚠️ Channel **#advertisement-logs** not found. Please create it.")
        except Exception as e:
            await ctx.send(f"⚠️ Failed to send log: `{e}`")

    # DM the submitter
    user = ctx.guild.get_member(final["user_id"]) if final else None
    if user:
        try:
            dm = await user.create_dm()
            await dm.send(
                f"📣 Your advertisement request has been **{final['status'].upper()}**.\n"
                f"• Advertisement: {final['ad_text']}\n"
                f"• Comments: {final['comments'] or '(none)'}\n"
                + ("✅ It has been posted!" if final["status"] == "approved" else "❌ It was denied.")
            )
        except discord.Forbidden:
            await ctx.send("ℹ️ Could not DM the submitter (DMs closed).")

    await ctx.send(f"✅ Decision **{final['status'].title()}** recorded for **{final['username']}**.")

# ===== CHANNEL PURGE TASK =====
@tasks.loop(minutes=1)
async def purge_channels():
    channel_names = ["verify", "advertise-here"]
    for name in channel_names:
        channel = discord.utils.get(bot.get_all_channels(), name=name)
        if channel and isinstance(channel, discord.TextChannel):
            try:
                await channel.purge(limit=100, bulk=True)
            except Exception as e:
                print(f"[PURGE] Failed to purge #{name}: {e}")

@bot.event
async def on_ready():
    purge_channels.start()
    print(f"[BOT3] Logged in as {bot.user} (ID: {bot.user.id})")

async def run_bot():
    if not TOKEN:
        print("❌ bot3: No token — not starting.")
        return
    await bot.start(TOKEN)

if __name__ == "__main__":
    import asyncio
    if not TOKEN:
        raise SystemExit("❌ No token set. Set BOT3_ADVERTISE, BOT3_TOKEN, or DISCORD_BOT3_TOKEN.")
    asyncio.run(run_bot())

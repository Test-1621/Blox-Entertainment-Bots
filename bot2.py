import os
import asyncio
import discord
from discord.ext import commands
from discord.ui import Select, View
from datetime import datetime

BOT_NAME = "Blox Entertainment Information"
BOT_PREFIX = "!"
TOKEN = os.getenv("INFORMATION_TICKET")
OWNER_ROLE_NAME = "Blox Entertainment Staff"
LOG_CHANNEL_NAME = "administration-logs"  # name of the logging channel

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix=BOT_PREFIX, intents=intents)

color_map = {
    "Blue": discord.Color.blue(),
    "Green": discord.Color.green(),
    "Red": discord.Color.red(),
    "Purple": discord.Color.purple(),
    "Orange": discord.Color.orange(),
    "Gold": discord.Color.gold(),
    "Dark Blue": discord.Color.dark_blue(),
    "Dark Green": discord.Color.dark_green(),
    "Dark Red": discord.Color.dark_red(),
    "Teal": discord.Color.teal(),
    "Default": discord.Color.default(),
}

async def ask_user(ctx, question, timeout=120):
    """Send a reply and wait for user's response in the same channel."""
    await ctx.reply(question, mention_author=True)
    def check(m):
        return m.author == ctx.author and m.channel == ctx.channel and not m.author.bot
    try:
        msg = await bot.wait_for("message", timeout=timeout, check=check)
        return msg.content.strip()
    except asyncio.TimeoutError:
        await ctx.reply("⌛ You took too long to reply. Operation cancelled.", mention_author=True)
        return None

class ColorSelect(Select):
    def __init__(self, embed_data):
        options = [
            discord.SelectOption(label=color, description=f"{color} color", value=color)
            for color in color_map
        ]
        super().__init__(placeholder="Select embed color", options=options)
        self.embed_data = embed_data

    async def callback(self, interaction: discord.Interaction):
        selected_color = self.values[0]
        self.embed_data["color"] = selected_color
        await interaction.response.send_message(f"✅ Color set to **{selected_color}**.", ephemeral=True)

class ChannelSelect(Select):
    def __init__(self, embed_data, channels):
        options = [
            discord.SelectOption(label=ch.name, value=str(ch.id))
            for ch in channels
        ]
        super().__init__(placeholder="Select target channel", options=options)
        self.embed_data = embed_data

    async def callback(self, interaction: discord.Interaction):
        channel_id = int(self.values[0])
        self.embed_data["channel"] = channel_id
        await interaction.response.send_message("✅ Channel selected.", ephemeral=True)

def truncate_field(text, limit=1024):
    """Truncate text for embed fields to avoid Discord limit."""
    if text is None:
        return "None"
    return text if len(text) <= limit else text[:limit-3] + "..."

@bot.command()
@commands.has_role(OWNER_ROLE_NAME)
async def message(ctx):
    embed_data = {
        "title": None,
        "description": None,
        "footer": None,
        "color": "Default",
        "channel": None,
    }

    # 1. Ask for Title
    title = await ask_user(ctx, "Please reply with the embed **title** (or type 'none' to skip):")
    if title is None:
        return
    embed_data["title"] = None if title.lower() == "none" else title

    # 2. Ask for Description
    description = await ask_user(ctx, "Please reply with the embed **description** (or type 'none' to skip):")
    if description is None:
        return
    embed_data["description"] = None if description.lower() == "none" else description

    # 3. Ask for Footer
    footer = await ask_user(ctx, "Please reply with the embed **footer** (or type 'none' to skip):")
    if footer is None:
        return
    embed_data["footer"] = None if footer.lower() == "none" else footer

    # 4. Color select dropdown
    view = View()
    color_select = ColorSelect(embed_data)
    view.add_item(color_select)
    color_msg = await ctx.reply("Select embed **color** from dropdown below:", view=view, mention_author=True)

    def color_check(i):
        return i.user == ctx.author and i.message.id == color_msg.id
    try:
        await bot.wait_for("interaction", timeout=120, check=color_check)
    except asyncio.TimeoutError:
        await ctx.reply("⌛ You took too long to select a color. Operation cancelled.", mention_author=True)
        return

    # 5. Channel select dropdown
    guild = ctx.guild
    channels = [c for c in guild.text_channels if c.permissions_for(guild.me).send_messages]
    if not channels:
        await ctx.reply("❌ No channels available where I can send messages.", mention_author=True)
        return

    view = View()
    channel_select = ChannelSelect(embed_data, channels)
    view.add_item(channel_select)
    channel_msg = await ctx.reply("Select the **target channel** to send the embed:", view=view, mention_author=True)

    def channel_check(i):
        return i.user == ctx.author and i.message.id == channel_msg.id
    try:
        await bot.wait_for("interaction", timeout=120, check=channel_check)
    except asyncio.TimeoutError:
        await ctx.reply("⌛ You took too long to select a channel. Operation cancelled.", mention_author=True)
        return

    # 6. Send embed
    channel = guild.get_channel(embed_data["channel"])
    if channel is None:
        await ctx.reply("❌ Invalid channel selected.", mention_author=True)
        return

    embed = discord.Embed(
        title=embed_data["title"],
        description=embed_data["description"],
        color=color_map.get(embed_data["color"], discord.Color.default()),
    )

    if embed_data["footer"]:
        embed.set_footer(text=embed_data["footer"])

    try:
        await channel.send(embed=embed)
        await ctx.reply(f"✅ Embed sent to {channel.mention}!", mention_author=True)

        # 7. Logging to #administration-logs with field truncation
        log_channel = discord.utils.get(guild.text_channels, name=LOG_CHANNEL_NAME)
        if log_channel:
            log_embed = discord.Embed(
                title="📢 Embed Sent",
                description=f"Sent by: {ctx.author.mention} ({ctx.author.id})\n"
                            f"Sent to: {channel.mention}\n"
                            f"Time: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC",
                color=discord.Color.orange()
            )
            log_embed.add_field(name="Embed Title", value=truncate_field(embed_data["title"]), inline=False)
            log_embed.add_field(name="Embed Description", value=truncate_field(embed_data["description"]), inline=False)
            log_embed.add_field(name="Embed Footer", value=truncate_field(embed_data["footer"]), inline=False)
            log_embed.add_field(name="Embed Color", value=embed_data["color"], inline=False)
            log_embed.set_footer(text="Embed Logging System")

            try:
                await log_channel.send(embed=log_embed)
            except discord.HTTPException as e:
                print(f"❌ Failed to send log embed: {e}")

    except Exception as e:
        await ctx.reply(f"❌ Failed to send embed: {e}", mention_author=True)

@bot.event
async def on_ready():
    print(f"✅ Logged in as {BOT_NAME} ({bot.user})")

async def run_bot():
    await bot.start(TOKEN)

if __name__ == "__main__":
    asyncio.run(run_bot())

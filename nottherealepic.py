import os
import sys
import time
import random
import logging
import re
import unicodedata
from collections import defaultdict
from discord import app_commands, Interaction
from datetime import datetime, timedelta
from threading import Thread

import discord
from discord.ext import commands, tasks
from discord import app_commands, Embed


# Your imported data modules (make sure these are correct)
from files import files_data
from pro_file_info import pro_file_info
from paid_id import paid_id_data
from licence import license_descriptions

# ----------- Setup Logging (Better than print for production) -----------

logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)


statuses = [
    "Playing GTA 6 — don't ask.",
    "Modding GTA like it's a career.",
    "ZModeler: cracked, patched, broken again.",
    "Scripting when I feel like it.",
    "Helping, but not politely.",
    "Banning you next, probably.",
    "Still fixing mods I didn’t break.",
    "GTA physics? Not my fault.",
    "Running Discord like a back alley shop.",
    "Support open — patience closed.",
    "ZModeler and I have beef.",
    "If it's broken, blame the dev.",
    "Custom cars, broken dreams.",
    "GTA garage — open, underpaid.",
    "Debugging one crash at a time.",
    "Reading logs like tarot cards.",
    "Updates? Maybe. Attitude? Always.",
    "Discord mod — not your therapist.",
    "This isn't a helpdesk. Kind of is.",
    "Yes, I’m Batman. No, I won’t fix it.",
    "Fixing what Rockstar couldn’t.",
    "No promises. Only patches.",
    "Your bug, my weekend.",
    "Helping people I lowkey dislike.",
    "I mod. I ban. I vanish.",
    "Welcome to tech support, now cry.",
    "5M server? Depends on my mood.",
    "Writing code that probably works.",
    "Lurking in logs, judging silently.",
    "Less talk, more fixing.",
]

user_activity = {}
TARGET_ROLE_NAME = "LEGIT"
BAN_DURATION_DAYS = 30
TIME_LIMIT_MINUTES = 180

user_message_tracker = defaultdict(list)

def normalize_text(text):
    return unicodedata.normalize('NFKD', text).encode('ascii', 'ignore').decode('ascii').lower()

bad_words = [
    # NSFW and explicit
    "free nitro", "free nude", "free nsfw", "nude", "fuck", "sex", "onlyfans",
    "private video", "click here", "join now", "snapchat nude",

    # Game & giveaway scams (refined to avoid false positives)
    "free steam", "steam giveaway", "steam gift", "free robux", "free vbucks",
    "free uc", "nitro drop", "claim nitro", "steam drop", "roblox code",
    "fortnite free", "cod points free", "valorant points free", "valorant free skin",

    # Suspicious domains / shortened URLs
    "discordnitro", "discord-airdrop", "steamcommunity", "steampowered",
    "nft-airdrop", "airdrop claim", "verify here", "free-key", "account-free",
    "giveaway-bot", "nitro-bot", "claim gift", "verify to claim",

    # Obvious bait / triggers
    "@everyone free", "@here get", ":gift:", ":tada:", ":gem:", ":moneybag:",
    "u.to/", "bit.ly/", "tinyurl.com/", "rb.gy/", "t.co/", "gg.gg/",
    "discord-",          # e.g. discord-airdrop.com
    "discordnitro.",     # e.g. discordnitro.gift
    "discord.giveaway",  # e.g. discord.giveawayevent.site
    "discordgift.",      # e.g. discordgift.codes
    "d1scord.",          # typo style
    "discorcl.",         # fake 'L' instead of 'd'

    "steamcommunity-",   # e.g. steamcommunity-offer.site
    "steamgift.",        # e.g. steamgiftdrop.com
    "steampowered-",     # e.g. steampowered-bonus.net
    "steamdrop.",        # e.g. steamdrop.shop
    "steamn1tro.",       # steam with nitro bait

    "epicgames-",        # e.g. epicgames-prize.store
    "epic-drop.",        # e.g. epic-drop.gg

    "roblox-",           # e.g. roblox-reward.tk
    "fortnite-",         # e.g. fortnite-code.online
    "valorant-",         # e.g. valorant-points.click

    "nitro-",            # nitro-gift.xyz
    "nitr0-",            # using zero
    "airdrop-",          # airdrop-nitro.store
    "verify-",           # verify-nitro.link
    "login-",            # login-steam.xyz
    "secure-",           # secure-discordlogin.com
    "giveaway-",         # giveaway-discord.tech
]



# ----------- Cooldown Check to Avoid Rapid Restarts -----------

def check_restart_limit():
    path = "last_restart.txt"
    current_time = time.time()

    if os.path.exists(path):
        with open(path, "r") as f:
            last_time = float(f.read().strip())
        if current_time - last_time < 1200:  # 20 minutes cooldown
            logging.error("⛔ Too soon to restart. Exiting to avoid rate-limit.")
            sys.exit()

    with open(path, "w") as f:
        f.write(str(current_time))
    logging.info("✅ Passed cooldown check. Starting bot.")

check_restart_limit()

# ----------- Utility Functions -----------

def generate_code():
    """Generate unique 8-char alphanumeric code like epic0001."""
    random_number = random.randint(1, 9999)
    return f"epic{random_number:04d}"

def check_code_exists(code: str) -> bool:
    if os.path.exists("generated_codes.txt"):
        with open("generated_codes.txt", "r") as file:
            codes = [line.strip() for line in file.readlines()]
            return code in codes
    return False
# --- CONFIG ---  
LEGIT_REACTION_CHANNEL_ID = 1233843778754838679  # Channel where embed will be sent
LEGIT_REACTION_ROLE_ID = 1232213167480901713  # Role to give on reaction
LEGIT_REACTION_EMOJI = "✅"  # Emoji to react with
LEGIT_REACTION_GIF_URL = "https://cdn.discordapp.com/attachments/1233831270866227271/1404083666791039079/nre_animated_low_mb.gif?ex=6899e650&is=689894d0&hm=d6cab030fec1bb426d9dc396f13efafacee9bac8dd60ecaee76f4301a2ca97ab&"  # Your GIF link
LEGIT_REACTION_MESSAGE_ID = 1404085986098413640  # Existing message ID to edit
# ---------------

# ----------- Discord Bot Setup -----------
intents = discord.Intents.default()
intents.message_content = True  # Required for commands reading message content
intents.guilds = True
intents.members = True
intents.reactions = True
bot = commands.Bot(command_prefix="!", intents=intents)
tree = bot.tree

# ----------- Uptime Tracking -----------

start_time = datetime.utcnow()

# Channel ID where uptime embed will be posted (change this)
UPTIME_CHANNEL_ID = 1369435929604784262  # <-- Replace with your channel ID

# Message ID for uptime embed, will be set after first send
status_message_id = None

# ----------- Autocomplete Functions -----------

async def model_autocomplete(interaction: discord.Interaction, current: str):
    choices = [
        app_commands.Choice(name=model, value=model)
        for model in files_data if current.lower() in model.lower()
    ][:25]
    return choices

async def code_autocomplete(interaction: discord.Interaction, current: str):
    choices = [
        app_commands.Choice(name=code, value=code)
        for code in paid_id_data if current.lower() in code.lower()
    ][:25]
    return choices

async def fid_autocomplete(interaction: discord.Interaction, current: str):
    choices = [
        app_commands.Choice(name=fid, value=fid)
        for fid in pro_file_info if current.lower() in fid.lower()
    ][:25]
    return choices

# ----------- Commands -----------

@tree.command(
    name="pass",
    description="Get info & password for Mod file",
    guilds=[discord.Object(id=1232208366735196283), discord.Object(id=1358758393300648126)]
)
@app_commands.describe(modelname="File")
@app_commands.autocomplete(modelname=model_autocomplete)
@app_commands.checks.has_role("LEGIT")
@app_commands.checks.cooldown(1, 10.0, key=lambda i: i.user.id)
async def pass_command(interaction: discord.Interaction, modelname: str):
    if modelname not in files_data:
        await interaction.response.send_message("Model not found!", ephemeral=True)
        return

    data = files_data[modelname]
    license_desc = license_descriptions.get(data["license"], "No description available.")

    embed = Embed(title=f"Access: {modelname}", color=0x2ecc71)
    embed.add_field(name="```|``` FILE NAME", value=f"```{modelname}```", inline=False)
    embed.add_field(name="```|``` FILE SIZE", value=f"```{data['size']}```", inline=True)
    embed.add_field(name="```|``` VERSION", value=f"```{data['version']}```", inline=True)
    embed.add_field(name="```|``` FOR", value=f"```{data['for']}```", inline=True)
    embed.add_field(name="```|``` LAST UPDATE", value=f"```{data['last_update']}```", inline=True)
    embed.add_field(name="```|``` LICENSE", value=f"```{data['license']}```", inline=True)
    embed.add_field(name="```|``` LICENSE DETAILS", value=f"```{license_desc}```", inline=False)
    embed.add_field(name="```|``` PASSWORD", value=f"```{data['password']}```", inline=False)

    await interaction.response.send_message(embed=embed, ephemeral=True)

@pass_command.error
async def pass_command_error(interaction: discord.Interaction, error):
    if isinstance(error, app_commands.errors.MissingRole):
        await interaction.response.send_message(
            "Access denied. Verify in <#1233843778754838679> to continue.", ephemeral=True
        )
    else:
        logging.error(f"Error in pass_command: {error}")

@tree.command(
    name="code",
    description="Generate code",
    guild=discord.Object(id=1232208366735196283)
)
@app_commands.default_permissions(administrator=True)
@app_commands.checks.has_role("ROOT")
@app_commands.checks.cooldown(1, 10.0, key=lambda i: i.user.id)
async def code_command(interaction: discord.Interaction):
    await interaction.response.defer(thinking=True)
    new_code = None
    for _ in range(100):
        candidate = generate_code()
        if not check_code_exists(candidate):
            new_code = candidate
            break

    if new_code is None:
        await interaction.followup.send("Failed to generate a unique code. Try again later.")
        return

    if not os.path.exists("generated_codes.txt"):
        with open("generated_codes.txt", "w"): pass

    with open("generated_codes.txt", "a") as f:
        f.write(f"{new_code}\n")

    logging.info(f"Code generated and saved: {new_code}")
    await interaction.followup.send(f"Generated Code: {new_code}")

@code_command.error
async def code_error(interaction: discord.Interaction, error):
    if isinstance(error, app_commands.errors.MissingRole):
        await interaction.response.send_message("You do not have permission to use this command.", ephemeral=True)
    else:
        logging.error(f"Error in code_command: {error}")
        await interaction.response.send_message(f"An error occurred: {error}", ephemeral=True)

@tree.command(
    name="paid_id",
    description="Customer info",
    guild=discord.Object(id=1232208366735196283)
)
@app_commands.default_permissions(administrator=True)
@app_commands.checks.has_role("ROOT")
@app_commands.describe(code="Enter the customer's code")
@app_commands.autocomplete(code=code_autocomplete)
@app_commands.checks.cooldown(1, 10.0, key=lambda i: i.user.id)
async def paid_id_command(interaction: discord.Interaction, code: str):
    try:
        await interaction.response.defer(thinking=True)

        if code not in paid_id_data:
            await interaction.edit_original_response(content="Code not found")
            return

        data = paid_id_data[code]

        embed = Embed(title=f"Access: {code}", color=0x2ecc71)
        embed.add_field(name="```|``` DISCORD ID", value=f"```{data['Discord_id']}```", inline=False)
        embed.add_field(name="```|``` FILE NAME", value=f"```{data['File_Name']}```", inline=False)
        embed.add_field(name="```|``` FOR", value=f"```{data['For_']}```", inline=True)
        embed.add_field(name="```|``` DATE", value=f"```{data['Date']}```", inline=True)
        embed.add_field(name="```|``` EMAIL", value=f"```{data['Email']}```", inline=False)
        embed.add_field(name="```|``` PAYMENT VIA", value=f"```{data['Via']}```", inline=True)
        embed.add_field(name="```|``` OTHER CODE", value=f"```{data['Othr']}```", inline=True)

        await interaction.edit_original_response(embed=embed)

    except Exception as e:
        logging.error(f"Error in paid_id_command: {e}")
        await interaction.edit_original_response(content=f"Error: {e}")

@paid_id_command.error
async def paid_id_error(interaction: discord.Interaction, error):
    if isinstance(error, app_commands.errors.MissingRole):
        await interaction.response.send_message("You do not have permission to use this command.", ephemeral=True)
    else:
        logging.error(f"Error in paid_id_command: {error}")

@tree.command(
    name="proinfo",
    description="Get info about paid files",
    guild=discord.Object(id=1232208366735196283)
)
@app_commands.checks.has_role("LEGIT")  # Only LEGIT role can use
@app_commands.describe(fid="Enter the file ID (select from list)")
@app_commands.autocomplete(fid=fid_autocomplete)
async def proinfo_command(interaction: discord.Interaction, fid: str):
    try:
        # Check if in correct category (REPLACE WITH YOUR CATEGORY ID)
        REQUIRED_CATEGORY_ID = 1369408086967844924
        if interaction.channel.category_id != REQUIRED_CATEGORY_ID:
            await interaction.response.send_message(
                "❌ This command only works in the PROFILES category!",
                ephemeral=True
            )
            return

        # Check if file exists
        if fid not in pro_file_info:
            await interaction.response.send_message(
                "❌ File not found in database!",
                ephemeral=True
            )
            return

        # Get the file data
        data = pro_file_info[fid]

        # Send each part sequentially but as separate messages
        await interaction.response.defer(ephemeral=True)  # Initial defer
        
        # Send FIRST if exists
        if 'FIRST' in data and data['FIRST']:
            await interaction.followup.send(data['FIRST'], ephemeral=False)
        
        # Send SEC if exists
        if 'SEC' in data and data['SEC']:
            await interaction.followup.send(data['SEC'], ephemeral=False)
        
        # Send THIRD if exists
        if 'THIRD' in data and data['THIRD']:
            await interaction.followup.send(data['THIRD'], ephemeral=False)
        
        # Send FOUR if exists
        if 'FOUR' in data and data['FOUR']:
            await interaction.followup.send(data['FOUR'], ephemeral=False)

    except Exception as e:
        logging.error(f"Error in /proinfo: {str(e)}")
        await interaction.followup.send(
            "⚠️ An error occurred while processing your request",
            ephemeral=True
        )



@tree.command(
    name="spread",
    description="Send a message to a specific channel by ID",
    guild=discord.Object(id=1232208366735196283)
)
@app_commands.describe(channel_id="The ID of the channel", message="Message to send")
@app_commands.default_permissions(administrator=True)
@app_commands.checks.has_role("ROOT")  # Optional: permission check
@app_commands.checks.cooldown(1, 5.0, key=lambda i: i.user.id)
async def spread(interaction: discord.Interaction, channel_id: str, message: str):
    try:
        channel = bot.get_channel(int(channel_id))
        if channel:
            await channel.send(message)
            await interaction.response.send_message(f"✅ Message sent to {channel.mention}", ephemeral=True)
        else:
            await interaction.response.send_message("❌ Channel not found.", ephemeral=True)
    except Exception as e:
        logging.error(f"Error in /spread: {e}")
        await interaction.response.send_message("⚠️ Failed to send message.", ephemeral=True)

@tree.command(
    name="epicembed",
    description="Send an embed message to a specific channel by ID",
    guild=discord.Object(id=1232208366735196283)
)
@app_commands.describe(
    channel_id="The ID of the channel",
    title="Embed title (optional)",
    description="Embed description",
    color="Embed color in HEX (e.g. #3498db, optional)"
)
@app_commands.default_permissions(administrator=True)
@app_commands.checks.has_role("ROOT")
@app_commands.checks.cooldown(1, 5.0, key=lambda i: i.user.id)
async def epicembed(
    interaction: discord.Interaction,
    channel_id: str,
    description: str,
    title: str = None,
    color: str = "#3498db"
):
    try:
        channel = bot.get_channel(int(channel_id))
        if not channel:
            await interaction.response.send_message("❌ Channel not found.", ephemeral=True)
            return
        
        # Parse color hex code, default to blue if invalid
        try:
            color_value = int(color.lstrip("#"), 16)
            embed_color = discord.Color(color_value)
        except:
            embed_color = discord.Color.blue()
        
        embed = discord.Embed(title=title, description=description, color=embed_color)
        await channel.send(embed=embed)
        
        await interaction.response.send_message(f"✅ Embed sent to {channel.mention}", ephemeral=True)
    except Exception as e:
        logging.error(f"Error in /epicembed: {e}")
        await interaction.response.send_message("⚠️ Failed to send embed.", ephemeral=True)

@tree.command(
    name="paymentxx",
    description="Send purchase confirmation to order ticket and DM",
    guilds=[discord.Object(id=1232208366735196283), discord.Object(id=1358758393300648126)]
)
@app_commands.describe(
    channelid="Order ticket channel ID",
    userid="User ID of the buyer",
    spawncode="Spawn code of the buyer"
)
@app_commands.default_permissions(administrator=True)
@app_commands.checks.has_role("ROOT")
@app_commands.checks.cooldown(1, 10.0, key=lambda i: i.user.id)
async def paymentxx(interaction: Interaction, channelid: str, userid: str, spawncode: str):
    try:
        target_channel = await interaction.client.fetch_channel(int(channelid))
        buyer = await interaction.client.fetch_user(int(userid))

        message = (
            f"{buyer.mention}\n"
            f"Thanks for your purchase! \n"
            f"If you need support or future updates, please open a ticket in <#1240335393686290514>.\n"
            f"Make sure to **mention your spawn code** (`{spawncode}`) clearly so we can assist you faster.\n\n"
            f"You may now close this order ticket.\n"
            f"— NOTTHEREALEPIC Team"
        )

        # ✅ Send in ticket/order channel
        await target_channel.send(message)

        # ✅ Send in user's DM
        try:
            await buyer.send(
                f"✅ **Your purchase is confirmed!**\n\n{message.replace(buyer.mention, 'You')}"
            )
        except discord.Forbidden:
            await interaction.followup.send(
                f"⚠️ Could not DM the user ({buyer}) — maybe they have DMs off.",
                ephemeral=True
            )

        await interaction.response.send_message("✅ Payment message sent to channel and DM!", ephemeral=True)

    except Exception as e:
        logging.error(f"Error in /paymentxx: {e}")
        await interaction.response.send_message(f"❌ Error: {e}", ephemeral=True)

@paymentxx.error
async def paymentxx_error(interaction: Interaction, error):
    if isinstance(error, app_commands.errors.MissingRole):
        await interaction.response.send_message(
            "Access denied. Verify in <#1233843778754838679> to continue.", ephemeral=True
        )
    else:
        logging.error(f"Error in paymentxx: {error}")
        await interaction.response.send_message("An error occurred while executing the command.", ephemeral=True)


@tree.command(
    name="warntt",
    description="Send purchase confirmation to order ticket and DM",
    guilds=[discord.Object(id=1232208366735196283), discord.Object(id=1358758393300648126)]
)
@app_commands.describe(
    channelid="Order ticket channel ID",
    userid="User ID of the buyer"
)
@app_commands.default_permissions(administrator=True)
@app_commands.checks.has_role("ROOT")
@app_commands.checks.cooldown(1, 10.0, key=lambda i: i.user.id)
async def warntt(interaction: Interaction, channelid: str, userid: str):
    try:
        await interaction.response.defer(ephemeral=True)

        target_channel = await interaction.client.fetch_channel(int(channelid))
        buyer = await interaction.client.fetch_user(int(userid))

        message = (
            f"## Ticket Inactivity Warning\n"
            f"Hy {buyer.mention}! \n"
            f"This ticket will automatically close if there is no response within the next 3 hours. \n"
            f"If you still need help, please reply here to keep the ticket open."
            f"If your issue is resolved, feel free to close the ticket using the appropriate button or command.\n\n"
            f"Thank you for understanding!\n"
            f"— NOTTHEREALEPIC Team"
        )

        # ✅ Send in ticket/order channel
        await target_channel.send(message)

        # ✅ Send in user's DM
        try:
            await buyer.send(
                f"## Ticket Inactivity Warning\n"
                f"Hy {buyer.mention}! \n"
                f"This ticket will automatically close if there is no response within the next 3 hours. \n"
                f"If you still need help, please reply here to keep the ticket open."
                f"If your issue is resolved, feel free to close the ticket using the appropriate button or command.\n\n"
                f"Thank you for understanding!\n"
                f"— NOTTHEREALEPIC Team"
            )
        except discord.Forbidden:
            await interaction.followup.send(
                f"⚠️ Could not DM the user ({buyer}) — maybe they have DMs off.",
                ephemeral=True
            )

        await interaction.response.send_message("✅ warn message sent to channel and DM!", ephemeral=True)

    except Exception as e:
        logging.error(f"Error in /warntt: {e}")
        await interaction.response.send_message(f"❌ Error: {e}", ephemeral=True)

@warntt.error
async def warntt_error(interaction: Interaction, error):
    if isinstance(error, app_commands.errors.MissingRole):
        await interaction.response.send_message(
            "Access denied. Verify in <#1233843778754838679> to continue.", ephemeral=True
        )
    else:
        logging.error(f"Error in warntt: {error}")
        await interaction.response.send_message("An error occurred while executing the command.", ephemeral=True)


@tasks.loop(seconds=50)
async def update_uptime_embed():
    try:
        channel = bot.get_channel(1391327447764435005)
        if not channel:
            logging.warning("⚠️ Uptime channel not found.")
            return

        message = await channel.fetch_message(1391327711926157463)
        if not message:
            logging.warning("⚠️ Uptime message not found.")
            return

        now_utc = datetime.utcnow()
        now_ist = now_utc + timedelta(hours=5, minutes=30)
        uptime = now_utc - start_time

        days, rem = divmod(int(uptime.total_seconds()), 86400)
        hours, rem = divmod(rem, 3600)
        minutes, seconds = divmod(rem, 60)
        uptime_str = f"{days:02}:{hours:02}:{minutes:02}:{seconds:02}"

        embed = discord.Embed(
            title="NOTTHEREALEPIC BOT",
            color=discord.Color.green()
        )
        embed.add_field(name="STATUS", value="```ONLINE```", inline=True)
        embed.add_field(name="START", value=f"```{start_time + timedelta(hours=5, minutes=30):%I:%M %p} IST```", inline=True)
        embed.add_field(name="UPTIME", value=f"```{uptime_str}```", inline=True)
        embed.add_field(name="LAST UPDATED", value=f"```{now_ist:%H:%M:%S} IST```", inline=True)
        embed.set_footer(text="Auto-updated every 50s")

        await message.edit(embed=embed)

    except Exception as e:
        logging.error(f"⚠️ Failed to update uptime embed: {e}")

# ✅ Role/admin check
def is_admin_or_mod(interaction: discord.Interaction):
    if interaction.user.guild_permissions.administrator:
        return True
    allowed_roles = ["ROOT", "MOD"]
    user_roles = [role.name.upper() for role in interaction.user.roles]
    return any(role in user_roles for role in allowed_roles)

# ✅ Slash command: /dm
@bot.tree.command(
    name="dm",
    description="Send a DM to a user by their ID",
    guilds=[discord.Object(id=1232208366735196283)]  # <-- your server ID here
)
@app_commands.check(is_admin_or_mod)
@app_commands.describe(userid="User ID to DM", message="Message (use \\n for newlines)")
async def dm(interaction: discord.Interaction, userid: str, message: str):
    await interaction.response.defer(ephemeral=True)
    try:
        user = await bot.fetch_user(int(userid))
        text = message.replace("\\n", "\n")
        await user.send(text)
        await interaction.followup.send(f"✅ DM sent to <@{userid}>.")
    except Exception as e:
        await interaction.followup.send(f"❌ Failed: `{e}`")

# ✅ Error handler
@dm.error
async def dm_error(interaction: discord.Interaction, error):
    if isinstance(error, app_commands.CheckFailure):
        await interaction.response.send_message("❌ You don't have permission.", ephemeral=True)

# ----------- Events -----------


@bot.event
async def on_message(message):
    if message.author.bot:
        return

    now = datetime.utcnow()
    norm_content = normalize_text(message.content)

    # Track per-user message data
    user_id = message.author.id
    user_message_tracker[user_id].append((norm_content, now, message.guild.id))

    # Keep only recent messages (last 10 mins)
    user_message_tracker[user_id] = [
        (msg, t, gid) for msg, t, gid in user_message_tracker[user_id]
        if now - t < timedelta(minutes=10)
    ]

    # Multi-server spam check
    same_msg_count = sum(1 for msg, _, _ in user_message_tracker[user_id] if msg == norm_content)
    unique_guilds = {gid for msg, _, gid in user_message_tracker[user_id] if msg == norm_content}

    # Condition 1: Same message in 5+ servers in 10 minutes
    if len(unique_guilds) >= 5:
        try:
            await message.delete()
            await message.author.timeout(timedelta(hours=24), reason="⚠️ Multi-server spam")
            print(f"⛔ {message.author} timed out for multi-server spam.")
        except Exception as e:
            print(f"Error: {e}")
        return

    # Condition 2 & 3: NSFW keyword detection in any font
    if any(word in norm_content for word in bad_words):
        try:
            await message.delete()
            await message.author.timeout(timedelta(hours=12), reason="⚠️ NSFW/Scam content")
            print(f"⚠️ {message.author} timed out for NSFW word.")
        except Exception as e:
            print(f"Error: {e}")
        return

    await bot.process_commands(message)



@bot.event
async def on_ready():
    logging.info(f"Logged in as {bot.user} (ID: {bot.user.id})")
    logging.info("------")
    try:
        guild = discord.Object(id=1232208366735196283)
        synced = await tree.sync(guild=guild)  # Only guild sync
        logging.info(f"Synced {len(synced)} commands.")
    except Exception as e:
        logging.error(f"Error syncing commands: {e}")
    change_status.start()
    update_uptime_embed.start()
    channel = bot.get_channel(LEGIT_REACTION_CHANNEL_ID)
    if not channel:
        print("❌ Channel not found.")
        return

    try:
        msg = await channel.fetch_message(LEGIT_REACTION_MESSAGE_ID)

        embed = discord.Embed(
            title="🎯 Get Verified Access",
            description=f"React with {LEGIT_REACTION_EMOJI} to get the **Legit** role.\nOnce given, your role will stay forever.",
            color=discord.Color.red()
        )
        embed.set_image(url=LEGIT_REACTION_GIF_URL)
        embed.set_footer(text="Server Security • Auto-Verification", icon_url=bot.user.display_avatar.url)

        await msg.edit(embed=embed)  # Edit instead of sending new
        await msg.clear_reactions()
        await msg.add_reaction(LEGIT_REACTION_EMOJI)

        print(f"📌 Updated existing reaction role message (ID: {LEGIT_REACTION_MESSAGE_ID})")

    except discord.NotFound:
        print("❌ Message not found. Check MESSAGE_ID.")

@bot.event
async def on_raw_reaction_add(payload):
    if payload.channel_id == LEGIT_REACTION_CHANNEL_ID and payload.message_id == LEGIT_REACTION_MESSAGE_ID and str(payload.emoji) == LEGIT_REACTION_EMOJI and not payload.member.bot:
        guild = bot.get_guild(payload.guild_id)
        role = guild.get_role(LEGIT_REACTION_ROLE_ID)
        member = payload.member
        channel = guild.get_channel(payload.channel_id)
        message = await channel.fetch_message(payload.message_id)

        if role and member and role not in member.roles:
            await member.add_roles(role)
            try:
                await member.send(f"✅ You have been verified with the **{role.name}** role.")
            except discord.Forbidden:
                pass

        # Remove reaction to keep count at 1
        await message.remove_reaction(payload.emoji, member)

# No removal event → role stays forever


@tasks.loop(seconds=30)  
async def change_status():
    chosen_status = random.choice(statuses)
    activity = discord.Activity(type=discord.ActivityType.playing, name=chosen_status)
    await bot.change_presence(status=discord.Status.online, activity=activity)

@bot.event
async def on_app_command_error(interaction: discord.Interaction, error):
    if isinstance(error, app_commands.CommandOnCooldown):
        await interaction.response.send_message(
            f"Slow down! Try again in {error.retry_after:.2f} seconds.", ephemeral=True
        )
    else:
        logging.error(f"Unhandled app command error: {error}")

@bot.event
async def on_member_join(member):
    user_activity[member.id] = {"joined": datetime.utcnow(), "got_role": False}
    try:
        await member.send("Thank you for joining the server!")
        print(f"Sent welcome DM to {member}")
    except Exception as e:
        print(f"Failed to send DM: {e}")

@bot.event
async def on_member_update(before, after):
    if not user_activity.get(after.id):
        return
    before_roles = set(before.roles)
    after_roles = set(after.roles)
    for role in after.roles:
        if role.name == TARGET_ROLE_NAME and role not in before_roles:
            user_activity[after.id]["got_role"] = True

@bot.event
async def on_member_remove(member: discord.Member):
    activity = user_activity.get(member.id)
    if not activity:
        return

    # Store the user's ID and name now, as the member object will become less useful
    user_id = member.id
    user_name = str(member)

    try:
        if activity["got_role"]:
            # Use timezone-aware datetime for more accurate comparisons
            time_spent = datetime.now(timezone.utc) - activity["joined"]

            if time_spent < timedelta(minutes=TIME_LIMIT_MINUTES):
                # --- BAN LOGIC ---
                try:
                    await member.guild.ban(
                        discord.Object(id=user_id), # Use discord.Object for reliability
                        reason="Auto-ban: Accessed a protected role and left the server shortly after.",
                        delete_message_days=0
                    )
                    print(f"Successfully banned {user_name} ({user_id}).")
                except discord.Forbidden:
                    print(f"Could not ban {user_name} ({user_id}). Bot lacks 'Ban Members' permission.")
                    return # Can't continue if ban fails
                except Exception as e:
                    print(f"An unexpected error occurred while trying to ban {user_name}: {e}")
                    return

                # --- DM LOGIC (The Fix) ---
                try:
                    # Fetch the global User object using the ID
                    user = await bot.fetch_user(user_id)

                    # Send a clear ban notification, not a welcome message
                    await user.send(
                        f"Hello {user.name},\n\n"
                        "You have been automatically banned from the **NOTTHEREALEPIC** Discord server. "
                        "Our system detected that you joined, gained a specific role, and left within a very short time frame. "
                        "This action is a security measure to prevent potential abuse.\n\n"
                        "If you believe this was a mistake, you can appeal by contacting the server owner."
                    )
                    print(f"Successfully sent a ban notification DM to {user_name} ({user_id}).")
                except discord.Forbidden:
                    # This is common if the user has DMs disabled or blocked the bot.
                    print(f"Could not DM {user_name} ({user_id}). They may have DMs disabled.")
                except Exception as e:
                    print(f"An unexpected error occurred while trying to DM {user_name}: {e}")
    finally:
        # --- CLEANUP ---
        # This cleanup should happen regardless of the outcome to prevent memory leaks.
        # The 'finally' block ensures this code always runs.
        user_activity.pop(user_id, None)
        print(f"Cleaned up activity tracking for {user_name} ({user_id}).")



# ----------- Main Entrypoint -----------

if __name__ == "__main__":
    # Run the bot
    TOKEN = os.getenv("asmr")  # Or replace with your token string here
    if not TOKEN:
        logging.error("DISCORD_TOKEN environment variable not set!")
        sys.exit(1)

    bot.run(TOKEN)

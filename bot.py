# bot.py
# bot.py

import os
import re
import asyncio
import random
from datetime import datetime, timedelta
from dotenv import load_dotenv
import discord
from discord.ext import commands

load_dotenv()  # loads the .env file

TOKEN = os.getenv("DISCORD_TOKEN")
if not TOKEN:
    raise SystemExit("Environment variable DISCORD_TOKEN is not set. Create a .env file or set the variable.")

# Use explicit intents and enable message content if you need command/message content access
intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)


def parse_time_string(time_str: str) -> int | None:
    """Parse time strings like '1d2h30m10s' or '10m' into seconds.

    Returns seconds or None if unparsable.
    """
    time_str = time_str.strip().lower()
    if time_str.isdigit():
        return int(time_str)

    pattern = r"(?:(\d+)d)?(?:(\d+)h)?(?:(\d+)m)?(?:(\d+)s)?$"
    m = re.match(pattern, time_str)
    if not m:
        return None
    days, hours, minutes, seconds = (g or "0" for g in m.groups())
    total = int(days) * 86400 + int(hours) * 3600 + int(minutes) * 60 + int(seconds)
    return total if total > 0 else None


@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")


@bot.group(name="create", invoke_without_command=True)
async def create_group(ctx: commands.Context):
    await ctx.send("Usage: `!create gw {time} [reward] {winners}`")


@create_group.command(name="gw")
async def create_gw(ctx: commands.Context, *, raw: str):
    """Create a giveaway.

    Command syntax: `!create gw {time} [reward] {winners}`
    Where `time` is first token (like `1h30m`), `winners` is last token (an integer),
    and `reward` is the text in-between (optional).
    """
    # Parse the raw arguments from the message content to preserve spacing
    # raw contains everything after `!create gw ` because of the `*` capture
    tokens = raw.split()
    if len(tokens) < 2:
        await ctx.send("Invalid usage. Example: `!create gw 10m Nitro 2`")
        return

    time_input = tokens[0]
    winners_input = tokens[-1]
    reward = " ".join(tokens[1:-1]) if len(tokens) > 2 else "No reward specified"

    seconds = parse_time_string(time_input)
    if seconds is None:
        await ctx.send("Could not parse the time. Use formats like `1h30m`, `10m`, `2d`, or seconds as a number.")
        return

    try:
        winners = int(winners_input)
        if winners < 1:
            raise ValueError()
    except ValueError:
        await ctx.send("Number of winners must be a positive integer.")
        return

    end_time = datetime.utcnow() + timedelta(seconds=seconds)

    embed = discord.Embed(
        title="🎉 Giveaway! 🎉",
        description=reward,
        color=discord.Color.blurple(),
        timestamp=end_time,
    )
    embed.add_field(name="Host", value=str(ctx.author), inline=True)
    embed.add_field(name="Winners", value=str(winners), inline=True)
    embed.add_field(name="Ends", value=f"<t:{int(end_time.timestamp())}:R>", inline=False)

    try:
        gw_message = await ctx.send(embed=embed)
        await gw_message.add_reaction("🎉")
    except discord.Forbidden:
        await ctx.send("I need permission to send messages and add reactions here.")
        return

    # Wait for the giveaway to end
    await asyncio.sleep(seconds)

    try:
        gw_message = await ctx.channel.fetch_message(gw_message.id)
    except Exception:
        await ctx.send("Could not fetch the giveaway message after the timer ended.")
        return

    reaction = None
    for react in gw_message.reactions:
        if str(react.emoji) == "🎉":
            reaction = react
            break

    if reaction is None:
        await ctx.send("No reactions found; no winners can be chosen.")
        return

    users = []
    try:
        users = [u for u in await reaction.users().flatten() if not u.bot]
    except Exception:
        await ctx.send("Failed to retrieve reaction users.")
        return

    if not users:
        await ctx.send("No valid participants, nobody entered the giveaway.")
        return

    if len(users) <= winners:
        chosen = users
    else:
        chosen = random.sample(users, k=winners)

    winners_mentions = ", ".join(u.mention for u in chosen)
    result_embed = discord.Embed(
        title="🎊 Giveaway Ended 🎊",
        description=f"Prize: {reward}\nWinners: {winners_mentions}",
        color=discord.Color.green(),
    )

    await ctx.send(content=f"Congratulations {winners_mentions}!", embed=result_embed)

# ------------------ Economy Commands ------------------
import json
from pathlib import Path
from typing import Dict, Any

DAILY_AMOUNT = 100
DAILY_COOLDOWN = 86400  # 24 hours
PET_COOLDOWN = 1800  # 30 minutes
WORK_COOLDOWN = 3600  # 1 hour
SNUGGLE_COOLDOWN = 3600  # 1 hour

DATA_FILE = Path("economy.json")
_data_lock = asyncio.Lock()


def _read_data() -> Dict[str, Any]:
    if not DATA_FILE.exists():
        return {}
    try:
        with DATA_FILE.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _write_data(data: Dict[str, Any]) -> None:
    with DATA_FILE.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _ensure_user_record(data: Dict[str, Any], user_id: int) -> Dict[str, Any]:
    key = str(user_id)
    if key not in data:
        data[key] = {
            "balance": 0,
            "last_daily": 0,
            "last_pet": 0,
            "last_work": 0,
            "last_snuggle": 0,
        }
    return data[key]


def _format_seconds(sec: int) -> str:
    m, s = divmod(sec, 60)
    h, m = divmod(m, 60)
    parts = []
    if h:
        parts.append(f"{h}h")
    if m:
        parts.append(f"{m}m")
    if s or not parts:
        parts.append(f"{s}s")
    return " ".join(parts)


@bot.command(name="bal")
async def balance_cmd(ctx: commands.Context, member: discord.Member | None = None):
    member = member or ctx.author
    async with _data_lock:
        data = _read_data()
        record = _ensure_user_record(data, member.id)
    embed = discord.Embed(
        title=f"{member.display_name}'s Balance",
        description=f"💰 {record['balance']} coins",
        color=discord.Color.gold(),
    )
    await ctx.send(embed=embed)


@bot.command(name="daily")
async def daily_cmd(ctx: commands.Context):
    uid = ctx.author.id
    now = int(datetime.utcnow().timestamp())
    async with _data_lock:
        data = _read_data()
        rec = _ensure_user_record(data, uid)
        last = int(rec.get("last_daily", 0))
        if now - last < DAILY_COOLDOWN:
            remaining = DAILY_COOLDOWN - (now - last)
            await ctx.send(f"You already claimed daily. Try again in {_format_seconds(remaining)}.")
            return
        rec["balance"] += DAILY_AMOUNT
        rec["last_daily"] = now
        _write_data(data)
    await ctx.send(f"You claimed your daily {DAILY_AMOUNT} coins, {ctx.author.mention}!")


@bot.command(name="pet")
async def pet_cmd(ctx: commands.Context):
    uid = ctx.author.id
    now = int(datetime.utcnow().timestamp())
    reward = random.randint(5, 25)
    async with _data_lock:
        data = _read_data()
        rec = _ensure_user_record(data, uid)
        last = int(rec.get("last_pet", 0))
        if now - last < PET_COOLDOWN:
            remaining = PET_COOLDOWN - (now - last)
            await ctx.send(f"You petted recently. Try again in {_format_seconds(remaining)}.")
            return
        rec["balance"] += reward
        rec["last_pet"] = now
        _write_data(data)
    await ctx.send(f"You pet your pet and earned {reward} coins, {ctx.author.mention}! 🐾")


@bot.command(name="work")
async def work_cmd(ctx: commands.Context):
    uid = ctx.author.id
    now = int(datetime.utcnow().timestamp())
    reward = random.randint(20, 150)
    async with _data_lock:
        data = _read_data()
        rec = _ensure_user_record(data, uid)
        last = int(rec.get("last_work", 0))
        if now - last < WORK_COOLDOWN:
            remaining = WORK_COOLDOWN - (now - last)
            await ctx.send(f"You're tired. Try working again in {_format_seconds(remaining)}.")
            return
        rec["balance"] += reward
        rec["last_work"] = now
        _write_data(data)
    await ctx.send(f"You worked hard and earned {reward} coins, {ctx.author.mention}! 💼")


@bot.command(name="snuggle")
async def snuggle_cmd(ctx: commands.Context, member: discord.Member | None = None):
    if member is None:
        await ctx.send("Usage: `!snuggle @user` — mention someone to snuggle.")
        return
    if member.id == ctx.author.id:
        await ctx.send("You can't snuggle yourself — find someone cute to snuggle with!")
        return
    uid = ctx.author.id
    now = int(datetime.utcnow().timestamp())
    reward = 10
    async with _data_lock:
        data = _read_data()
        rec_a = _ensure_user_record(data, uid)
        rec_b = _ensure_user_record(data, member.id)
        last = int(rec_a.get("last_snuggle", 0))
        if now - last < SNUGGLE_COOLDOWN:
            remaining = SNUGGLE_COOLDOWN - (now - last)
            await ctx.send(f"You snuggled recently. Try again in {_format_seconds(remaining)}.")
            return
        rec_a["balance"] += reward
        rec_b["balance"] += reward
        rec_a["last_snuggle"] = now
        _write_data(data)
    await ctx.send(f"{ctx.author.mention} snuggled {member.mention}! Both received {reward} coins 💞")


@bot.command(name="give")
async def give_cmd(ctx: commands.Context, member: discord.Member, amount: int):
    """Transfer `amount` coins to `member`. Usage: `!give @user 50`"""
    if member.bot:
        await ctx.send("You cannot give coins to bots.")
        return
    if amount <= 0:
        await ctx.send("Amount must be a positive integer.")
        return
    if member.id == ctx.author.id:
        await ctx.send("You can't transfer coins to yourself.")
        return

    async with _data_lock:
        data = _read_data()
        sender = _ensure_user_record(data, ctx.author.id)
        receiver = _ensure_user_record(data, member.id)
        if sender["balance"] < amount:
            await ctx.send(f"Insufficient funds — your balance is {sender['balance']} coins.")
            return
        sender["balance"] -= amount
        receiver["balance"] += amount
        _write_data(data)

    embed = discord.Embed(
        title="Transfer Complete",
        description=f"{ctx.author.mention} gave {member.mention} {amount} coins.",
        color=discord.Color.green(),
    )
    embed.add_field(name="Sender Balance", value=f"{sender['balance']} coins", inline=True)
    embed.add_field(name="Receiver Balance", value=f"{receiver['balance']} coins", inline=True)
    await ctx.send(embed=embed)


# ------------------ Modmail (very basic) ------------------
# Behavior:
# - Users DM the bot to open a modmail thread; the bot forwards the DM to a configured `MODMAIL_CHANNEL_ID`.
# - Moderators can reply with `!reply <user_id> <message>` to send a DM back.
# - Moderators can close a thread with `!close <user_id>` which sends a closing message to the user.

MODMAIL_CHANNEL_ID = int(os.getenv("MODMAIL_CHANNEL_ID")) if os.getenv("MODMAIL_CHANNEL_ID") else None


async def _forward_dm_to_mods(message: discord.Message):
    """Forward a DM `message` to the configured mod channel, including attachments."""
    if not MODMAIL_CHANNEL_ID:
        return
    channel = bot.get_channel(MODMAIL_CHANNEL_ID)
    if channel is None:
        return
    embed = discord.Embed(
        title="Modmail",
        description=message.content or "(no message content)",
        color=discord.Color.blue(),
        timestamp=datetime.utcnow(),
    )
    embed.add_field(name="From", value=f"{message.author} ({message.author.id})", inline=False)
    await channel.send(embed=embed)

    # Forward attachments (basic: send each attachment as a file)
    for att in message.attachments:
        try:
            file = await att.to_file()
            await channel.send(content=f"Attachment from {message.author} — {att.filename}", file=file)
        except Exception:
            # Fallback: send the attachment URL if file sending fails
            await channel.send(f"Attachment URL: {att.url}")


@bot.event
async def on_message(message: discord.Message):
    # Allow commands to work as normal
    if message.author == bot.user:
        return

    # If it's a DM to the bot, forward to mod channel
    if isinstance(message.channel, discord.DMChannel):
        await _forward_dm_to_mods(message)
        try:
            await message.channel.send("Your message has been forwarded to the moderators. They'll reply here.")
        except Exception:
            pass
        return

    await bot.process_commands(message)


@bot.command(name="reply")
@commands.has_permissions(manage_messages=True)
async def mod_reply(ctx: commands.Context, user_id: int, *, reply_text: str):
    """Reply to a user's modmail thread: `!reply <user_id> message`"""
    try:
        user = await bot.fetch_user(user_id)
        await user.send(reply_text)
        await ctx.send(f"Sent reply to {user.mention}.")
    except Exception as e:
        await ctx.send(f"Failed to send DM: {e}")


@bot.command(name="close")
@commands.has_permissions(manage_messages=True)
async def mod_close(ctx: commands.Context, user_id: int):
    """Close a modmail thread by sending a closing DM to the user."""
    try:
        user = await bot.fetch_user(user_id)
        await user.send("A moderator has closed your modmail thread. If you need more help, open a new message.")
        await ctx.send(f"Closed modmail thread with {user.mention}.")
    except Exception as e:
        await ctx.send(f"Failed to close thread: {e}")


bot.run(TOKEN)

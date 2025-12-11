import discord
from discord.ext import commands
import yt_dlp
from flask import Flask
import threading
import asyncio
import os

TOKEN = os.environ.get("DISCORD_TOKEN")

# -------------------- Flask (keep Render alive) --------------------
app = Flask("")

@app.route("/")
def home():
    return "Bot is running!"

def run():
    app.run(host="0.0.0.0", port=8080)

def keep_alive():
    t = threading.Thread(target=run)
    t.start()

# -------------------- Discord Bot --------------------
intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True
bot = commands.Bot(command_prefix="!", intents=intents)

# yt-dlp setup (better for newer songs)
ytdl_format_options = {
    'format': 'bestaudio[ext=m4a]/bestaudio/best',
    'noplaylist': True,
    'quiet': True,
    'ignoreerrors': True,
    'nocheckcertificate': True,
    'default_search': 'ytsearch',
    'cookiefile': 'cookies.txt',  # <-- your cookies.txt here
}

ffmpeg_options = {
    'options': '-vn -reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5'
}

ytdl = yt_dlp.YoutubeDL(ytdl_format_options)

# Queue per guild
queues = {}  # {guild_id: [song1, song2,...]}

# -------------------- Music Functions --------------------
async def play_next(ctx):
    guild_id = ctx.guild.id
    if queues.get(guild_id):
        song = queues[guild_id].pop(0)

        # Search YouTube
        try:
            info = ytdl.extract_info(f"ytsearch:{song}", download=False)
            entries = info.get("entries") if info else None
            if not entries:
                await ctx.send(f"❌ Could not find a playable version for: {song}")
                return await play_next(ctx)  # try next song

            # Find first playable entry
            url = None
            title = None
            for entry in entries:
                if entry:
                    url = entry.get("url")
                    title = entry.get("title")
                    if url:
                        break
            if not url:
                await ctx.send(f"❌ Could not find a playable version for: {song}")
                return await play_next(ctx)
        except Exception as e:
            await ctx.send(f"⚠️ Error fetching song info: {e}")
            return await play_next(ctx)

        try:
            source = discord.FFmpegPCMAudio(url, **ffmpeg_options)
            ctx.voice_client.play(
                discord.PCMVolumeTransformer(source),
                after=lambda e: asyncio.run_coroutine_threadsafe(play_next(ctx), bot.loop)
            )
            await ctx.send(f"🎶 Now playing: **{title}**")
        except Exception as e:
            await ctx.send(f"⚠️ Error playing {song}: {e}")
            await play_next(ctx)
    else:
        await ctx.send("✅ Queue ended! Add more songs with `!play <song name>`.")

# -------------------- Bot Commands --------------------
@bot.event
async def on_ready():
    print(f"{bot.user} is online!")

@bot.command()
async def join(ctx):
    if ctx.author.voice:
        channel = ctx.author.voice.channel
        if ctx.voice_client:
            await ctx.voice_client.move_to(channel)
        else:
            await channel.connect()
        await ctx.send(f"✅ Joined **{channel.name}**")
    else:
        await ctx.send("❌ You need to be in a voice channel!")

@bot.command()
async def leave(ctx):
    if ctx.voice_client:
        await ctx.voice_client.disconnect()
        queues.pop(ctx.guild.id, None)
        await ctx.send("👋 Left the voice channel!")
    else:
        await ctx.send("❌ I'm not in a voice channel!")

@bot.command()
async def play(ctx, *, song_name):
    guild_id = ctx.guild.id

    if not ctx.voice_client:
        if ctx.author.voice:
            channel = ctx.author.voice.channel
            await channel.connect()
        else:
            return await ctx.send("❌ You're not in a voice channel!")

    if guild_id not in queues:
        queues[guild_id] = []

    queues[guild_id].append(song_name)

    if not ctx.voice_client.is_playing() and len(queues[guild_id]) == 1:
        await play_next(ctx)
    else:
        await ctx.send(f"➕ Added to queue: **{song_name}**")

@bot.command()
async def pause(ctx):
    if ctx.voice_client and ctx.voice_client.is_playing():
        ctx.voice_client.pause()
        await ctx.send("⏸️ Music paused!")
    else:
        await ctx.send("❌ Nothing is playing!")

@bot.command()
async def resume(ctx):
    if ctx.voice_client and ctx.voice_client.is_paused():
        ctx.voice_client.resume()
        await ctx.send("▶️ Music resumed!")
    else:
        await ctx.send("❌ Nothing is paused!")

@bot.command()
async def stop(ctx):
    if ctx.voice_client:
        ctx.voice_client.stop()
        queues[ctx.guild.id] = []
        await ctx.send("⛔ Music stopped and queue cleared!")
    else:
        await ctx.send("❌ Nothing is playing!")

@bot.command()
async def skip(ctx):
    if ctx.voice_client and ctx.voice_client.is_playing():
        ctx.voice_client.stop()
        await ctx.send("⏭️ Skipped current song!")
    else:
        await ctx.send("❌ Nothing is playing!")

# -------------------- Keep bot alive --------------------
keep_alive()
bot.run(TOKEN)

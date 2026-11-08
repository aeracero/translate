import os
import re
import asyncio

import discord
from discord import app_commands
from discord.ext import commands
from deep_translator import GoogleTranslator

TOKEN = os.environ["DISCORD_TOKEN"]

# ひらがな・カタカナ・漢字・半角カナ
JP_RE = re.compile(r"[\u3040-\u30ff\u4e00-\u9fff\uff66-\uff9f]")
EN_RE = re.compile(r"[A-Za-z]")
# 翻訳前に取り除くもの（URL・カスタム絵文字・メンション）
STRIP_RE = re.compile(r"https?://\S+|<a?:\w+:\d+>|<[@#&!]+\d+>")

intents = discord.Intents.default()
intents.message_content = True  # Developer Portal でも有効化が必要
bot = commands.Bot(command_prefix="!", intents=intents)

# 翻訳が有効なチャンネルID（再起動で消えます）
active_channels: set[int] = set()


def detect_direction(text: str):
    """日本語の文字があれば ja→en、なければ英字があれば en→ja。"""
    if JP_RE.search(text):
        return "ja", "en"
    if EN_RE.search(text):
        return "en", "ja"
    return None


def translate(text: str, src: str, tgt: str) -> str:
    return GoogleTranslator(source=src, target=tgt).translate(text[:4900])


group = app_commands.Group(name="translate", description="リアルタイム日英翻訳")


@group.command(name="start", description="このチャンネルで翻訳を開始します")
async def start(interaction: discord.Interaction):
    active_channels.add(interaction.channel_id)
    await interaction.response.send_message("🌐 翻訳を開始しました（日本語⇄英語）")


@group.command(name="stop", description="このチャンネルの翻訳を停止します")
async def stop(interaction: discord.Interaction):
    active_channels.discard(interaction.channel_id)
    await interaction.response.send_message("⏹️ 翻訳を停止しました")


@group.command(name="status", description="翻訳が有効か確認します")
async def status(interaction: discord.Interaction):
    on = interaction.channel_id in active_channels
    await interaction.response.send_message(
        "✅ 有効です" if on else "❌ 無効です", ephemeral=True
    )


bot.tree.add_command(group)


@bot.event
async def on_ready():
    await bot.tree.sync()
    print(f"Logged in as {bot.user}")


@bot.event
async def on_message(message: discord.Message):
    if message.author.bot or message.channel.id not in active_channels:
        return

    text = STRIP_RE.sub("", message.content).strip()
    if not text:
        return

    direction = detect_direction(text)
    if direction is None:
        return
    src, tgt = direction

    try:
        result = await asyncio.to_thread(translate, text, src, tgt)
    except Exception as e:
        print(f"translate error: {e}")
        return

    if not result or result.strip() == text:
        return

    flag = "🇺🇸" if tgt == "en" else "🇯🇵"
    await message.reply(f"{flag} {result}", mention_author=False)


bot.run(TOKEN)

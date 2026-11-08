import os
import re
import asyncio
from functools import lru_cache

import deepl
import discord
from discord import app_commands
from discord.ext import commands

TOKEN = os.environ["DISCORD_TOKEN"]
DEEPL_KEY = os.environ["DEEPL_API_KEY"]  # Free版のキーは末尾が ":fx"

# Free/Pro はキーから自動判別されます
translator = deepl.Translator(DEEPL_KEY)

# ひらがな・カタカナ・漢字・半角カナ
JP_RE = re.compile(r"[\u3040-\u30ff\u4e00-\u9fff\uff66-\uff9f]")
EN_RE = re.compile(r"[A-Za-z]")
# 翻訳前に取り除くもの（URL・カスタム絵文字・メンション）
STRIP_RE = re.compile(r"https?://\S+|<a?:\w+:\d+>|<[@#&!]+\d+>")

intents = discord.Intents.default()
intents.message_content = True  # Developer Portal でも有効化が必要
bot = commands.Bot(command_prefix="!", intents=intents)

# 翻訳が有効なユーザーID（再起動で消えます）
active_users: set[int] = set()


def detect_target(text: str):
    """日本語の文字があれば英語へ、なければ英字があれば日本語へ。"""
    if JP_RE.search(text):
        return "EN-US"
    if EN_RE.search(text):
        return "JA"
    return None


@lru_cache(maxsize=512)  # 同じ文は再リクエストせず文字数を節約
def _deepl(text: str, target: str) -> str:
    result = translator.translate_text(text, target_lang=target)
    return result.text


async def translate(text: str, target: str) -> str:
    return await asyncio.to_thread(_deepl, text, target)


group = app_commands.Group(name="translate", description="リアルタイム日英翻訳")


@group.command(name="start", description="自分の発言の翻訳を開始します")
async def start(interaction: discord.Interaction):
    active_users.add(interaction.user.id)
    await interaction.response.send_message(
        "🌐 あなたの発言の翻訳を開始しました（日本語⇄英語）", ephemeral=True
    )


@group.command(name="stop", description="自分の発言の翻訳を停止します")
async def stop(interaction: discord.Interaction):
    active_users.discard(interaction.user.id)
    await interaction.response.send_message(
        "⏹️ あなたの発言の翻訳を停止しました", ephemeral=True
    )


@group.command(name="status", description="自分の翻訳が有効か確認します")
async def status(interaction: discord.Interaction):
    on = interaction.user.id in active_users
    await interaction.response.send_message(
        "✅ 有効です" if on else "❌ 無効です", ephemeral=True
    )


@group.command(name="usage", description="DeepLの今月の使用文字数を表示します")
async def usage(interaction: discord.Interaction):
    u = await asyncio.to_thread(translator.get_usage)
    c = u.character
    if c.valid:
        pct = c.count / c.limit * 100
        msg = f"📊 {c.count:,} / {c.limit:,} 文字（{pct:.1f}%）"
    else:
        msg = "使用量を取得できませんでした"
    await interaction.response.send_message(msg, ephemeral=True)


bot.tree.add_command(group)


@bot.event
async def on_ready():
    await bot.tree.sync()
    print(f"Logged in as {bot.user}")


@bot.event
async def on_message(message: discord.Message):
    if message.author.bot or message.author.id not in active_users:
        return

    text = STRIP_RE.sub("", message.content).strip()
    if not text:
        return

    target = detect_target(text)
    if target is None:
        return

    try:
        result = await translate(text, target)
    except deepl.QuotaExceededException:
        # 枠は全員共通なので全ユーザーを停止
        await message.channel.send("⚠️ DeepLの今月の無料枠を使い切ったため、翻訳を停止しました。")
        active_users.clear()
        return
    except deepl.DeepLException as e:
        print(f"deepl error: {e}")
        return

    if not result or result.strip() == text:
        return

    flag = "🇺🇸" if target == "EN-US" else "🇯🇵"
    await message.reply(f"{flag} {result}", mention_author=False)


bot.run(TOKEN)

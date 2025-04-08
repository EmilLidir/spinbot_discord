import discord
from discord import app_commands
import asyncio
import os
import websocket
import time
import re
import json
from collections import defaultdict

TOKEN = os.getenv("DISCORD_TOKEN")

rewards = defaultdict(int)

class SpinModal(discord.ui.Modal, title="🎰 SpinBot Eingabe"):
    def __init__(self):
        super().__init__()

        self.username = discord.ui.TextInput(
            label="Benutzername",
            placeholder="Gib deinen Empire-Benutzernamen ein...",
            required=True
        )
        self.password = discord.ui.TextInput(
            label="Passwort",
            placeholder="Gib dein Passwort ein...!!!",
            style=discord.TextStyle.short,
            required=True
        )
        self.spins = discord.ui.TextInput(
            label="Anzahl der Spins",
            placeholder="Wie oft soll das Rad gedreht werden?",
            style=discord.TextStyle.short,
            required=True
        )

        self.add_item(self.username)
        self.add_item(self.password)
        self.add_item(self.spins)

    async def on_submit(self, interaction: discord.Interaction):
        username = self.username.value
        password = self.password.value
        spins = int(self.spins.value)

        await interaction.response.send_message("🔒 Deine Eingaben wurden verarbeitet!", ephemeral=True)

        embed = discord.Embed(
            title="🎰 SpinBot gestartet!",
            description=f"Starte `{spins}` Spins für `{username}`...",
            color=discord.Color.green()
        )
        embed.set_footer(text="Bitte warten, bis alle Spins abgeschlossen sind...")
        await interaction.followup.send(embed=embed)

        await asyncio.to_thread(spin_lucky_wheel, username, password, spins)

        embed_done = discord.Embed(
            title="✅ Spins abgeschlossen!",
            description=f"Alle `{spins}` Spins für `{username}` wurden erfolgreich ausgeführt!",
            color=discord.Color.blue()
        )

        reward_text = ""
        if rewards:
            reward_text += "**Belohnungen**\n"
            for name, amount in rewards.items():
                reward_text += f"• **{name}**: {amount}\n"
        else:
            reward_text = "Keine Belohnungen erkannt. ❌"

        embed_done.add_field(name="📦 Belohnungen", value=reward_text, inline=False)
        await interaction.followup.send(embed=embed_done)

class SpinBot(discord.Client):
    def __init__(self):
        super().__init__(intents=discord.Intents.default())
        self.tree = app_commands.CommandTree(self)

    async def on_ready(self):
        await self.tree.sync()
        print(f"✅ Bot ist online als {self.user}")

bot = SpinBot()

def log(message):
    timestamp = time.strftime("%H:%M:%S")
    print(f"[{timestamp}] {message}")

def parse_reward_message(msg):
    try:
        match = re.search(r"%xt%lws%1%0%(.*?)%", msg)
        if not match:
            return

        json_str = match.group(1)
        data = json.loads(json_str)

        if "R" in data:
            for entry in data["R"]:
                typ = entry[0]
                val = entry[1]

                if typ == "U":
                    unit_id, amount = val
                    if unit_id == 215:
                        rewards["Schildmaid"] += amount
                    elif unit_id == 238:
                        rewards["Walküren-Scharfschützin"] += amount
                    elif unit_id == 227:
                        rewards["Beschützer des Nordens"] += amount
                    elif unit_id == 216:
                        rewards["Walküren-Waldläuferin"] += amount
                    elif amount == 1000:
                        rewards["Werkzeuge"] += 1
                elif typ == "RI":
                    if "EQ" in val:
                        rewards["Ausrüstung"] += 1
                    elif "GEM" in val:
                        rewards["Ausrüstung"] += 1
                elif typ == "CI":
                    rewards["Konstrukte"] += 1
                elif typ == "LM":
                    rewards["Ausbaumarken"] += val
                elif typ == "STP":
                    rewards["Sceattas"] += val
                elif typ == "LB":
                    kistenmenge = val[1]
                    rewards["Kisten"] += kistenmenge
                elif typ == "UE":
                    rewards["Mehrweller"] += 1
                elif typ == "C2":
                    rewards["Rubine"] += val
                elif typ == "FKT":
                    rewards["Geschenk Ludwig"] += val
                elif typ == "PTK":
                    rewards["Geschenk Beatrice"] += val
                elif typ == "KTK":
                    rewards["Geschenk Ulrich"] += val
                elif typ == "D":
                    rewards["Dekorationen"] += 1

    except Exception as e:
        log(f"❌ Fehler beim Parsen: {e}")

def spin_lucky_wheel(username, password, spins):
    try:
        ws = websocket.WebSocket()
        ws.connect("wss://ep-live-de1-game.goodgamestudios.com/")
        log("✅ Verbindung hergestellt!")

        ws.send("<msg t='sys'><body action='verChk' r='0'><ver v='166' /></body></msg>")
        time.sleep(0.1)

        ws.send("<msg t='sys'><body action='login' r='0'><login z='EmpireEx_2'><nick><![CDATA[]]></nick><pword><![CDATA[1119057%de%0]]></pword></login></body></msg>")
        time.sleep(0.1)

        ws.send(f"%xt%EmpireEx_2%vln%1%{{\"NOM\":\"{username}\"}}%")
        time.sleep(0.1)

        login_befehl = f"%xt%EmpireEx_2%lli%1%{{\"CONM\":491,\"RTM\":74,\"ID\":0,\"PL\":1,\"NOM\":\"{username}\" ,\"PW\":\"{password}\",\"LT\":null,\"LANG\":\"de\",\"DID\":\"0\",\"AID\":\"1735403904264644306\",\"KID\":\"\",\"REF\":\"https://empire-html5.goodgamestudios.com\",\"GCI\":\"\",\"SID\":9,\"PLFID\":1}}%"
        ws.send(login_befehl)
        time.sleep(0.2)

        log("🔐 Erfolgreich eingeloggt! Starte Spins...")

        for i in range(spins):
            log(f"🎰 Spin {i+1}/{spins}")
            ws.send("%xt%EmpireEx_2%lws%1%{\"LWET\":1}%")
            msg = ws.recv()
            print(f"🔍 Empfangen: {msg}")
            parse_reward_message(msg)
            time.sleep(0.1)

        log("✅ Alle Spins abgeschlossen!")
        ws.close()

    except Exception as e:
        log(f"❌ Fehler beim Spin-Prozess: {e}")

@bot.tree.command(name="spin", description="Starte das Glücksrad-Drehen!")
async def spin(interaction: discord.Interaction):
    await interaction.response.send_modal(SpinModal())

bot.run(TOKEN)

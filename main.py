import discord
from discord import app_commands
import asyncio
import os
import websocket
import time
import json
import re
from collections import defaultdict

TOKEN = os.getenv("DISCORD_TOKEN")

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
            placeholder="Gib dein Passwort ein (keiner kann dein Passwort sehen)...",
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

        rewards = await asyncio.to_thread(spin_lucky_wheel, username, password, spins)

        embed_done = discord.Embed(
            title="✅ Spins abgeschlossen!",
            description=f"Alle `{spins}` Spins für `{username}` wurden erfolgreich ausgeführt!",
            color=discord.Color.blue()
        )

        reward_text = ""
        for name, amount in rewards.items():
            reward_text += f"**{name}**: {amount}\n"

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

def spin_lucky_wheel(username, password, spins):
    rewards = defaultdict(int)

    def parse_reward_message(msg):
        match = re.search(r"%xt%lws%1%0%(.*)%", msg)
        if not match:
            return

        try:
            json_str = match.group(1)
            data = json.loads(json_str)

            for reward in data.get("R", []):
                rtype = reward[0]
                rvalue = reward[1]

                # Truppen
                if rtype == "U":
                    unit_id, amount = rvalue
                    if unit_id == 215:
                        rewards["Schildmaid"] += amount
                    elif unit_id == 238:
                        rewards["Walküren-Scharfschützin"] += amount
                    elif unit_id == 227:
                        rewards["Beschützer des Nordens"] += amount
                    elif unit_id == 216:
                        rewards["Walküren-Waldläuferin"] += amount
                    else:
                        rewards["Werkzeuge"] += amount

                # Konstrukte
                elif rtype == "CI":
                    rewards["Konstrukte"] += 1

                # Ausrüstung
                elif rtype == "RI":
                    eq = rvalue.get("EQ", [])
                    gem = rvalue.get("GEM", [])
                    if eq:
                        rewards["Ausrüstung"] += 1
                    elif gem:
                        rewards["Ausrüstung"] += 1  # Edelstein = Ausrüstung

                # Ausbaumarken
                elif rtype == "LM":
                    rewards["Ausbaumarken"] += rvalue

                # Sceattas
                elif rtype == "STP":
                    rewards["Sceattas"] += rvalue

                # Ludwig-Geschenke
                elif rtype == "FKT":
                    rewards["Geschenke Ludwig"] += rvalue

                # Beatrice
                elif rtype == "PTK":
                    rewards["Geschenk Beatrice"] += rvalue

                # Ulrich
                elif rtype == "KTK":
                    rewards["Geschenke Ulrich"] += rvalue

                # Kisten
                elif rtype == "LB":
                    rewards["Kisten"] += rvalue[1]

                # Mehrweller
                elif rtype == "UE":
                    rewards["Mehrweller"] += 1

                # Rubine
                elif rtype == "C2":
                    rewards["Rubine"] += rvalue

                # Dekorationen
                elif rtype == "D":
                    rewards["Dekorationen"] += 1

        except Exception as e:
            log(f"⚠️ Fehler beim Parsen: {e}")

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
            time.sleep(0.1)

            ws.settimeout(2)
            try:
                msg = ws.recv()
                if isinstance(msg, bytes):
                    msg = msg.decode("utf-8", errors="ignore")
                parse_reward_message(msg)
            except websocket.WebSocketTimeoutException:
                log("⏱️ Kein Antwort-Paket empfangen!")

        log("✅ Alle Spins abgeschlossen!")
        ws.close()
        return rewards

    except Exception as e:
        log(f"❌ Fehler beim Spin-Prozess: {e}")
        return rewards

@bot.tree.command(name="spin", description="Starte das Glücksrad-Drehen!")
async def spin(interaction: discord.Interaction):
    await interaction.response.send_modal(SpinModal())

bot.run(TOKEN)

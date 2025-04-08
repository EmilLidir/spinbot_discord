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
            placeholder="Gib dein Passwort (sicher) ein...",
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

        reward_lines = "\n".join([f"**{k}**: {v}" for k, v in rewards.items()])
        embed_done.add_field(name="🎁 Belohnungen", value=reward_lines or "Keine Belohnungen erkannt", inline=False)

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

def parse_reward_message(msg, rewards):
    try:
        json_str = re.search(r"%xt%lws%1%0%(.*)%", msg).group(1)
        data = json.loads(json_str)

        if "R" not in data:
            return

        for item in data["R"]:
            reward_type = item[0]
            reward_data = item[1]

            if reward_type == "U":  # Truppen oder Werkzeuge
                unit_id, amount = reward_data
                if unit_id in [215, 238, 227, 216]:  # Truppen
                    truppen_namen = {
                        215: "Schildmaid",
                        238: "Walküren-Scharfschützin",
                        227: "Beschützer des Nordens",
                        216: "Walküren-Waldläuferin"
                    }
                    rewards[truppen_namen[unit_id]] += amount
                else:  # Werkzeuge
                    rewards["Werkzeuge"] += amount

            elif reward_type == "RI":  # Ausrüstung oder Edelsteine
                rewards["Ausrüstung"] += 1

            elif reward_type == "CI":  # Konstrukt
                rewards["Konstrukte"] += 1

            elif reward_type == "LM":  # Ausbaumarken
                rewards["Ausbaumarken"] += reward_data

            elif reward_type == "STP":  # Sceattas
                rewards["Sceattas"] += reward_data

            elif reward_type == "LB":  # Kisten
                _, amount = reward_data
                rewards["Kisten"] += amount

            elif reward_type == "UE":
                rewards["Mehrweller"] += 1

            elif reward_type == "C2":
                rewards["Rubine"] += reward_data

            elif reward_type == "FKT":
                rewards["Ludwig-Geschenke"] += reward_data

            elif reward_type == "PTK":
                rewards["Beatrice-Geschenke"] += reward_data

            elif reward_type == "KTK":
                rewards["Ulrich-Geschenke"] += reward_data

            elif reward_type == "D":
                rewards["Dekorationen"] += 1

    except Exception as e:
        log(f"❌ Fehler beim Parsen: {e}")

def spin_lucky_wheel(username, password, spins):
    rewards = defaultdict(int)

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
            time.sleep(0.3)

            try:
                msg = ws.recv()
                if isinstance(msg, bytes):
                    msg = msg.decode("utf-8", errors="ignore")
                log(f"🔍 Empfangen: {msg}")

                if "%xt%lws%" in msg:
                    parse_reward_message(msg, rewards)
            except Exception as e:
                log(f"⚠️ Fehler beim Empfangen: {e}")

        log("✅ Alle Spins abgeschlossen!")
        ws.close()
    except Exception as e:
        log(f"❌ Fehler beim Spin-Prozess: {e}")

    return rewards

@bot.tree.command(name="spin", description="Starte das Glücksrad-Drehen!")
async def spin(interaction: discord.Interaction):
    await interaction.response.send_modal(SpinModal())

bot.run(TOKEN)

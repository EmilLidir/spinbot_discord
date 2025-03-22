import discord
from discord import app_commands
import asyncio
import websocket
import time

TOKEN = "MTM1MjQxOTgxMDE2MzY5MTU1MA.GtYKt0.lPJhq1CMwXXP0BHUxgXuLUEgdaekmHdaP_ClMk"

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

def drehe_los(username, password):
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
        time.sleep(0.1)

        ws.send("%xt%EmpireEx_2%lws%1%{\"LWET\":1}%")
        log("🎰 Los gedreht!")
        ws.close()

    except Exception as e:
        log(f"❌ Fehler: {e}")

def spin_lucky_wheel(username, password, spins):
    for i in range(spins):
        log(f"🔄 Runde {i+1}/{spins}")
        drehe_los(username, password)
        time.sleep(0.1)
    log("🎉 Alle Lose wurden gedreht!")

@bot.tree.command(name="spin", description="Starte das Glücksrad-Drehen!")
async def spin(interaction: discord.Interaction, username: str, password: str, spins: int):
    # Ephemeral Message → Nur der Nutzer sieht die Nachricht mit dem Passwort
    await interaction.response.send_message("🔒 Dein Passwort wurde sicher verarbeitet!", ephemeral=True)

    # Normale Nachricht ohne Passwort → Für alle sichtbar
    embed = discord.Embed(title="🎰 SpinBot gestartet!", description=f"Starte `{spins}` Spins für `{username}`...", color=discord.Color.green())
    embed.set_footer(text="Bitte warten, bis alle Spins abgeschlossen sind...")
    await interaction.followup.send(embed=embed)

    await asyncio.to_thread(spin_lucky_wheel, username, password, spins)

    embed_done = discord.Embed(title="✅ Spins abgeschlossen!", description=f"Alle `{spins}` Spins für `{username}` wurden erfolgreich ausgeführt!", color=discord.Color.blue())
    await interaction.followup.send(embed=embed_done)

bot.run(TOKEN)

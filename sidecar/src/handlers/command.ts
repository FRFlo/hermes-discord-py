import { readdirSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import type { Client, SlashCommandBuilder } from "discord.js";
import type { SlashCommand } from "../types.js";

const __dirname = fileURLToPath(new URL(".", import.meta.url));

export default async (client: Client) => {
  const commandsDir = join(__dirname, "../commands");
  const commandFiles = readdirSync(commandsDir).filter(
    (file) => (file.endsWith(".ts") || file.endsWith(".js")) && !file.endsWith(".d.ts")
  );

  const commandBuilders: SlashCommandBuilder[] = [];

  for (const file of commandFiles) {
    const mod = await import(`../commands/${file}`);
    const slashCommand: SlashCommand = mod.default;
    if (!slashCommand || !slashCommand.command) continue;

    client.commands.set(slashCommand.command.name, slashCommand);
    commandBuilders.push(slashCommand.command as SlashCommandBuilder);
    console.log(`[discord.js] Commande slash chargée : /${slashCommand.command.name}`);
  }

  // Enregistrement auprès de Discord une fois le client prêt
  const register = async () => {
    if (!client.application) return;
    try {
      await client.application.commands.set(commandBuilders);
      console.log(`[discord.js] ${commandBuilders.length} commande(s) slash enregistrée(s) auprès de Discord.`);
    } catch (err) {
      console.error("[discord.js] Erreur lors de l'enregistrement des commandes slash :", err);
    }
  };

  if (client.isReady()) {
    await register();
  } else {
    client.once("ready", register);
  }
};

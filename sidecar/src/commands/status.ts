import { SlashCommandBuilder, EmbedBuilder } from "discord.js";
import type { SlashCommand } from "../types.js";

const DEFAULT_ALLOWED_USER = "544862774002581504";
const DEFAULT_FORUM_CHANNEL = "1544452203207589938";

const command: SlashCommand = {
  command: new SlashCommandBuilder()
    .setName("status")
    .setDescription("Affiche l'état de santé du bot, la latence et les ressources"),
  execute: async (interaction) => {
    const allowedUserId = process.env.DISCORD_ALLOWED_USERS?.split(",")[0]?.trim() || DEFAULT_ALLOWED_USER;
    const forumChannelId = process.env.DISCORD_FORUM_CHANNEL_ID || DEFAULT_FORUM_CHANNEL;

    const ping = interaction.client.ws.ping;
    const uptimeSec = Math.floor(process.uptime());
    const hours = Math.floor(uptimeSec / 3600);
    const mins = Math.floor((uptimeSec % 3600) / 60);
    const secs = uptimeSec % 60;
    const uptimeStr = `${hours}h ${mins}m ${secs}s`;
    const mem = (process.memoryUsage().heapUsed / 1024 / 1024).toFixed(2);

    const embed = new EmbedBuilder()
      .setTitle("🤖 État du Bot Hermes (discord.js fine-tuned)")
      .setColor(0x57f287)
      .addFields(
        { name: "⚡ Latence WebSocket", value: `${ping} ms`, inline: true },
        { name: "⏱️ Uptime Sidecar", value: uptimeStr, inline: true },
        { name: "🧠 Mémoire Heap", value: `${mem} MB`, inline: true },
        { name: "👤 Utilisateur autorisé", value: `<@${allowedUserId}>`, inline: true },
        { name: "💬 Forum des sessions", value: `<#${forumChannelId}>`, inline: true }
      )
      .setTimestamp();

    await interaction.reply({ embeds: [embed] });
  },
};

export default command;

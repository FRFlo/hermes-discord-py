import { SlashCommandBuilder, ThreadChannel } from "discord.js";
import type { SlashCommand, InboundCommandEvent } from "../types.js";

const command: SlashCommand = {
  command: new SlashCommandBuilder()
    .setName("close")
    .setDescription("Clôture et archive la session courante du post de forum"),
  execute: async (interaction) => {
    const channel = interaction.channel;
    if (channel && channel.isThread()) {
      await interaction.reply({ content: "🔒 Session clôturée. Archivage du fil en cours...", ephemeral: false });
      try {
        await (channel as ThreadChannel).setArchived(true, "Clôture demandée via /close");
      } catch (err) {
        console.error("[discord.js] Échec archivage fil :", err);
      }
    } else {
      await interaction.reply({ content: "ℹ️ `/close` s'applique uniquement dans un fil de forum.", ephemeral: true });
    }

    const event: InboundCommandEvent = {
      type: "command",
      platform: "discord",
      command: "close",
      chat_id: interaction.channelId,
      sender_id: interaction.user.id,
      sender_name: interaction.user.username,
      interaction_id: interaction.id,
      is_dm: interaction.channel?.isDMBased() ?? false,
    };
    interaction.client.bridge?.emitInboundEvent(event);
  },
};

export default command;

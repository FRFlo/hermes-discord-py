import {
  ActionRowBuilder,
  ButtonBuilder,
  ButtonStyle,
  EmbedBuilder,
} from "discord.js";
import type { DiscordBridgeClient } from "./bridge.js";
import { isSendable } from "./channels.js";

export class AlertManager {
  constructor(private bridge: DiscordBridgeClient) {}

  public async sendSystemAlert(
    title: string,
    errorMessage: string,
    details?: string,
    taskId: string = "default"
  ): Promise<{ messageId?: string }> {
    try {
      const user = await this.bridge.client.users.fetch(this.bridge.allowedUserId);
      const dmChannel = await user.createDM();

      const embed = new EmbedBuilder()
        .setTitle(`🚨 Alerte Système : ${title}`)
        .setColor(0xed4245)
        .setDescription(`**Erreur détectée :**\n\`\`\`\n${errorMessage.slice(0, 1000)}\n\`\`\``)
        .setTimestamp();

      if (details) {
        embed.addFields({ name: "Détails / Contexte", value: details.slice(0, 1000) });
      }

      const row = new ActionRowBuilder<ButtonBuilder>().addComponents(
        new ButtonBuilder()
          .setCustomId(`alert:retry:${taskId}`)
          .setLabel("Relancer la tâche")
          .setStyle(ButtonStyle.Primary)
          .setEmoji("🔄"),
        new ButtonBuilder()
          .setCustomId(`alert:logs:${taskId}`)
          .setLabel("Voir les logs")
          .setStyle(ButtonStyle.Secondary)
          .setEmoji("📜")
      );

      const sent = await dmChannel.send({ embeds: [embed], components: [row] });
      return { messageId: sent.id };
    } catch (err) {
      console.error("[discord.js] Échec envoi alerte système en DM :", err);
      return {};
    }
  }

  public async sendExecApproval(
    chatId: string,
    command: string,
    description?: string,
    replyTo?: string
  ): Promise<{ messageId: string }> {
    const channel = await this.bridge.client.channels.fetch(chatId);
    if (!isSendable(channel)) throw new Error(`Salon ${chatId} invalide`);

    const row = new ActionRowBuilder<ButtonBuilder>().addComponents(
      new ButtonBuilder()
        .setCustomId(`approval:approve:${Date.now()}`)
        .setLabel("Approuver")
        .setStyle(ButtonStyle.Success)
        .setEmoji("✅"),
      new ButtonBuilder()
        .setCustomId(`approval:deny:${Date.now()}`)
        .setLabel("Refuser")
        .setStyle(ButtonStyle.Danger)
        .setEmoji("❌")
    );

    const embed = new EmbedBuilder()
      .setTitle("⚠️ Confirmation requise pour commande sensible")
      .setColor(0xfee75c)
      .setDescription(description || "Hermes demande votre approbation avant d'exécuter la commande ci-dessous :")
      .addFields({ name: "Commande", value: `\`\`\`bash\n${command}\n\`\`\`` })
      .setTimestamp();

    const options: Record<string, unknown> = {
      embeds: [embed],
      components: [row],
    };
    if (replyTo) {
      options.reply = { messageReference: replyTo };
    }

    const sent = await channel.send(options);
    return { messageId: sent.id };
  }
}

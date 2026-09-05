import {
  ActionRowBuilder,
  ButtonBuilder,
  ButtonStyle,
  AttachmentBuilder,
} from "discord.js";
import fs from "node:fs";
import path from "node:path";
import type { DiscordBridgeClient } from "./bridge.js";
import { isSendable } from "./channels.js";
import { splitMarkdown, formatThinkingWithSubtext } from "../splitter.js";

export class MessageManager {
  constructor(private bridge: DiscordBridgeClient) {}

  /**
   * Envoi de messages avec formatage Thinking en sous-texte (-#),
   * découpage Markdown intelligent, support des pièces jointes et boutons d'action post-réponse.
   */
  public async sendMessage(
    chatId: string,
    content: string,
    replyTo?: string,
    extraFiles?: string[],
    withActionButtons: boolean = true
  ): Promise<{ messageIds: string[] }> {
    const channel = await this.bridge.client.channels.fetch(chatId);
    if (!isSendable(channel)) {
      throw new Error(`Le salon ${chatId} est introuvable ou non sendable.`);
    }

    // 1. Formatage du Thinking en sous-texte (-#)
    const formattedWithThinking = formatThinkingWithSubtext(content);

    // 2. Détection et extraction des balises MEDIA:/chemin
    const mediaFiles: string[] = [...(extraFiles || [])];
    const cleanedContent = formattedWithThinking.replace(/MEDIA:([^\s\n]+)/g, (_, filePath) => {
      mediaFiles.push(filePath.trim());
      return "";
    }).trim();

    // 3. Découpage Markdown intelligent
    const chunks = splitMarkdown(cleanedContent || (mediaFiles.length > 0 ? "" : "*(Réponse vide)*"));
    const messageIds: string[] = [];

    // Pièces jointes
    const attachments: AttachmentBuilder[] = [];
    for (const filePath of mediaFiles) {
      if (fs.existsSync(filePath)) {
        attachments.push(new AttachmentBuilder(filePath, { name: path.basename(filePath) }));
      }
    }

    // Boutons post-réponse : [ 🔄 Régénérer ] [ 🔒 Clôturer ]
    const actionRow = new ActionRowBuilder<ButtonBuilder>().addComponents(
      new ButtonBuilder()
        .setCustomId(`action:regenerate:${chatId}`)
        .setLabel("Régénérer")
        .setStyle(ButtonStyle.Secondary)
        .setEmoji("🔄"),
      new ButtonBuilder()
        .setCustomId(`action:close:${chatId}`)
        .setLabel("Clôturer")
        .setStyle(ButtonStyle.Secondary)
        .setEmoji("🔒")
    );

    for (let i = 0; i < chunks.length; i++) {
      const chunk = chunks[i];
      const isLastChunk = i === chunks.length - 1;
      const sendOptions: Record<string, unknown> = { content: chunk };

      if (i === 0 && replyTo) {
        sendOptions.reply = { messageReference: replyTo };
      }

      if (isLastChunk) {
        if (attachments.length > 0) {
          sendOptions.files = attachments;
        }
        if (withActionButtons && !channel.isDMBased()) {
          sendOptions.components = [actionRow];
        }
      }

      const sent = await channel.send(sendOptions);
      messageIds.push(sent.id);
    }

    return { messageIds };
  }
}

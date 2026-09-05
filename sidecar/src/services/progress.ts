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
import { saveLargeOutputToLogFile } from "../splitter.js";

export interface ActiveProgress {
  messageId: string;
  chatId: string;
  steps: string[];
}

export class ProgressManager {
  private activeProgressMessages = new Map<string, ActiveProgress>();

  constructor(private bridge: DiscordBridgeClient) {}

  public hasActiveProgress(chatId: string): boolean {
    return this.activeProgressMessages.has(chatId);
  }

  public getActiveProgress(chatId: string): ActiveProgress | undefined {
    return this.activeProgressMessages.get(chatId);
  }

  public async cancelActiveProgress(chatId: string): Promise<void> {
    const active = this.activeProgressMessages.get(chatId);
    if (active) {
      try {
        const channel = await this.bridge.client.channels.fetch(chatId);
        if (isSendable(channel)) {
          const msg = await channel.messages.fetch(active.messageId);
          await msg.edit({
            content: `||⚠️ **Exécution interrompue par l'utilisateur.**\n${active.steps.join("\n")}||`,
            components: [],
          });
        }
      } catch {
        // ignore
      }
      this.activeProgressMessages.delete(chatId);
    }
  }

  public async updateToolProgress(
    chatId: string,
    toolName: string,
    toolArgs?: string,
    status: "start" | "running" | "done" | "error" = "running",
    output?: string,
    isFinal: boolean = false
  ): Promise<{ progressMessageId?: string }> {
    const channel = await this.bridge.client.channels.fetch(chatId);
    if (!isSendable(channel)) return {};

    let active = this.activeProgressMessages.get(chatId);

    // Si sortie volumineuse > 1500 caractères, sauvegarde automatique dans un fichier .log ou .diff
    let outputSummary = output;
    let generatedLogFile: string | undefined = undefined;
    if (output && output.length > 1500) {
      const saved = saveLargeOutputToLogFile(toolName, output, 1500);
      outputSummary = saved.summary;
      generatedLogFile = saved.filePath;
    }

    const stepText = `• \`${toolName}\`${toolArgs ? ` (${toolArgs.slice(0, 70)})` : ""} : ${
      status === "done" ? "✅" : status === "error" ? "❌" : "⏳"
    }`;

    const stopButtonRow = new ActionRowBuilder<ButtonBuilder>().addComponents(
      new ButtonBuilder()
        .setCustomId(`cancel:${chatId}`)
        .setLabel("Interrompre")
        .setStyle(ButtonStyle.Danger)
        .setEmoji("⏹️")
    );

    if (!active) {
      const initialContent = `⚙️ **Exécution d'outils en cours...**\n${stepText}`;
      const sent = await channel.send({ content: initialContent, components: [stopButtonRow] });
      active = { messageId: sent.id, chatId, steps: [stepText] };
      this.activeProgressMessages.set(chatId, active);
    } else {
      active.steps.push(stepText);
    }

    if (isFinal) {
      // Transformation en bloc spoiler repliable
      const stepsSummary = active.steps.slice(-10).join("\n");
      const spoilerContent = `||⚙️ **Journal des outils exécutés :**\n${stepsSummary}${
        outputSummary ? `\n> Sortie : ${outputSummary.slice(0, 300)}` : ""
      }||`;

      try {
        const msg = await channel.messages.fetch(active.messageId);
        const editOptions: Record<string, unknown> = { content: spoilerContent, components: [] };
        if (generatedLogFile && fs.existsSync(generatedLogFile)) {
          editOptions.files = [new AttachmentBuilder(generatedLogFile, { name: path.basename(generatedLogFile) })];
        }
        await msg.edit(editOptions);
      } catch (err) {
        console.warn("[discord.js] Impossible de mettre à jour le spoiler final des outils :", err);
      }
      this.activeProgressMessages.delete(chatId);
      return { progressMessageId: active.messageId };
    }

    // Mise à jour live avec bouton d'interruption conservé
    const currentSteps = active.steps.slice(-4).join("\n");
    try {
      const msg = await channel.messages.fetch(active.messageId);
      await msg.edit({
        content: `⚙️ **Exécution d'outils en cours...**\n${currentSteps}`,
        components: [stopButtonRow],
      });
    } catch {
      // ignore
    }

    return { progressMessageId: active.messageId };
  }
}

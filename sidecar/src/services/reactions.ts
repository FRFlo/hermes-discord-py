import type { DiscordBridgeClient } from "./bridge.js";
import { isSendable } from "./channels.js";

export class ReactionManager {
  public busyChats = new Set<string>();

  constructor(private bridge: DiscordBridgeClient) {}

  public isChatBusy(chatId: string): boolean {
    return this.busyChats.has(chatId) || this.bridge.progress.hasActiveProgress(chatId);
  }

  public setChatBusy(chatId: string, busy: boolean): void {
    if (busy) {
      this.busyChats.add(chatId);
    } else {
      this.busyChats.delete(chatId);
    }
  }

  public async setReaction(chatId: string, messageId: string, emoji: string, action: "add" | "remove"): Promise<void> {
    const channel = await this.bridge.client.channels.fetch(chatId);
    if (!isSendable(channel)) return;
    try {
      const message = await channel.messages.fetch(messageId);
      if (action === "add") {
        await message.react(emoji);
      } else {
        const reaction = message.reactions.cache.get(emoji);
        if (reaction && this.bridge.client.user) {
          await reaction.users.remove(this.bridge.client.user.id);
        }
      }
    } catch (err) {
      console.warn(`[discord.js] Impossible de modifier la réaction ${emoji} :`, err);
    }
  }

  public async setTurnStartReaction(chatId: string, triggerMessageId: string): Promise<void> {
    if (!this.bridge.enableReactions || !triggerMessageId) return;
    this.busyChats.add(chatId);
    // Si le message portait l'émoji d'attente ⏱️, on le remplace par ⏳ pour indiquer le début du traitement actif
    await this.setReaction(chatId, triggerMessageId, "⏱️", "remove");
    await this.setReaction(chatId, triggerMessageId, "⏳", "add");
  }

  public async setFinalStatusReaction(chatId: string, triggerMessageId: string, success: boolean): Promise<void> {
    if (!this.bridge.enableReactions || !triggerMessageId) return;
    this.busyChats.delete(chatId);
    await this.setReaction(chatId, triggerMessageId, "⏱️", "remove");
    await this.setReaction(chatId, triggerMessageId, "⏳", "remove");
    await this.setReaction(chatId, triggerMessageId, success ? "✅" : "❌", "add");
  }
}

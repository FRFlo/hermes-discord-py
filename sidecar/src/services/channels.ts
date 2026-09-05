import {
  ChannelType,
  type TextChannel,
  type DMChannel,
  type ThreadChannel,
} from "discord.js";
import type { DiscordBridgeClient } from "./bridge.js";
import type { ChatInfoResponse } from "../types.js";

export type Sendable = TextChannel | DMChannel | ThreadChannel;

export function isSendable(channel: unknown): channel is Sendable {
  return Boolean(channel && typeof (channel as { send?: unknown }).send === "function");
}

export class ChannelManager {
  constructor(private bridge: DiscordBridgeClient) {}

  public isChannelAllowed(channel: unknown): boolean {
    if (!channel || typeof channel !== "object") return false;
    const ch = channel as {
      id?: string;
      isDMBased?: () => boolean;
      isThread?: () => boolean;
      parentId?: string;
      parent?: { type?: number };
    };

    // 1. Messages privés (DM)
    if (ch.isDMBased?.()) return true;

    // 2. Fils de discussion sous le salon Forum
    if (ch.isThread?.()) {
      if (ch.parentId === this.bridge.forumChannelId) return true;
      if (ch.parent?.type === ChannelType.GuildForum) return true;
    }

    // 3. Le salon Forum lui-même
    if (ch.id === this.bridge.forumChannelId) return true;

    return false;
  }

  public async deleteMessage(chatId: string, messageId: string): Promise<boolean> {
    try {
      const channel = await this.bridge.client.channels.fetch(chatId);
      if (!isSendable(channel)) return false;
      const message = await channel.messages.fetch(messageId).catch(() => null);
      if (message) {
        await message.delete();
        return true;
      }
      return false;
    } catch (err) {
      console.warn(`[discord.js] Impossible de supprimer le message ${messageId} dans ${chatId}:`, err);
      return false;
    }
  }

  public async archiveThread(chatId: string, reason?: string): Promise<boolean> {
    try {
      const channel = await this.bridge.client.channels.fetch(chatId);
      if (channel && channel.isThread()) {
        await (channel as ThreadChannel).setArchived(true, reason || "Archivage demandé");
        return true;
      }
      return false;
    } catch (err) {
      console.error(`[discord.js] Échec archivage fil ${chatId}:`, err);
      return false;
    }
  }

  public async sendTyping(chatId: string): Promise<void> {
    try {
      const channel = await this.bridge.client.channels.fetch(chatId);
      if (isSendable(channel)) {
        await channel.sendTyping();
      }
    } catch {
      // ignore
    }
  }

  public async getChatInfo(chatId: string): Promise<ChatInfoResponse> {
    try {
      const channel = await this.bridge.client.channels.fetch(chatId);
      if (!channel) {
        return { name: "unknown", type: "unknown", chat_id: chatId };
      }

      if (channel.isDMBased()) {
        return { name: "DM", type: "dm", chat_id: chatId };
      }

      if (channel.isThread()) {
        const isForum = channel.parentId === this.bridge.forumChannelId;
        return {
          name: channel.name,
          type: isForum ? "forum_thread" : "thread",
          chat_id: chatId,
          is_forum_thread: isForum,
        };
      }

      const name = "name" in channel ? (channel.name as string) : "channel";
      return { name, type: "channel", chat_id: chatId };
    } catch {
      return { name: "unknown", type: "unknown", chat_id: chatId };
    }
  }
}

import type { Client } from "discord.js";
import type { BotEvent } from "../types.js";

const event: BotEvent<"ready"> = {
  name: "ready",
  once: true,
  execute: async (client: Client) => {
    if (client.bridge) {
      client.bridge.isReady = true;
    }
    console.log(`[discord.js] Connecté avec succès en tant que ${client.user?.tag}`);
  },
};

export default event;

import { readdirSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import type { Client } from "discord.js";
import type { BotEvent } from "../types.js";

const __dirname = fileURLToPath(new URL(".", import.meta.url));

export default async (client: Client) => {
  const eventsDir = join(__dirname, "../events");
  const eventFiles = readdirSync(eventsDir).filter(
    (file) => (file.endsWith(".ts") || file.endsWith(".js")) && !file.endsWith(".d.ts")
  );

  for (const file of eventFiles) {
    const mod = await import(`../events/${file}`);
    const event: BotEvent = mod.default;
    if (!event || !event.name) continue;

    if (event.once) {
      client.once(event.name, (...args: unknown[]) =>
        (event.execute as (...a: unknown[]) => void)(...args)
      );
    } else {
      client.on(event.name, (...args: unknown[]) =>
        (event.execute as (...a: unknown[]) => void)(...args)
      );
    }
    console.log(`[discord.js] Événement enregistré : ${event.name}`);
  }
};

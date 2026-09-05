import { readdirSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import type { Client } from "discord.js";
import type { ButtonCommand } from "../types.js";

const __dirname = fileURLToPath(new URL(".", import.meta.url));

export default async (client: Client) => {
  const buttonsDir = join(__dirname, "../buttons");
  const buttonFiles = readdirSync(buttonsDir).filter(
    (file) => (file.endsWith(".ts") || file.endsWith(".js")) && !file.endsWith(".d.ts")
  );

  for (const file of buttonFiles) {
    const mod = await import(`../buttons/${file}`);
    const button: ButtonCommand = mod.default;
    if (!button || !button.prefix) continue;

    client.buttons.set(button.prefix, button);
    console.log(`[discord.js] Bouton interactif chargé : [${button.prefix}]`);
  }
};

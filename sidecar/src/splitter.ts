/**
 * Utilitaire de découpage de messages Markdown respectant la limite de 2 000 caractères de Discord
 * tout en préservant l'intégrité des blocs de code Markdown (fermeture/réouverture des balises ```).
 */

import fs from "node:fs";
import path from "node:path";

const MAX_DISCORD_LENGTH = 1950; // Marge de sécurité pour les balises de code et sauts de ligne

export function splitMarkdown(content: string, maxLength: number = MAX_DISCORD_LENGTH): string[] {
  if (content.length <= maxLength) {
    return [content];
  }

  const lines = content.split("\n");
  const chunks: string[] = [];
  let currentChunk = "";
  let inCodeBlock = false;
  let codeBlockLang = "";

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    const codeBlockMatch = line.match(/^```(\w*)/);

    // Vérifie si l'ajout de cette ligne dépasse la limite
    // En tenant compte d'une éventuelle fermeture de bloc de code `\n``` `
    const overhead = inCodeBlock ? 4 : 0;
    if (currentChunk.length + line.length + 1 + overhead > maxLength) {
      if (currentChunk.trim().length > 0) {
        if (inCodeBlock) {
          // Ferme le bloc de code dans le fragment actuel
          currentChunk += "\n```";
          chunks.push(currentChunk);
          // Réouvre le même bloc de code dans le fragment suivant
          currentChunk = `\`\`\`${codeBlockLang}\n${line}`;
        } else {
          chunks.push(currentChunk);
          currentChunk = line;
        }
      } else {
        // La ligne seule dépasse la limite max -> découpage séquentiel
        let remaining = line;
        while (remaining.length > maxLength) {
          const slice = remaining.slice(0, maxLength);
          chunks.push(inCodeBlock ? slice + "\n```" : slice);
          remaining = (inCodeBlock ? `\`\`\`${codeBlockLang}\n` : "") + remaining.slice(maxLength);
        }
        currentChunk = remaining;
      }
    } else {
      if (currentChunk.length > 0) {
        currentChunk += "\n" + line;
      } else {
        currentChunk = line;
      }
    }

    if (codeBlockMatch) {
      if (inCodeBlock) {
        inCodeBlock = false;
        codeBlockLang = "";
      } else {
        inCodeBlock = true;
        codeBlockLang = codeBlockMatch[1] || "";
      }
    }
  }

  if (currentChunk.trim().length > 0) {
    if (inCodeBlock && !currentChunk.endsWith("```")) {
      currentChunk += "\n```";
    }
    chunks.push(currentChunk);
  }

  return chunks;
}

/**
 * Formate les blocs de réflexion interne (Thinking / Chain of Thought)
 * avec le format natif Discord de sous-texte (-# texte grisé).
 */
export function formatThinkingWithSubtext(content: string): string {
  // Détection des balises <thinking>...</thinking> ou <thought>...</thought>
  return content.replace(/<(?:thinking|thought)>([\s\S]*?)<\/(?:thinking|thought)>/gi, (_, thinkingContent) => {
    const trimmed = thinkingContent.trim();
    if (!trimmed) return "";
    const lines = trimmed.split("\n");
    const subtextLines = lines.map((l: string) => `-# ${l}`).join("\n");
    return `${subtextLines}\n\n`;
  });
}

/**
 * Si une sortie d'outil dépasse 1500 caractères, l'enregistre dans un fichier .log ou .diff
 * et renvoie le chemin du fichier pour pièce jointe Discord.
 */
export function saveLargeOutputToLogFile(toolName: string, output: string, threshold: number = 1500): { summary: string; filePath?: string } {
  if (output.length <= threshold) {
    return { summary: output };
  }

  const now = new Date();
  const timeStr = `${now.getHours()}h${String(now.getMinutes()).padStart(2, "0")}`;
  const ext = toolName.includes("diff") ? "diff" : "log";
  const filename = `${toolName.replace(/[^a-zA-Z0-9_-]/g, "_")}_output_${timeStr}.${ext}`;

  const targetDir = process.env.HERMES_UPLOADS_DIR || path.join(process.cwd(), "uploads");
  if (!fs.existsSync(targetDir)) {
    fs.mkdirSync(targetDir, { recursive: true });
  }

  const filePath = path.join(targetDir, filename);
  try {
    fs.writeFileSync(filePath, output, "utf-8");
    const preview = output.slice(0, 300).trim();
    const summary = `${preview}...\n*(Sortie complète de ${output.length} car. disponible dans le fichier joint ${filename})*`;
    return { summary, filePath };
  } catch (err) {
    console.warn("[splitter] Impossible de sauvegarder le log volumineux:", err);
    return { summary: output.slice(0, threshold) + "...\n*(Tronqué)*" };
  }
}

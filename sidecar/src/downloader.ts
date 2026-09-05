import fs from "node:fs";
import path from "node:path";
import https from "node:https";
import http from "node:http";

const UPLOAD_DIR_CANDIDATES = [
  process.env.HERMES_UPLOADS_DIR,
  "/workspace/uploads",
  path.join(process.cwd(), "cache", "uploads"),
].filter(Boolean) as string[];

function getTargetUploadDir(): string {
  for (const dir of UPLOAD_DIR_CANDIDATES) {
    try {
      if (!fs.existsSync(dir)) {
        fs.mkdirSync(dir, { recursive: true });
      }
      return dir;
    } catch {
      continue;
    }
  }
  const fallback = path.join(process.cwd(), "uploads");
  if (!fs.existsSync(fallback)) {
    fs.mkdirSync(fallback, { recursive: true });
  }
  return fallback;
}

export interface CachedAttachment {
  name: string;
  url: string;
  size: number;
  localPath: string;
  isText: boolean;
  textContent?: string;
  contentType?: string;
}

const TEXT_EXTENSIONS = new Set([
  ".txt", ".md", ".json", ".yaml", ".yml", ".py", ".js", ".ts", ".tsx", ".jsx",
  ".sh", ".bash", ".css", ".html", ".sql", ".env", ".toml", ".ini", ".conf", ".log", ".diff", ".patch"
]);

export async function downloadAndCacheAttachment(
  url: string,
  filename: string,
  size: number,
  contentType?: string
): Promise<CachedAttachment> {
  const uploadDir = getTargetUploadDir();
  const safeFilename = `${Date.now()}_${filename.replace(/[^a-zA-Z0-9._-]/g, "_")}`;
  const targetPath = path.join(uploadDir, safeFilename);

  await new Promise<void>((resolve, reject) => {
    const file = fs.createWriteStream(targetPath);
    const client = url.startsWith("https") ? https : http;

    client.get(url, (response) => {
      if (response.statusCode !== 200) {
        file.close();
        fs.unlink(targetPath, () => {});
        reject(new Error(`Échec du téléchargement (status: ${response.statusCode})`));
        return;
      }

      response.pipe(file);
      file.on("finish", () => {
        file.close();
        resolve();
      });
    }).on("error", (err) => {
      file.close();
      fs.unlink(targetPath, () => {});
      reject(err);
    });
  });

  const ext = path.extname(filename).toLowerCase();
  const isText = TEXT_EXTENSIONS.has(ext) || (contentType?.startsWith("text/") ?? false);
  let textContent: string | undefined = undefined;

  // Injection automatique si fichier texte < 50 Ko
  if (isText && size < 50 * 1024 && fs.existsSync(targetPath)) {
    try {
      textContent = fs.readFileSync(targetPath, "utf-8");
    } catch (err) {
      console.warn(`[downloader] Impossible de lire le texte de ${filename}:`, err);
    }
  }

  return {
    name: filename,
    url,
    size,
    localPath: targetPath,
    isText,
    textContent,
    contentType,
  };
}

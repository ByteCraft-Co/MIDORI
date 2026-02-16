import fs from "node:fs";
import path from "node:path";

type LoadedDoc = {
  title: string;
  body: string;
  slug: string;
};

const CONTENT_ROOT = path.join(process.cwd(), "content");

function parseTitle(raw: string, fallback: string): string {
  const firstHeading = raw.match(/^#\s+(.+)$/m);
  return firstHeading?.[1]?.trim() ?? fallback;
}

function toSlug(parts: string[]): string {
  return parts.join("/").replace(/\\/g, "/");
}

function safeReadFile(filePath: string): string | null {
  try {
    return fs.readFileSync(filePath, "utf8");
  } catch {
    return null;
  }
}

export function loadDoc(slugParts: string[]): LoadedDoc | null {
  const slug = toSlug(slugParts);
  const candidate = path.join(CONTENT_ROOT, "docs", `${slug}.md`);
  const fallback = path.join(CONTENT_ROOT, "docs", ...slugParts, "index.md");
  const raw = safeReadFile(candidate) ?? safeReadFile(fallback);

  if (!raw) {
    return null;
  }

  const title = parseTitle(raw, slugParts.at(-1) ?? "Document");
  return { title, body: raw, slug };
}

export function loadBlogPost(slugParts: string[]): LoadedDoc | null {
  const slug = toSlug(slugParts);
  const post = path.join(CONTENT_ROOT, "blog", `${slug}.md`);
  const raw = safeReadFile(post);

  if (!raw) {
    return null;
  }

  const title = parseTitle(raw, slugParts.at(-1) ?? "Post");
  return { title, body: raw, slug };
}

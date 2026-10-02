import {extname, join, normalize} from "node:path";

const TYPES = {
  ".css": "text/css; charset=utf-8",
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".json": "application/json; charset=utf-8",
};

export function contentTypeFor(path) {
  return TYPES[extname(path)] || "application/octet-stream";
}

export function resolveAsset(root, pathname) {
  if (!pathname.startsWith("/src/")) return null;
  const relative = normalize(pathname).replace(/^[/\\]+/, "");
  if (!relative.startsWith("src/")) return null;
  return join(root, relative);
}

export function isDocumentPath(pathname) {
  return pathname === "/" || !extname(pathname);
}

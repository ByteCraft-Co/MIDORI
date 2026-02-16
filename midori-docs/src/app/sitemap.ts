import type { MetadataRoute } from "next";

export default function sitemap(): MetadataRoute.Sitemap {
  const base = "https://midori-lang.dev";

  return [
    "",
    "/about",
    "/roadmap",
    "/docs/getting-started",
    "/docs/tour",
    "/docs/reference",
    "/docs/compiler",
    "/blog/launch-note",
    "/changelog",
    "/playground",
  ].map((route) => ({
    url: `${base}${route}`,
    lastModified: new Date(),
    changeFrequency: "weekly",
    priority: route === "" ? 1 : 0.7,
  }));
}

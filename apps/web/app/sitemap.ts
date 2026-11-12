import type { MetadataRoute } from "next";
import { SITE, concepts, errors, interviews, roadmaps, skills } from "./lib/seo";

export default function sitemap(): MetadataRoute.Sitemap {
  const now = new Date();
  const pages: MetadataRoute.Sitemap = [
    { url: `${SITE}/`, lastModified: now, priority: 1 },
    { url: `${SITE}/concepts`, lastModified: now, priority: 0.9 },
    { url: `${SITE}/roadmaps`, lastModified: now, priority: 0.8 },
    { url: `${SITE}/errors`, lastModified: now, priority: 0.7 },
    { url: `${SITE}/interviews`, lastModified: now, priority: 0.8 },
  ];
  return [
    ...pages,
    ...concepts.map((item) => ({ url: `${SITE}/concepts/${item.slug}`, lastModified: now, priority: 0.6 })),
    ...roadmaps.map((item) => ({ url: `${SITE}/roadmaps/${item.slug}`, lastModified: now, priority: 0.6 })),
    ...errors.map((item) => ({ url: `${SITE}/errors/${item.slug}`, lastModified: now, priority: 0.4 })),
    ...skills.map((item) => ({ url: `${SITE}/skills/${item.slug}`, lastModified: now, priority: 0.5 })),
    ...interviews.map((item) => ({ url: `${SITE}/interviews/${item.slug}`, lastModified: now, priority: 0.6 })),
  ];
}

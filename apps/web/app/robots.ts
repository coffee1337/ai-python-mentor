import type { MetadataRoute } from "next";
import { SITE } from "./lib/seo";

export default function robots(): MetadataRoute.Robots {
  return {
    rules: [
      { userAgent: "*", allow: ["/", "/concepts", "/roadmaps", "/errors", "/interviews", "/skills"], disallow: ["/api/", "/admin"] },
    ],
    sitemap: `${SITE}/sitemap.xml`,
    host: SITE,
  };
}

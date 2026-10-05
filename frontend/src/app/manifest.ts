import type { MetadataRoute } from "next";

export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "GlideUp",
    short_name: "GlideUp",
    description: "Find jobs. Practice interviews. Get hired.",
    start_url: "/dashboard",
    scope: "/",
    display: "standalone",
    background_color: "#0b2a4a",
    theme_color: "#0b2a4a",
    icons: [
      { src: "/icons/icon-192.png", sizes: "192x192", type: "image/png" },
      { src: "/icons/icon-512.png", sizes: "512x512", type: "image/png" },
      { src: "/icons/icon-maskable-512.png", sizes: "512x512", type: "image/png", purpose: "maskable" },
    ],
  };
}

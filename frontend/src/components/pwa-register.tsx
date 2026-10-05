"use client";

import { useEffect } from "react";

/** Registers the service worker in production builds (installable app, offline page). */
export function PwaRegister() {
  useEffect(() => {
    if (process.env.NODE_ENV !== "production" || !("serviceWorker" in navigator)) return;
    navigator.serviceWorker.register("/sw.js").catch(() => {
      // An unsupported or blocked service worker only costs the offline page.
    });
  }, []);
  return null;
}

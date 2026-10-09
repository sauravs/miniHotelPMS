/**
 * The real-browser layer. Kept small on purpose: it does only what jsdom cannot - computed
 * styles, keyboard reachability, and an accessibility pass.
 *
 * NO webServer AND NO PORT. Each test renders the components to static HTML in Node, from the
 * golden payloads, and hands the browser that HTML with the engine's stylesheet inlined. Nothing
 * listens and nothing is fetched (architecture.md section 5: a suite that needs a server up is
 * not a suite).
 */
import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "e2e",
  forbidOnly: !!process.env.CI,
  reporter: process.env.CI ? "list" : "line",
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
});

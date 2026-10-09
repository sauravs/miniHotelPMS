/**
 * Render a component inside the app's real chrome (Shell) to a whole document, styled by the engine's own stylesheet read from disk -
 * the same bytes `/style.css` serves - and load it into the page. No server, no port, no fetch.
 */
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import type { Page } from "@playwright/test";
import { createElement, type ReactElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { Shell } from "../components/Shell";

const ROOT = resolve(import.meta.dirname, "../..");
const STYLESHEET = readFileSync(resolve(ROOT, "hotelcontrols/web/assets/style.css"), "utf-8");

export const golden = <T>(name: string): T =>
  JSON.parse(readFileSync(resolve(ROOT, "fixtures/api", name), "utf-8")) as T;

export async function show(page: Page, element: ReactElement) {
  await page.setContent(
    `<!doctype html><html lang="en"><head><meta charset="utf-8"><title>Run</title>` +
      `<style>${STYLESHEET}</style></head><body>` +
      renderToStaticMarkup(createElement(Shell, null, element)) +
      `</body></html>`,
  );
}

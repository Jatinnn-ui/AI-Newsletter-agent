// Creates demo runs (deterministic test mode) on a running backend and captures real UI screenshots
// with the locally installed Chrome/Edge. Each capture waits for actual rendered content.
//
//   cd scripts && npm install && npm run screenshots
//   (backend on :8000, frontend dev server on :5173; override with API_URL / UI_URL)

import { existsSync, mkdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import puppeteer from "puppeteer-core";

const API = process.env.API_URL ?? "http://127.0.0.1:8000";
const UI = process.env.UI_URL ?? "http://127.0.0.1:5173";
const OUT = join(dirname(fileURLToPath(import.meta.url)), "..", "docs", "screenshots");
const GOAL = "Create a weekly newsletter on the latest AI agent news and send it to our subscribers.";
const BROWSERS = [
  process.env.CHROME_PATH,
  "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
  "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe",
  "/usr/bin/google-chrome",
  "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
].filter(Boolean);

async function call(method, path, body) {
  const res = await fetch(`${API}${path}`, {
    method,
    headers: body ? { "Content-Type": "application/json" } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) throw new Error(`${method} ${path} -> ${res.status} ${await res.text()}`);
  return res.json();
}

async function waitStatus(id, statuses, timeoutMs = 30000) {
  const end = Date.now() + timeoutMs;
  while (Date.now() < end) {
    const d = await call("GET", `/api/agent/runs/${id}`);
    if (statuses.includes(d.status)) return d;
    await new Promise((r) => setTimeout(r, 300));
  }
  throw new Error(`run ${id} did not reach ${statuses}`);
}

async function shoot(browser, { url, name, width, height = 900, text, fullPage = true }) {
  const page = await browser.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  page.on("console", (m) => m.type() === "error" && errors.push(m.text()));
  await page.setViewport({ width, height, deviceScaleFactor: 1 });
  await page.goto(url, { waitUntil: "domcontentloaded" });
  // Wait until the UI shows content that only appears after real API responses.
  await page.waitForFunction((t) => document.body.innerText.includes(t), { timeout: 20000 }, text);
  await new Promise((r) => setTimeout(r, 800)); // let the sandboxed preview iframe paint
  if (fullPage) {
    // The app shell scrolls inside <main>, so grow the viewport to the content height.
    const contentHeight = await page.evaluate(() => document.querySelector("main")?.scrollHeight ?? document.body.scrollHeight);
    await page.setViewport({ width, height: Math.min(Math.max(contentHeight, height), 6000), deviceScaleFactor: 1 });
    await new Promise((r) => setTimeout(r, 500));
  }
  const path = join(OUT, name);
  await page.screenshot({ path });
  console.log(`saved ${name}${errors.length ? `  (page errors: ${errors.join(" | ")})` : ""}`);
  await page.close();
  return errors;
}

async function main() {
  mkdirSync(OUT, { recursive: true });
  const executablePath = BROWSERS.find((p) => existsSync(p));
  if (!executablePath) throw new Error("Chrome/Edge not found; set CHROME_PATH");

  const auto = (await call("POST", "/api/agent/runs", { goal: GOAL, mode: "autonomous", deterministic: true })).run_id;
  await waitStatus(auto, ["completed", "completed_with_warnings"]);
  const research = (await call("POST", "/api/agent/runs", { goal: GOAL, mode: "human_in_the_loop", deterministic: true })).run_id;
  await waitStatus(research, ["awaiting_research_approval"]);
  const draft = (await call("POST", "/api/agent/runs", { goal: GOAL, mode: "human_in_the_loop", deterministic: true })).run_id;
  await waitStatus(draft, ["awaiting_research_approval"]);
  await call("POST", `/api/agent/runs/${draft}/approve-research`, { selected_ids: null });
  await waitStatus(draft, ["awaiting_draft_approval"]);

  const browser = await puppeteer.launch({ executablePath, headless: true, args: ["--no-first-run"] });
  const errors = [];
  try {
    errors.push(...(await shoot(browser, { url: `${UI}/`, name: "workspace.png", width: 1600, text: "What should I research?", fullPage: false })));
    errors.push(...(await shoot(browser, { url: `${UI}/runs/${research}`, name: "hitl-research.png", width: 1600, text: "Waiting for your approval" })));
    errors.push(...(await shoot(browser, { url: `${UI}/runs/${draft}`, name: "hitl-draft.png", width: 1600, text: "Waiting for your approval" })));
    errors.push(...(await shoot(browser, { url: `${UI}/runs/${auto}`, name: "completed-run.png", width: 1600, height: 1100, text: "Simulated delivery", fullPage: false })));
    errors.push(...(await shoot(browser, { url: `${UI}/runs/${auto}`, name: "mobile.png", width: 390, height: 844, text: "Simulated delivery", fullPage: false })));
  } finally {
    await browser.close();
  }
  if (errors.length) {
    console.error("Browser reported errors:", errors);
    process.exit(1);
  }
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});

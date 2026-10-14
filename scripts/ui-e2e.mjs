// Browser end-to-end test: drives the real UI (clicks the actual controls) against the running backend.
//   cd scripts && npm run e2e      (backend :8000 + frontend :5173 must be running; override with UI_URL)
// Uses deterministic test mode unless E2E_LIVE=1 (then it needs real API keys on the backend).

import { existsSync } from "node:fs";
import puppeteer from "puppeteer-core";

const UI = (process.env.UI_URL ?? "http://127.0.0.1:5173").replace(/\/+$/, "");
const LIVE = process.env.E2E_LIVE === "1";
const TIMEOUT = LIVE ? 240000 : 30000;
const GOAL = "Create a weekly newsletter covering the latest AI agent news, product launches and research.";
const exe = [
  process.env.CHROME_PATH,
  "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
  "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe",
  "/usr/bin/google-chrome",
].find((p) => p && existsSync(p));

const step = (m) => console.log(`OK  ${m}`);
const waitText = (page, text, timeout = TIMEOUT) =>
  page.waitForFunction((t) => document.body.innerText.includes(t), { timeout }, text);

/** Clicks the first enabled button whose text starts with `label`, optionally inside `scope`. */
async function clickButton(page, label, scope = "body") {
  const handle = await page.waitForFunction(
    (l, s) => [...document.querySelectorAll(`${s} button`)].find((b) => b.innerText.trim().startsWith(l) && !b.disabled && b.offsetParent !== null),
    { timeout: TIMEOUT },
    label,
    scope,
  );
  await handle.asElement().click();
}

async function noHorizontalOverflow(page, where) {
  const over = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  if (over > 1) throw new Error(`horizontal overflow of ${over}px on ${where}`);
}

async function startRun(page, { hitl }) {
  await page.goto(UI, { waitUntil: "domcontentloaded" });
  await waitText(page, "API connected", 15000);
  await page.waitForSelector("#goal");
  await page.$eval("#goal", (el) => {
    el.focus();
  });
  await page.keyboard.type(GOAL);
  if (hitl) await page.$eval('input[value="human_in_the_loop"]', (el) => el.click());
  if (!LIVE) {
    const box = await page.$('input[name="demo"]');
    if (box && !(await box.evaluate((el) => el.checked || el.disabled))) await box.click();
  }
  await clickButton(page, "Run Agent");
  await page.waitForFunction(() => /^\/runs\/[a-f0-9]{32}/.test(location.pathname), { timeout: 10000 });
}

const storyCount = (page) =>
  page.$eval('iframe[title="Newsletter HTML preview"]', (f) => (f.srcdoc.match(/class="story"/g) ?? []).length);

async function main() {
  if (!exe) throw new Error("Chrome/Edge not found; set CHROME_PATH");
  const browser = await puppeteer.launch({ executablePath: exe, headless: true });
  const errors = [];
  try {
    const page = await browser.newPage();
    page.on("pageerror", (e) => errors.push(e.message));
    await page.setViewport({ width: 1440, height: 1000 });

    // 0. Validation: an empty goal is rejected client-side without a request.
    await page.goto(UI, { waitUntil: "domcontentloaded" });
    await waitText(page, "API connected", 15000);
    await clickButton(page, "Run Agent");
    await waitText(page, "Describe the newsletter you want");
    if (!/^\/$/.test(new URL(page.url()).pathname)) throw new Error("navigated despite invalid goal");
    step("Empty goal blocked by validation");

    // 1. Autonomous: no approvals, ends saved, newsletter preview + downloads.
    await startRun(page, { hitl: false });
    await waitText(page, "Simulated delivery · Newsletter generated and saved");
    await page.waitForSelector('iframe[title="Newsletter HTML preview"]', { timeout: 10000 });
    const sandbox = await page.$eval('iframe[title="Newsletter HTML preview"]', (f) => f.getAttribute("sandbox"));
    if (sandbox.includes("allow-scripts") || sandbox.includes("allow-same-origin")) throw new Error(`unsafe sandbox: ${sandbox}`);
    if ((await storyCount(page)) < 1) throw new Error("preview has no stories");
    // Export lives in a toolbar popover. Open it once, then download both files.
    await clickButton(page, "Export");
    await page.waitForSelector('[role="dialog"][aria-label="Export newsletter"]', { timeout: 5000 });
    for (const [label, ext] of [["HTML", "newsletter.html"], ["Markdown", "newsletter.md"]]) {
      const res = page.waitForResponse((r) => r.url().includes(ext) && r.request().method() === "GET");
      await clickButton(page, label, '[role="dialog"][aria-label="Export newsletter"]');
      if ((await res).status() !== 200) throw new Error(`${label} download failed`);
    }
    await page.keyboard.press("Escape"); // close the popover
    await page.$eval("#studio-tab-markdown", (el) => el.click());
    await page.waitForSelector("article.prose-editorial h2", { timeout: 5000 });
    step("Autonomous run completed; sandboxed preview, Markdown view, HTML + Markdown downloads work");

    // 2. HITL: approve an edited article selection, request a revision, approve and save.
    await startRun(page, { hitl: true });
    await waitText(page, "Waiting for your approval");
    const boxes = 'ul[aria-label="Candidate articles"] input[type="checkbox"]';
    await page.waitForSelector(`${boxes}:checked`, { timeout: 5000 });
    const before = await page.$$eval(`${boxes}:checked`, (els) => els.length);
    await page.$eval(`${boxes}:checked`, (el) => el.click());
    await new Promise((r) => setTimeout(r, 5000)); // survive background refreshes
    const after = await page.$$eval(`${boxes}:checked`, (els) => els.length);
    if (after !== before - 1) throw new Error(`selection edit lost (before ${before}, after ${after})`);
    await clickButton(page, "Approve research");
    await waitText(page, "Approve and save");
    await page.waitForSelector('iframe[title="Newsletter HTML preview"]', { timeout: 10000 });
    const stories = await storyCount(page);
    if (stories !== after) throw new Error(`draft has ${stories} stories, expected ${after}`);
    step(`HITL paused for research; removed one article; draft shows exactly ${after} stories`);

    await page.type("#revision-feedback", "Make the summaries shorter");
    await clickButton(page, "Revise newsletter");
    await page.waitForFunction(() => /1\/\d+ used/.test(document.body.innerText), { timeout: TIMEOUT });
    // Revision history lives in the collapsible review details in the insights rail.
    await clickButton(page, "Show checks, issues and revisions");
    await waitText(page, "requested by you");
    step("Revision request re-ran revision + review and paused again");

    await clickButton(page, "Approve and save");
    await waitText(page, "Simulated delivery · Newsletter generated and saved");
    step("Draft approved and saved");

    // 3. HITL cancel through the confirm dialog.
    await startRun(page, { hitl: true });
    await waitText(page, "Waiting for your approval");
    await clickButton(page, "Cancel run", "section[aria-labelledby=approval-title]");
    await clickButton(page, "Cancel run", "dialog[open]");
    await waitText(page, "Run cancelled");
    step("Paused run cancelled via confirm dialog");

    // 4. History filters and mobile layout.
    await page.goto(`${UI}/runs`, { waitUntil: "domcontentloaded" });
    await page.waitForSelector('[role="table"] a[role="row"]', { timeout: 10000 });
    await page.select("#f-status", "closed");
    await page.waitForFunction(() => [...document.querySelectorAll('[role="table"] a[role="row"]')].every((r) => r.innerText.includes("Cancelled") || r.innerText.includes("Expired")), { timeout: 5000 });
    step("Run history status filter works");

    await page.setViewport({ width: 390, height: 844, isMobile: true, hasTouch: true });
    for (const path of ["/", "/runs", "/newsletters", "/settings"]) {
      await page.goto(`${UI}${path}`, { waitUntil: "networkidle0" });
      await noHorizontalOverflow(page, path);
    }
    await page.click('button[aria-label="Open navigation"]');
    await page.waitForSelector("dialog[open] nav", { timeout: 3000 });
    step("Mobile: no horizontal overflow; navigation drawer opens");
  } finally {
    await browser.close();
  }
  if (errors.length) throw new Error("Page errors: " + errors.join(" | "));
  console.log("UI end-to-end: all checks passed");
}

main().catch((e) => {
  console.error("FAIL", e.message);
  process.exit(1);
});

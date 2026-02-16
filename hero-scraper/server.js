/**
 * Hero Scraper API
 * HTTP wrapper for Ulixee Hero - receives URLs and returns scraped HTML.
 * Connects to Ulixee Cloud (Hero Core) running in a separate container.
 */
import express from "express";
import Hero from "@ulixee/hero";

const app = express();
app.use(express.json());

const HERO_CORE_HOST = process.env.HERO_CORE_HOST || "hero:1818";
const PORT = parseInt(process.env.PORT || "3000", 10);

app.get("/health", (req, res) => {
  res.json({ status: "ok", service: "hero-scraper" });
});

app.post("/scrape", async (req, res) => {
  const { url } = req.body;
  if (!url || typeof url !== "string") {
    return res.status(400).json({ error: "Missing or invalid 'url' in request body" });
  }

  let hero;
  try {
    hero = new Hero({
      connectionToCore: {
        host: HERO_CORE_HOST,
      },
    });

    await hero.goto(url, { timeoutMs: 60000 });

    const html = await hero.document.documentElement.outerHTML;

    res.set("Content-Type", "text/html; charset=utf-8");
    res.send(html);
  } catch (err) {
    console.error(`[hero-scraper] Error scraping ${url}:`, err.message);
    res.status(500).json({
      error: "Scrape failed",
      message: err.message,
    });
  } finally {
    if (hero) {
      await hero.close().catch(() => {});
    }
  }
});

app.listen(PORT, "0.0.0.0", () => {
  console.log(`[hero-scraper] Listening on port ${PORT}, Hero Core: ${HERO_CORE_HOST}`);
});

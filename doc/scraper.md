# Universal Scraper

The Universal Scraper allows complex multi-step scraping (chaining) where results from one step serve as input for the next.

## Key Concepts
- **`follow_links: true`**: Explicitly tells the scraper to use extracted links as URLs for the next step.
- **`yield_links: true`**: Explicitly tells the scraper that extracted links are final results to be saved in the database.
- **`use_browser: true`**: Uses the headless Chromium instance (Webtop) to handle Javascript, wait for elements, or bypass protections.
- **`wait_for: 'selector'`**: Used with `use_browser: true`. Pauses the scraper until the specified CSS element (or text like `text=...`) appears on the page.
- **`wait_timeout: 30`**: (Optional) Time in seconds to wait for `wait_for` before timing out (default: 15s).
- **`wait_until: 'networkidle'`**: (Optional) Browser condition to wait for: `load`, `domcontentloaded`, `networkidle` (default: `domcontentloaded`).
- **`click_selector: 'selector'`**: Used with `use_browser: true`. Instructs the browser to click the specified CSS element before extracting the page content.
- **`js_code: |`**: Used with `use_browser: true`. Executes custom Javascript within the page to manually extract complex data. The code must return an array of strings (URLs) or dictionaries. If it returns dictionaries, they can contain `url` (the target link to follow/unlock), `scraped_url` (an optional custom stable identifier like `url#Episode-1` to check/record in the database instead of the volatile URL to avoid duplicate scraping/unlocking of the same item), and other custom properties (like `title`, `release`, etc.).
- **`scrape_once: true`**: Instructs the scraper to memorize the URL of this step in the database so it is never scraped again during future runs (prevents infinite loops on old articles).
- **`cooldown_hours: 6`** (or **`scrape_cooldown_hours: 6`**): (Optional) Number of hours to wait before re-scraping a URL in this step. The scraper checks the database for the last scrape timestamp. If the elapsed time is less than the specified number of hours, the URL is skipped. Once the cooldown has expired, the URL is scraped again. This is ideal for index pages or feeds that are periodically updated.
- **`item_delay: 1.5`**: (Optional) Time in seconds to wait between processing individual items/links in a loop. Adds ±20% jitter for better stealth. (Default: 1s for RSS/Follow steps).
- **`ignore_resolutions: ["720p", "480p"]`**: (Optional) List of resolutions to ignore. If found in the item title or content, the item will be skipped.
- **`override_title: "{{ step_name.variable }}"`**: Forces the final media title using a variable extracted during a previous step (via `js_code` or `rss`). This title is treated as the **source of truth** and will prioritize over obfuscated filenames during metadata enrichment.
- **`override_year: "{{ step_name.variable }}"`**: Same as `override_title` but forces the release year.
- **`auto_download: true`**: (New) Automatically triggers the debrid-unlock and download workflow as soon as links are discovered and enriched. Perfect for full automation.
  - Can also accept a list of years, e.g., `auto_download: [2025, 2026]` to only download releases from specific years.
  - Alternatively, you can specify `auto_download_years: [2025, 2026]` at the same level as `auto_download: true` to restrict downloads by year for that specific step.
  - You can also specify `auto_download_keywords: ["multi", "truefrench"]` to only download releases where the title or filename contains at least one of these keywords (case-insensitive).
  - You can also specify `auto_download_resolutions: ["1080p", "4kLight"]` to only download releases that match one of these resolutions (either matched via parsed metadata or containing the resolution text in the title/filename).
- **`schedule_hour: 1`**: (Optional, source-level) Scheduled hour (0-23) to run this source. When defined, the scraper for this source will run only once a day at that specific hour, completely bypassing and ignoring the global scheduler restrictions (`scan_start_hour`, `scan_end_hour`, `scan_interval_minutes`).
- **Global Settings** (in `config/config.yaml`):
  - **`auto_download_series_packs: false`**: (New) If set to `false`, prevents automatic download of series packs (full seasons). Default is `true`.
- **`debug: true`**: Saves the HTML content and a screenshot of the step in `/app/data/debug/` for troubleshooting.
- **`hoster_patterns`** (or `hoster_patterns_url`): Regex patterns to extract the final hoster links (e.g., 1fichier). If defined, the unlocker will exclusively search for these patterns on the unlocked page.
- **`dig_patterns`** (or `dig_patterns_url`): Regex patterns to extract intermediate links that must be navigated/dug into during the next step (e.g., rentry, idrix).
- **`ignore_patterns`**: List of regex patterns to explicitly ignore. If an extracted link matches one of these, it will be discarded (useful for filtering out tags, comments, or help pages).
- **`unlockers`** (Global config): Defines global rules for unlocking specific link protectors. Links matching any unlocker `patterns` are sent to the unlocker. You can configure `wait_for`, `click`, `extract_input`, and other actions to automate the unlocking process globally without writing code.
- **`unlock_patterns`**: (Optional) You can still define step-specific patterns that should be automatically sent to the LinkUnlocker. Any links matching these patterns (or the global unlocker patterns) are sent to the unlocker.
- **`type: "json"`**: Tells the scraper to parse the response as JSON (perfect for APIs).
- **`headers`**: Dictionary of custom HTTP headers to send with the request (e.g., `Accept`, `Origin`, `Authorization`).
- **`items_path: "$.path"`**: JSONPath expression to extract an array of items from the JSON response.
- **`filter: "$.results[?(@.id == {{ ... }})]"`**: JSONPath filter to match specific objects in the array.
- **`result_path: "$[0]"`**: Selects a specific element from the extracted/filtered list (e.g., to keep only the first result).
- **`pagination`**: Dictionary to handle paginated APIs. Contains `param` (the URL query parameter for the page), `max_pages` (limit), and `total_path` (JSONPath to find the total number of pages).
- **`{{ settings.VARIABLE }}`**: You can access any variable from `settings.py` or `.env` dynamically inside your URLs (e.g., `{{ settings.TMDB_API_KEY }}`).

## Configuration Example

```yaml
# --- Global Unlockers ---
unlockers:
  - name: "unlock"
    patterns:
      - 'https?://unlock\.net/.*'
    wait_for: "#unlockBtn"
    click: "#unlockBtn"
    wait_result: ".result-input"
    extract_input: true

sources:
  - name: "MyComplexSource"
    is_chain: true
    steps:
      - name: "index"
        url: "https://example.com/index"
        type: "html"
        follow_links: true
        dig_patterns_url:
          - 'https?://example\.com/post/[\w-]+'

      - name: "post_page"
        url: "{{ index }}"
        use_browser: true
        wait_for: ".download-button"
        debug: true  # Saves screenshot & HTML to data/debug/
        yield_links: true
        hoster_patterns_url:
          - 'href=["''](https?://(?:www\.)?1fichier\.com/\?[\w-]+)[^"'']*["'']'
```

## Context Variables (Templating)

When a step extracts links and passes them to the next step, it transfers an entire dictionary of attributes. These attributes are accessible in the next step using `{{ step_name.attribute }}`.

The structure of this dictionary depends on how the links were extracted:
- **`js_code`**: Transfers exactly the dictionary returned by the Javascript code (e.g., `{"url": "...", "title": "..."}`).
- **`type: "json"` (`items_path`)**: Transfers the exact JSON object extracted from the API (e.g., `{"id": 123, "title": "...", "release_date": "2024-01-01"}`).
- **`type: "rss"`**: Transfers standard RSS item fields (e.g., `{"link": "...", "title": "...", "published": "..."}`).
- **`type: "html"` (Regex `dig_patterns` / `regex_patterns`)**: Transfers a minimal dictionary containing only the URL: `{"url": "the_matched_url"}`.

*Note: For steps that only extract URLs (like regex), you can use `{{ step_name.url }}` or simply `{{ step_name }}` to inject the URL into the next step.*

## Debugging Config

- **Visual Inspection**: Open `http://localhost:8002` to see the browser in action.
- **Debug Files**: Check `./data/debug/` for screenshots and HTML dumps generated via `debug: true`.

## Alternative scrapers

- https://github.com/omkarcloud/botasaurus
- https://github.com/D4Vinci/Scrapling

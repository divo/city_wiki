# Product Roadmap

## Current State

The dataset creation tool can import cities from WikiVoyage, geocode POIs, detect duplicates, and auto-merge them. A web console allows manual review and refinement. The mobile app consumes exported datasets.

## Roadmap

1. [ ] POI Deduplication Refinement — Complete the main city POI deduplication logic that merges POIs appearing in both main city and district listings, using best-value selection for merged fields `S`

2. [ ] Duplicate Key Detection and Merge — Implement detection and automatic merging of POIs with identical name-latitude-longitude keys to eliminate exact duplicates `S`

3. [ ] OSM ID Matching Pipeline — Integrate local PBF file processing into the Prefect workflow to match POIs with OpenStreetMap IDs, enabling external data validation and future enrichment `M`

4. [ ] Hero Image Fetching — Implement automated fetching of city hero images from Wikipedia/Wikimedia Commons, with selection logic to pick the best image from multiple candidates `M`

5. [ ] POI Image Pipeline — Build automated POI image fetching from available sources (Wikimedia, OSM-linked images), with storage and optimization for mobile delivery `L`

6. [ ] LLM Description Rewriting — Implement batch processing to rewrite all POI descriptions using OpenAI, ensuring consistent style, tone, and quality across the dataset `M`

7. [ ] LLM City Summary Generation — Use LLM to generate engaging city "about" sections and "10 things this city is famous for" content from POI data and wiki sources `S`

8. [ ] Themed List Auto-Generation — Automate the creation of curated POI lists based on city characteristics, using LLM to identify themes and select appropriate POIs `M`

9. [ ] S3 Export Pipeline — Build automated export of completed city datasets to S3 in mobile-app-ready format, with versioning and integrity checks `S`

10. [ ] Seed-to-Guide Automation — Implement the full pipeline starting from only GPS coordinates: auto-detect city name, fetch WikiVoyage content, run all enrichment steps, generate content, export to S3 `XL`

11. [ ] Quality Validation Framework — Build automated quality checks that verify dataset completeness (coordinate coverage, description quality, image presence) before export approval `M`

12. [ ] Multi-Source Data Fetching — Extend beyond WikiVoyage to pull POI data from additional sources (Wikipedia, OSM tags, other travel wikis) for cities with sparse coverage `L`

> Notes
> - Items 1-3 complete the current Prefect workflow as outlined in Plan.md
> - Items 4-8 add the content enrichment layer (images + LLM rewriting)
> - Items 9-12 achieve the long-term vision of fully automated dataset creation
> - Each item should result in a working, testable feature integrated into the Prefect workflow
> - Effort estimates: XS (1 day), S (2-3 days), M (1 week), L (2 weeks), XL (3+ weeks)

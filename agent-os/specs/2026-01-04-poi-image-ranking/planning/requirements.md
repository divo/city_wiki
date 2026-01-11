# Spec Requirements: POI Image Ranking

## Initial Description

Automatically downloading images for POIs and ranking them in terms of quality. Download 10 images and automatically pick the best one.

## Requirements Discussion

### First Round Questions

**Q1:** Image Sources - Should we continue using Wikimedia Commons and Pixabay, or add additional sources?
**Answer:** Just use Wikimedia, Pixabay doesn't have much relevant content.

**Q2:** Ranking Method - Should we use an LLM via OpenAI API to evaluate and rank images?
**Answer:** Use a locally running ML ranker instead. User already has images in datasets, so re-fetch 10 images for those POIs and mark 1 as "best". Also wants a quick UI for ranking images and building a ranking dataset. Training a model will probably be the bulk of this work.

**Q3:** Search Query Strategy - Should search queries include POI name plus contextual information (city name, category)?
**Answer:** Search queries work better with less context. Translation can be a problem - most images are captioned in English but POI titles may be in different languages.

**Q4:** Batch Processing - Should this run for all POIs or only those without images?
**Answer:** To start with, just for POIs that are also included in Lists. When moving to backend serving content, it will be all POIs.

**Q5:** Candidate Storage - Should we store all 10 candidates temporarily, or only download the winner?
**Answer:** If we can get away with just ranking the thumbnail and only download the winner, do that. Thumbnail is probably enough to rank on.

**Q6:** Failure Handling - What should happen if no suitable images are found for a POI?
**Answer:** Leave blank and flag for review, but also supply a category fallback option.

**Q7:** Rate Limiting - Should there be limits on API requests?
**Answer:** 500 requests/hour for Wikimedia API - be good citizens and respect this limit.

**Q8:** Image Resize - Any requirements around image optimization?
**Answer:** There is already a script to resize images (`resize_images.sh`), need to incorporate that.

### Existing Code to Reference

**Similar Features Identified:**
- Feature: Image fetching from Wikimedia - Path: `/home/divo/code/city_wiki/cities/views/images.py` (specifically `_fetch_wikimedia_images()` function)
- Feature: Image resize script - Path: `/home/divo/code/city_wiki/resize_images.sh` (Shell script using ImageMagick, max 800x600)
- Feature: Batch processing pattern - Path: `/home/divo/code/city_wiki/cities/enrich_tasks.py` (Celery tasks with progress logging)
- Feature: Prefect workflow integration - Path: `/home/divo/code/city_wiki/workflow/city_import.py` (Async task orchestration)

### Follow-up Questions

**Follow-up 1:** Training Data Approach - For the ranking UI, should it be pairwise comparison where you're shown two images and click the better one?
**Answer:** User already has "good" images - everything in existing datasets (~561 images). Don't need pairwise comparison between random images. Instead, read the POI database and use the same fetch requests to get other candidate images - those can be ranked as "bad". This is essentially a binary classification: existing selected images = good, other fetched candidates = bad.

**Follow-up 2:** Model Complexity - Should we use (A) transfer learning, (B) feature extraction + simple classifier, or (C) heuristic scoring with pre-trained aesthetic models?
**Answer:** Start with option C (heuristic scoring using existing aesthetic models like NIMA/LAION) as baseline.

**Follow-up 3:** Good Image Criteria - What makes a POI image "good"?
**Answer:** Mostly lighting and composition - like it was taken by a professional.

**Follow-up 4:** Ranking UI Scope - Should the ranking UI be a standalone Django page or a separate tool?
**Answer:** Add it to the Django app (not a separate tool).

## Visual Assets

### Files Provided:
No visual assets provided.

### Visual Insights:
N/A

## Requirements Summary

### Functional Requirements

**Image Fetching:**
- Use Wikimedia Commons as the sole image source (drop Pixabay)
- Fetch up to 10 candidate images per POI
- Use minimal search context (POI name primarily) to avoid translation issues
- Respect Wikimedia API rate limit of 500 requests/hour
- Evaluate candidates using thumbnails only, download only the selected winner

**Image Ranking:**
- Implement aesthetic scoring using pre-trained models (NIMA or LAION aesthetic predictor)
- Run scoring locally (no cloud API calls for ranking)
- Quality criteria: professional-looking images with good lighting and composition
- Binary classification approach: existing curated images = good, fetched alternatives = bad

**Batch Processing:**
- Initial scope: Process only POIs that are included in PoiLists
- Future scope: Expand to all POIs when backend serves content
- Integrate into existing Prefect workflow pipeline
- Incorporate existing `resize_images.sh` script for final image processing

**Failure Handling:**
- If no suitable images found: leave image blank and flag POI for manual review
- Provide category-based fallback images as an option (e.g., generic "restaurant" image)

**Training Data Generation:**
- Use existing ~561 POI images as "good" training examples
- Fetch alternative candidates for same POIs as "bad" training examples
- Store training data for potential future model fine-tuning

**Django UI:**
- Add image ranking/review page to existing Django web console
- Allow manual review of flagged POIs without suitable images
- Support building training dataset through the UI

### Reusability Opportunities

- Extend `_fetch_wikimedia_images()` in `/home/divo/code/city_wiki/cities/views/images.py` for thumbnail fetching
- Follow batch processing pattern from `/home/divo/code/city_wiki/cities/enrich_tasks.py`
- Integrate into Prefect workflow following `/home/divo/code/city_wiki/workflow/city_import.py` patterns
- Reuse or Python-ify logic from `/home/divo/code/city_wiki/resize_images.sh`

### Scope Boundaries

**In Scope:**
- Wikimedia image fetching with rate limiting
- Pre-trained aesthetic model scoring (NIMA/LAION)
- Thumbnail-based candidate evaluation
- Winner download and storage
- Image resizing (800x600 max)
- Prefect workflow integration for batch processing
- Django UI for manual review and training data building
- Processing POIs in Lists initially
- Category fallback images
- Training data generation (existing images = good, alternatives = bad)

**Out of Scope:**
- Pixabay or other image sources
- Custom ML model training (using pre-trained only for now)
- Processing all POIs (future phase)
- Cloud-based image ranking APIs
- Mobile-optimized image formats beyond resize
- Image source attribution/licensing tracking
- Pairwise comparison UI (not needed with binary classification approach)

### Technical Considerations

- **ML Library:** Will need to add NIMA or LAION aesthetic predictor dependencies (likely PyTorch-based)
- **Local Processing:** Model inference runs locally, no GPU required for pre-trained aesthetic scoring
- **Rate Limiting:** Must implement 500 req/hour limit for Wikimedia API (approximately 8 requests/minute, or ~7.5 second delay between requests)
- **Thumbnail Strategy:** Wikimedia API provides thumbnail URLs - use these for ranking to minimize bandwidth
- **Storage:** Only final selected images stored; thumbnails used transiently for ranking
- **Existing Images:** 561 POI images across 7 cities available as training data baseline
- **Image Resize:** Incorporate existing ImageMagick-based resize script (max 800x600, maintains aspect ratio)

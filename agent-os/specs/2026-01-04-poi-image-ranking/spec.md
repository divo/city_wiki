# Specification: POI Image Ranking

## Goal
Automatically fetch and rank images for POIs using pre-trained aesthetic scoring models (NIMA/LAION), evaluating thumbnails from Wikimedia Commons and selecting the best image based on lighting and composition quality.

## User Stories
- As a dataset curator, I want images to be automatically fetched and ranked for POIs so that I spend less time manually selecting images
- As a dataset curator, I want to review flagged POIs without suitable images so that I can manually resolve edge cases

## Specific Requirements

**Wikimedia Image Fetching**
- Extend `_fetch_wikimedia_images()` to return thumbnail URLs alongside full image URLs
- Use Wikimedia API `iiurlwidth` parameter to request 300px thumbnails for ranking
- Implement 500 requests/hour rate limiting using a token bucket or sliding window approach
- Use minimal search context (POI name only) to avoid translation issues with non-English POI names
- Fetch up to 10 candidate images per POI

**Aesthetic Scoring Service**
- Create a new service module `cities/services/image_ranking.py` for ML scoring logic
- Use NIMA (Neural Image Assessment) or LAION aesthetic predictor as pre-trained model
- Run inference locally on CPU (no GPU required for aesthetic scoring)
- Score images based on lighting, composition, and professional quality
- Return normalized scores (0-10 scale) for comparison across images

**Thumbnail-Based Evaluation**
- Download only thumbnails (approximately 300px width) for scoring candidates
- Store thumbnails transiently in memory or temp files during scoring
- Delete thumbnails after scoring is complete
- Only download the full-resolution winner image for permanent storage

**POI Scope: Lists Only**
- Query POIs that exist in at least one `PoiList` via the `lists` ManyToMany relationship
- Filter to POIs without existing `image_file` (or optionally include all for re-ranking)
- Add a parameter to toggle between "missing images only" and "all POIs in lists"

**Image Storage and Resizing**
- Use existing `poi_image_path()` function for file path generation
- Integrate Python equivalent of `resize_images.sh` logic: max 800x600, maintain aspect ratio
- Use Pillow for image resizing (already in Django ecosystem)
- Delete old image file before saving new one using existing `delete_image_file()` method

**Failure Handling and Flagging**
- Create a new Validation record when no suitable images found (context='image_ranking', aggregate='no_images')
- Flag POIs with all candidate scores below a configurable threshold
- Provide category-based fallback images as optional feature (e.g., generic "restaurant.jpg")
- Log detailed failure reasons for debugging

**Prefect Workflow Integration**
- Create new task `rank_poi_images_for_lists` in `workflow/city_import.py`
- Follow existing async pattern using `sync_to_async` for Django ORM calls
- Process POIs in batches of 50 to balance memory usage and progress visibility
- Add step to main `import_city` flow after OSM ID lookup

**Django Training Data Review Page**
- Create new URL route: `/image-ranking/` for training data management
- Create new template: `cities/templates/cities/image_ranking.html`
- Display side-by-side comparison: current "good" image vs fetched candidates
- Allow marking images as "good" or "bad" for training dataset
- Store training labels in a new `ImageTrainingData` model

## Visual Design
No visual assets provided.

## Existing Code to Leverage

**`/home/divo/code/city_wiki/cities/views/images.py` - Wikimedia Fetching**
- Reuse `_fetch_wikimedia_images()` as base for thumbnail fetching
- Follow the same User-Agent header pattern for API compliance
- Extend response structure to include thumbnail URLs from `imageinfo` API
- Reuse `_download_image()` for downloading winner image

**`/home/divo/code/city_wiki/cities/enrich_tasks.py` - Batch Processing Pattern**
- Follow the Celery `@shared_task` decorator pattern for new tasks
- Use same progress logging approach (log every N POIs processed)
- Replicate error handling pattern with try/except per POI
- Follow the result dictionary structure: `{'status': 'success', 'processed_count': N, 'updated_count': M}`

**`/home/divo/code/city_wiki/workflow/city_import.py` - Prefect Integration**
- Follow existing `@task` and `@flow` decorator patterns
- Use `sync_to_async` wrapper for all Django ORM operations
- Replicate the `_get_user_confirmation()` pattern if manual review checkpoint needed
- Add to the main flow after `_auto_merge_duplicates` step

**`/home/divo/code/city_wiki/resize_images.sh` - Image Resizing Logic**
- Convert ImageMagick `convert -resize 800x600>` to Pillow equivalent
- Maintain aspect ratio (the `>` flag only shrinks if larger)
- Support jpg, jpeg, png, gif formats as in the shell script

**`/home/divo/code/city_wiki/cities/models.py` - Model Patterns**
- Follow `PointOfInterest` model pattern for new `ImageTrainingData` model
- Use `models.ForeignKey` with `on_delete=models.CASCADE` for POI relationship
- Include `created_at` timestamp following existing conventions

## Out of Scope
- Pixabay or other image sources beyond Wikimedia Commons
- Custom ML model training or fine-tuning (using pre-trained models only)
- Processing POIs outside of PoiLists (future phase)
- Cloud-based image ranking APIs or services
- Mobile-optimized image formats (WebP, AVIF) beyond standard resize
- Image source attribution or licensing metadata tracking
- Pairwise comparison UI for training data (using binary classification instead)
- GPU acceleration for model inference
- Caching of aesthetic scores between runs
- Automatic re-ranking of existing images

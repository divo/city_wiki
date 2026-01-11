# Task Breakdown: POI Image Ranking

## Overview
Total Tasks: 34 subtasks across 5 task groups

This feature implements automatic image fetching and aesthetic ranking for POIs using pre-trained ML models (NIMA/LAION). Images are fetched from Wikimedia Commons, ranked using thumbnails for efficiency, and the best image is downloaded and resized for storage.

## Task List

### Infrastructure & Dependencies

#### Task Group 1: ML Dependencies and Rate Limiting
**Dependencies:** None

- [ ] 1.0 Complete ML infrastructure setup
  - [ ] 1.1 Write 3-5 focused tests for rate limiter and ML scoring
    - Test token bucket rate limiter respects 500 req/hour limit
    - Test aesthetic scorer returns normalized 0-10 scores
    - Test scorer handles missing/corrupt images gracefully
  - [ ] 1.2 Add ML dependencies to project
    - Add PyTorch (CPU-only) to requirements
    - Add NIMA or LAION aesthetic predictor package
    - Add any required image processing dependencies
    - Run `uv add` for each dependency
  - [ ] 1.3 Create rate limiter utility in `cities/services/rate_limiter.py`
    - Implement token bucket or sliding window algorithm
    - Configure for 500 requests/hour (approximately 7.5 second delay between requests)
    - Add async-compatible interface for Prefect workflow usage
    - Include logging for rate limit events
  - [ ] 1.4 Create aesthetic scoring service in `cities/services/image_ranking.py`
    - Load pre-trained NIMA or LAION model (CPU inference)
    - Implement `score_image(image_bytes) -> float` method
    - Return normalized scores on 0-10 scale
    - Handle image loading errors gracefully with logging
  - [ ] 1.5 Ensure infrastructure tests pass
    - Run ONLY the 3-5 tests written in 1.1
    - Verify rate limiter enforces timing constraints
    - Verify scorer produces valid scores

**Acceptance Criteria:**
- The 3-5 tests written in 1.1 pass
- Rate limiter correctly throttles requests to 500/hour
- Aesthetic scorer loads model and produces 0-10 scores
- All dependencies install cleanly with `uv sync`

---

### Database Layer

#### Task Group 2: Data Model and Migration
**Dependencies:** None (can run in parallel with Task Group 1)

- [ ] 2.0 Complete database layer
  - [ ] 2.1 Write 3-4 focused tests for ImageTrainingData model
    - Test model creation with POI foreign key
    - Test image_label choices (good/bad)
    - Test cascade delete when POI is deleted
  - [ ] 2.2 Create `ImageTrainingData` model in `cities/models.py`
    - Fields: `poi` (ForeignKey to PointOfInterest), `image_url` (URLField), `thumbnail_url` (URLField, nullable), `image_label` (CharField with choices: good/bad), `aesthetic_score` (FloatField, nullable), `created_at` (DateTimeField)
    - Follow existing model patterns (use `on_delete=models.CASCADE`)
    - Add index on `poi` and `image_label` for query performance
  - [ ] 2.3 Create migration for `ImageTrainingData` table
    - Run `python manage.py makemigrations cities`
    - Verify migration file is created correctly
  - [ ] 2.4 Apply migration
    - Run `python manage.py migrate`
    - Verify table is created in database
  - [ ] 2.5 Register model with Django admin
    - Add `ImageTrainingData` to `cities/admin.py`
    - Configure list display for easy browsing
  - [ ] 2.6 Ensure database layer tests pass
    - Run ONLY the 3-4 tests written in 2.1
    - Verify model creates and saves correctly

**Acceptance Criteria:**
- The 3-4 tests written in 2.1 pass
- Migration runs successfully
- Model appears in Django admin
- Foreign key relationship works correctly

---

### Backend Services

#### Task Group 3: Image Fetching and Processing Services
**Dependencies:** Task Group 1, Task Group 2

- [ ] 3.0 Complete image fetching and processing services
  - [ ] 3.1 Write 4-6 focused tests for image services
    - Test `_fetch_wikimedia_images_with_thumbnails()` returns both full and thumbnail URLs
    - Test thumbnail download and transient storage
    - Test image resizing maintains aspect ratio within 800x600
    - Test winner image download and storage
    - Test Validation record creation for failed lookups
  - [ ] 3.2 Extend `_fetch_wikimedia_images()` in `cities/views/images.py`
    - Add `iiurlwidth=300` parameter to Wikimedia API call for thumbnails
    - Return dictionary with both `url` and `thumbnail_url` for each image
    - Limit to 10 candidate images per POI
    - Use minimal search context (POI name only)
  - [ ] 3.3 Create thumbnail download utility in `cities/services/image_ranking.py`
    - Download thumbnail to memory (BytesIO) or temp file
    - Integrate with rate limiter from Task Group 1
    - Return image bytes for scoring
    - Clean up temp files after scoring
  - [ ] 3.4 Create image resize utility in `cities/services/image_ranking.py`
    - Port `resize_images.sh` logic to Pillow
    - Max dimensions: 800x600, maintain aspect ratio
    - Only shrink if image is larger (like ImageMagick `>` flag)
    - Support jpg, jpeg, png, gif formats
  - [ ] 3.5 Create POI image ranking service in `cities/services/image_ranking.py`
    - Implement `rank_poi_images(poi) -> Optional[str]` method
    - Fetch up to 10 candidate thumbnails using extended Wikimedia function
    - Score each thumbnail using aesthetic scorer
    - Return URL of highest-scoring image above threshold
    - Return None if no suitable images found
  - [ ] 3.6 Create image storage service in `cities/services/image_ranking.py`
    - Download full-resolution winner image
    - Resize using utility from 3.4
    - Use existing `poi_image_path()` for file path generation
    - Delete old image using `poi.delete_image_file()` before saving
    - Save new image to POI's `image_file` field
  - [ ] 3.7 Implement failure handling
    - Create Validation record when no suitable images found
    - Use `context='image_ranking'`, `aggregate='no_images'`
    - Include POI name and city in description
    - Log detailed failure reasons for debugging
  - [ ] 3.8 Ensure image service tests pass
    - Run ONLY the 4-6 tests written in 3.1
    - Verify end-to-end ranking flow works

**Acceptance Criteria:**
- The 4-6 tests written in 3.1 pass
- Wikimedia API returns thumbnail URLs
- Images are correctly resized within 800x600
- Validation records created for failures
- Winner images saved to correct path

---

### Workflow Integration

#### Task Group 4: Prefect Workflow and Batch Processing
**Dependencies:** Task Group 3

- [ ] 4.0 Complete Prefect workflow integration
  - [ ] 4.1 Write 3-4 focused tests for workflow tasks
    - Test `rank_poi_images_for_lists` processes POIs in lists only
    - Test batch processing respects batch size of 50
    - Test workflow handles POI processing errors gracefully
  - [ ] 4.2 Create POI query utility for workflow
    - Query POIs that exist in at least one `PoiList` via `lists` ManyToMany
    - Add parameter to filter: "missing images only" vs "all POIs in lists"
    - Return queryset for batch processing
  - [ ] 4.3 Create `rank_poi_images_for_lists` task in `workflow/city_import.py`
    - Follow existing `@task` decorator pattern
    - Use `sync_to_async` for all Django ORM operations
    - Process POIs in batches of 50
    - Log progress every batch (e.g., "Processed 50/200 POIs")
    - Follow existing result dictionary structure: `{'status': 'success', 'processed_count': N, 'updated_count': M}`
  - [ ] 4.4 Add configurable score threshold
    - Default threshold for minimum acceptable aesthetic score
    - Flag POIs with all scores below threshold
    - Make threshold configurable via task parameter
  - [ ] 4.5 Integrate into main `import_city` flow
    - Add step after `_auto_merge_duplicates` (Step 8)
    - Call `rank_poi_images_for_lists` for the imported city
    - Add results to main result dictionary under `image_ranking` key
  - [ ] 4.6 Add optional category fallback images
    - Define fallback image paths for each POI category (eat, see, sleep, shop, drink, play)
    - Apply fallback when no suitable images found (configurable)
    - Store fallback images in `media/cities/images/fallbacks/`
  - [ ] 4.7 Ensure workflow tests pass
    - Run ONLY the 3-4 tests written in 4.1
    - Verify workflow processes POIs correctly

**Acceptance Criteria:**
- The 3-4 tests written in 4.1 pass
- Only POIs in PoiLists are processed
- Batch processing works with configurable size
- Workflow integrates into existing import flow
- Progress is logged appropriately

---

### Django UI

#### Task Group 5: Training Data Review Page
**Dependencies:** Task Group 2, Task Group 3

- [ ] 5.0 Complete Django training data review UI
  - [ ] 5.1 Write 2-3 focused tests for training data views
    - Test image ranking page loads with POIs that have images
    - Test marking image as good/bad creates ImageTrainingData record
    - Test fetching alternative candidates for comparison
  - [ ] 5.2 Create URL route in `cities/urls.py`
    - Add `/image-ranking/` route for training data management
    - Add `/image-ranking/mark/` POST endpoint for labeling
    - Add `/image-ranking/fetch-alternatives/<poi_id>/` for fetching candidates
  - [ ] 5.3 Create view functions in `cities/views/image_ranking.py`
    - `image_ranking_page(request)` - render main page with POIs that have images
    - `mark_image(request)` - POST handler to create ImageTrainingData record
    - `fetch_alternatives(request, poi_id)` - fetch alternative candidates for comparison
  - [ ] 5.4 Create template `cities/templates/cities/image_ranking.html`
    - Display POIs with current "good" image
    - Show side-by-side comparison: current image vs fetched alternatives
    - Add buttons to mark images as "good" or "bad"
    - Follow existing Django template patterns in the project
  - [ ] 5.5 Add basic styling
    - Use existing CSS framework/patterns from the project
    - Grid layout for image comparison
    - Clear visual distinction between current and candidate images
  - [ ] 5.6 Implement training data generation logic
    - Button to bulk-fetch alternatives for POIs with images
    - Auto-label existing images as "good"
    - Store fetched alternatives with aesthetic scores
  - [ ] 5.7 Ensure UI tests pass
    - Run ONLY the 2-3 tests written in 5.1
    - Verify page renders correctly
    - Verify labeling creates records

**Acceptance Criteria:**
- The 2-3 tests written in 5.1 pass
- Page accessible at `/image-ranking/`
- Can view current images and alternatives side-by-side
- Can mark images as good/bad
- ImageTrainingData records created correctly

---

### Testing

#### Task Group 6: Test Review and Gap Analysis
**Dependencies:** Task Groups 1-5

- [ ] 6.0 Review existing tests and fill critical gaps only
  - [ ] 6.1 Review tests from Task Groups 1-5
    - Review the 3-5 tests from infrastructure (Task 1.1)
    - Review the 3-4 tests from database (Task 2.1)
    - Review the 4-6 tests from services (Task 3.1)
    - Review the 3-4 tests from workflow (Task 4.1)
    - Review the 2-3 tests from UI (Task 5.1)
    - Total existing tests: approximately 15-22 tests
  - [ ] 6.2 Analyze test coverage gaps for image ranking feature only
    - Identify critical integration points lacking coverage
    - Focus on end-to-end workflow from fetch to storage
    - Do NOT assess entire application test coverage
  - [ ] 6.3 Write up to 8 additional strategic tests maximum
    - Focus on integration between services (e.g., fetching + scoring + saving)
    - Test error recovery scenarios (e.g., Wikimedia API failure mid-batch)
    - Test rate limiter under concurrent usage
    - Skip exhaustive edge case testing
  - [ ] 6.4 Run feature-specific tests only
    - Run ONLY tests related to POI image ranking feature
    - Expected total: approximately 23-30 tests maximum
    - Do NOT run the entire application test suite
    - Verify all critical workflows pass

**Acceptance Criteria:**
- All feature-specific tests pass (approximately 23-30 tests total)
- Critical integration paths are covered
- No more than 8 additional tests added
- Testing focused exclusively on image ranking feature

---

## Execution Order

Recommended implementation sequence:

```
Phase 1 (Parallel):
├── Task Group 1: ML Dependencies and Rate Limiting
└── Task Group 2: Data Model and Migration

Phase 2:
└── Task Group 3: Image Fetching and Processing Services

Phase 3 (Parallel):
├── Task Group 4: Prefect Workflow and Batch Processing
└── Task Group 5: Django Training Data Review Page

Phase 4:
└── Task Group 6: Test Review and Gap Analysis
```

**Notes:**
- Task Groups 1 and 2 have no dependencies and can be developed in parallel
- Task Group 3 depends on both 1 and 2 (needs ML scorer and model)
- Task Groups 4 and 5 can be developed in parallel after Task Group 3
- Task Group 6 should run last to review all tests

## Technical Notes

**Key Files to Create:**
- `cities/services/image_ranking.py` - Core ML scoring and image processing
- `cities/services/rate_limiter.py` - Wikimedia API rate limiting
- `cities/views/image_ranking.py` - Django views for training UI
- `cities/templates/cities/image_ranking.html` - Training data UI template

**Key Files to Modify:**
- `cities/models.py` - Add ImageTrainingData model
- `cities/views/images.py` - Extend `_fetch_wikimedia_images()` for thumbnails
- `cities/urls.py` - Add image ranking routes
- `cities/admin.py` - Register ImageTrainingData
- `workflow/city_import.py` - Add image ranking task to flow

**Existing Code to Leverage:**
- `_fetch_wikimedia_images()` in `cities/views/images.py`
- `_download_image()` in `cities/views/images.py`
- `poi_image_path()` in `cities/models.py`
- `delete_image_file()` method on PointOfInterest model
- Prefect task patterns in `workflow/city_import.py`
- Celery task result structure in `cities/enrich_tasks.py`

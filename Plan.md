# Running
source .venv/bin/activate
python manage.py runserver
redis-server
celery -A city_wiki worker -l INFO --pool=solo -P solo

For running prefect
uv run prefect server start
uv run prefect worker start --pool "import-pool"
http://localhost:4200/deployments/deployment/20428ca0-4db1-4434-a424-3fd5ff1b54e2?tab=Runs and start a new run

## Current task
Implement a full automated and cleanup flow using Prefect, in `workflows, folder.

Lots of uncommited changes to figure out, nice one me....

workflow/city_import.py#import_city is what ties it all together

- [x] Fetch raw data from wiki voyage
- [x] Pause and wait to continue, geocode the main city coordinates
- [x] Geocode missing addresses from GPS coords
- [x] Geocode missing coordinates from addresses
- [x] find all duplicate POIs
- [x] De-duplicate POIs
- [ ] Find duplicate keys and merge them
- [ ] De-dup main city POIs
- [ ] fetch OSM ids for POIs either remote or local
- [ ] Get the Hero image and pick the best of 10
- [ ] Use LLM to generate 10 things the city is famous for, then generate list for those using POIs
- [ ] Cleanup all the descriptions using LLM

Next is creating the automatic merge logic for the POIs. What should the logic be there?
enrich_tasks.py#dedup_main_city automatically finds all "Main City" POIs, finds duplicates with detect_duplicate_pois, takes the non main city one and call /city/<city_name>/poi/merge on the two. It does this for all the Main City duplicates.
/poi/merge maps to cities/views/pois.py#poi_merge, the same endpoint used by the merge UI dialog. At least I did that correctly.
poi_merge expects a keep_poi and remove_poi. It stores the keep_poi and deletes the remove_poi. field_selections contains the fields that we want to override in keep_poi.
To automate this I need to take the results of _find_duplicates, which uses the same duplicate detection logic as the other call, and use something similar to the logic in dedup_main_city but have it use whatever values are most suitable. This would be whatever values are not null, longer if they are both present, and the highest rank
Done

Next is finding OSM ids. I need to lookup how to do that using local archive, else it will get very expensive. What was that archive? Where do I get it and how do I interact with it?

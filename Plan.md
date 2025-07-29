# Running
source .venv/bin/activate
python manage.py runserver

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
- [ ] De-duplicate POIs
- [ ] De-dup main city POIs
- [ ] fetch OSM ids for POIs either remote or local
- [ ] Get the Hero image and pick the best of 10
- [ ] Use LLM to generate 10 things the city is famous for, then generate list for those using POIs
- [ ] Cleanup all the descriptions using LLM

Next is creating the automatic merge logic for the POIs

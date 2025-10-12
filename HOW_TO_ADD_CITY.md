# Generate content
## start
```
uv run prefect server start
uv run prefect worker start --pool "import-pool"
uv run python manage.py runserver
```

Visit localhost:4200, run the "import-city" workflow. http://localhost:4200/deployments/deployment/20428ca0-4db1-4434-a424-3fd5ff1b54e2?tab=Runs
Download ./pbf dataset set from https://download.geofabrik.de/index.html
Args a re city name in wiki voyage, and relative path of pbf file
Workflow will pause at a number of steps for manual verificaion.
This will kickoff other workflows, so you need to wait for all of them to complete.

Fetch a hero image

Use /generate to create the city summary and update in the City page.
Use /generate to create lists

Fetch images for Must see and other lists
Scale the images
```
mv media/cities/images/pois/lisbon/ media/cities/images/pois/lisbon-high-res
./resize_images.sh ./media/cities/images/pois/lisbon-high-res/ ./media/cities/images/pois/lisbon
```

Export it

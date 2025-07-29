# Move tasks from Plan.md when they are done

Create the automatic merge logic for the POIs. What should the logic be there?
enrich_tasks.py#dedup_main_city automatically finds all "Main City" POIs, finds duplicates with detect_duplicate_pois, takes the non main city one and call /city/<city_name>/poi/merge on the two. It does this for all the Main City duplicates.
/poi/merge maps to cities/views/pois.py#poi_merge, the same endpoint used by the merge UI dialog. At least I did that correctly.
poi_merge expects a keep_poi and remove_poi. It stores the keep_poi and deletes the remove_poi. field_selections contains the fields that we want to override in keep_poi.
To automate this I need to take the results of _find_duplicates, which uses the same duplicate detection logic as the other call, and use something similar to the logic in dedup_main_city but have it use whatever values are most suitable. This would be whatever values are not null, longer if they are both present, and the highest rank
Done

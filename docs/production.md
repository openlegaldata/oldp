# Production

## Deployment

When pushing new changes into the production system the following routine should be performed:

 - Check unit and integration tests
 - Backup code and database
 - Stop web service `sudo supervisorctl stop oldp`
 - Pull changes from repo `git pull`
 - Run
    - Activate production environment (only on oldp1) `source commands.sh`
    - Activate Python environment `source env/bin/activate`
    - `pip install -r requirements.txt`
    - `npm install`
    - `./manage.py render_html_pages`
    - `npm run-script build`
    - `./manage.py collectstatic --no-input`
    - `./manage.py compilemessages --l de --l en`
    - `./manage.py rebuild_index` or `./manage.py update_index`
 - Run `./manage.py migrate`
 - Start web service `sudo supervisorctl start oldp`


## Commands

Commands for running OLDP in production mode.


```
./manage.py process_cases --limit 20 --empty --input /var/www/apps/oldp/data/split001/
./manage.py set_law_book_order
./manage.py set_law_book_revision
```


### Dump data

Create JSONL files from API data:

```bash
./manage.py dump_api_data ./workingdir/2020-10-10-dump/
```

## Clean up database

```
DELETE FROM cases_case;
ALTER TABLE cases_case AUTO_INCREMENT=1;

DELETE FROM cases_relatedcase;
ALTER TABLE cases_relatedcase AUTO_INCREMENT=1;


DELETE FROM courts_court;
ALTER TABLE courts_court AUTO_INCREMENT=1;

DELETE FROM courts_city;
ALTER TABLE courts_city AUTO_INCREMENT=1;

DELETE FROM courts_state;
ALTER TABLE courts_state AUTO_INCREMENT=1;


DELETE FROM courts_country;
ALTER TABLE courts_country AUTO_INCREMENT=1;


DELETE FROM references_casereferencemarker;
ALTER TABLE references_casereferencemarker AUTO_INCREMENT=1;


```

## Helper commands for migration

```
# Set missing previous law references to NULL
UPDATE laws_law
SET previous_id = NULL
WHERE id in (
    SELECT * FROM (
        select l.id
        from laws_law l
        left join laws_law p
            on p.id = l.previous_id
        WHERE l.previous_id IS NOT NULL AND p.id IS NULL
        ) as t);

```

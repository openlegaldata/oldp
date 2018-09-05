# Database

As database backend you can use all Django-supported db adapters. However, the code is only tested with MySQL and SQLite.

## Schema

![DB Schema](_static/db_schema.png)
[(Show full-size image)](_static/db_schema.png)


## Set encoding

Run the following commands to make MySQL support propper utf-8

```
ALTER TABLE logtest CONVERT TO CHARACTER SET utf8 COLLATE utf8_general_ci;

ALTER TABLE logtest DEFAULT CHARACTER SET utf8 COLLATE utf8_general_ci;

ALTER TABLE logtest CHANGE title title VARCHAR(100) CHARACTER SET utf8 COLLATE utf8_general_ci;


```

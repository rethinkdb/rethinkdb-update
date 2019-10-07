rethinkdb-update
==================

This repository contains some scripts to manage update.rethinkdb.com and the update server itself.


## Actions

* `rake update-nginx` - upload the nginx config to the server
* `rake publish` - pretend to publish the files to update.rethinkdb.com using `rsync --dry-run`
* `rake publish force=true` - actually publish the files.

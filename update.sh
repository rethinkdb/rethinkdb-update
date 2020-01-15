#!/bin/bash

set -ex

VIRTUALENV_DIR='venv'

if [ ! -d "$VIRTUALENV_DIR" ]; then
    virtualenv --no-site-package "$VIRTUALENV_DIR"
fi

source "$VIRTUALENV_DIR/bin/activate"
pip install -r requirements.txt

# start the server
(nohup bash -c "python app/update_server.py >> app.log 2>&1" & sleep 5)

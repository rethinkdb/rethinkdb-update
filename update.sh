#!/bin/bash

set -ex

VIRTUALENV_DIR='venv'

if [ ! -d "$VIRTUALENV_DIR" ]; then
    virtualenv --no-site-package "$VIRTUALENV_DIR"
fi

source "$VIRTUALENV_DIR/bin/activate"
pip install -r requirements.txt

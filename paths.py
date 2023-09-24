"""
Single handy place for paths.
"""

import os
from os.path import dirname, abspath, relpath, join
import functools

import bottle
from bottle import jinja2_view

HOME = os.getenv('HOME')
if HOME is None:
    HOME = ''

ROOT_DIR = dirname(abspath(__file__))
STATIC_DIR = join(ROOT_DIR, 'static')
TEMPLATE_DIR = join(ROOT_DIR, 'templates')
TEST_DIR = join(ROOT_DIR, 'tests')
TEST_DATA_DIR = join(ROOT_DIR, 'tests', 'data')
SCHEMA_FILE = join(ROOT_DIR, 'etc', 'schema.sql')
BOTTLE_APP_PATH = join(ROOT_DIR, 'bottle_app.py')
BOTTLE_APP_INI_PATH = join(ROOT_DIR, 'bottle_app.ini')

PLANTTRACER_ENDPOINT = os.environ['PLANTTRACER_ENDPOINT']
BOTTlE_APP_INI_PATH = join(ROOT_DIR, 'bottle_app.ini')
# Add the relative template path (since jinja2 doesn't like absolute paths)
bottle.TEMPLATE_PATH.append(relpath(TEMPLATE_DIR))

# Database credentials
DBCREDENTIALS_PATH = join(HOME, 'planttracer.ini')
if not os.path.exists(DBCREDENTIALS_PATH):
    DBCREDENTIALS_PATH = join(HOME, 'plant_dev.ini')
if not os.path.exists(DBCREDENTIALS_PATH):
    DBCREDENTIALS_PATH = None

DBREADER_BASH_PATH = join(HOME, 'plant_dev.bash')
if not os.path.exists(DBREADER_BASH_PATH):
    DBREADER_BASH_PATH = join(HOME, 'plant_app.bash')

DBWRITER_BASH_PATH = join(HOME, 'plant_dev.bash')
if not os.path.exists(DBWRITER_BASH_PATH):
    DBWRITER_BASH_PATH = join(HOME, 'plant_app.bash')

# Create the @view decorator to add template to the function output
view = functools.partial(jinja2_view)

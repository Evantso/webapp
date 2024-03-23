"""
WSGI file used for bottle interface.

The goal is to only have the bottle code in this file and nowhere else.

Debug on Dreamhost:
(cd ~/apps.digitalcorpora.org/;make touch)
https://downloads.digitalcorpora.org/
https://downloads.digitalcorpora.org/ver
https://downloads.digitalcorpora.org/reports

Debug locally:

$ python bottle_app.py
Bottle v0.12.23 server starting up (using WSGIRefServer())...
Listening on http://localhost:8080/
Hit Ctrl-C to quit.

Then go to the URL printed above (e.g. http://localhost:8080). Note that you must have the environment variables set:
export MYSQL_DATABASE=***
export MYSQL_HOST=***
export MYSQL_PASSWORD=***
export MYSQL_USER=***
export SMTP_HOST=***
export SMTP_PASSWORD=***
export SMTP_PORT=***
export SMTP_USERNAME=***

For testing, you must also set:
export IMAP_PASSWORD=****
export IMAP_SERVER=****
export IMAP_USERNAME=****
export TEST_ENDPOINT='http://localhost:8080' (or whatever it is above)

For automated tests, we are using the localmail server.

And you will need a valid user in the current databse (or create your own with dbutil.py)
export TEST_USER_APIKEY=****
export TEST_USER_EMAIL=****
"""

# pylint: disable=too-many-lines
# pylint: disable=too-many-return-statements

import sys
import os
import io
import json
import time
import functools
import logging
import base64
import csv
import tempfile
import subprocess
import smtplib
from urllib.parse import urlparse
from collections import defaultdict

import filetype
import bottle
from bottle import request
from validate_email_address import validate_email

# Bottle creates a large number of no-member errors, so we just remove the warning
# pylint: disable=no-member

from lib.ctools import clogging

import db
import auth
from auth import get_dbreader

from paths import view, STATIC_DIR
from constants import C,E,__version__,GET,POST,GET_POST

import bottle_api
from bottle_api import expand_memfile_max,is_true,git_head_time,git_last_commit,get,get_json,get_int,get_float,get_bool,fix_types

import mailer
import tracker

DEFAULT_OFFSET = 0
DEFAULT_SEARCH_ROW_COUNT = 1000
MIN_SEND_INTERVAL = 60
DEFAULT_CAPABILITIES = ""
LOAD_MESSAGE = "Error: JavaScript did not execute. Please open JavaScript console and report a bug."

CHECK_MX = False                # True didn't work

app = bottle.default_app()      # for Lambda
app.mount('/api', bottle_api.api)

################################################################
# Bottle endpoints


# Local Static

# Disable caching during development.
# https://stackoverflow.com/questions/24672996/python-bottle-and-cache-control
# "Note: If there is a Cache-Control header with the max-age or s-maxage directive in the response,
#  the Expires header is ignored."
# "https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Expires
# Unfortunately, we are getting duplicate cache-control headers.
# So better to disable in the client:
# https://www.webinstinct.com/faq/how-to-disable-browser-cache


@bottle.route('/static/<path:path>', method=['GET'])
def static_path(path):
    try:
        kind = filetype.guess(os.path.join(STATIC_DIR,path))
    except FileNotFoundError:
        raise bottle.HTTPResponse(body=f'Error 404: File not found: {path}', status=404)
    mimetype = kind.mime if kind else 'text/plain'
    response = bottle.static_file( path, root=STATIC_DIR, mimetype=mimetype )
    response.set_header('Cache-Control', 'public, max-age=5')
    return response

@bottle.route('/favicon.ico', method=['GET'])
def favicon():
    return static_path('favicon.ico')

def get_user_dict():
    """Returns the user_id of the currently logged in user, or throws a response"""
    api_key = auth.get_user_api_key()
    if api_key is None:
        logging.info("api_key is none")
        # This will redirect to the / and produce a "Session expired" message
        raise bottle.HTTPResponse(body='', status=301, headers={ 'Location': '/'})
    userdict = db.validate_api_key(api_key)
    if not userdict:
        logging.info("api_key %s ipaddr %s is invalid  request.url=%s",api_key,request.environ.get('REMOTE_ADDR'),request.url)
        auth.clear_cookie()
        # This will produce a "Session expired" message
        if request.url.endswith("/error"):
            raise bottle.HTTPResponse(body='', status=301, headers={ 'Location': '/logout'})
        raise bottle.HTTPResponse(body='', status=301, headers={ 'Location': '/error'})
    return userdict

def get_user_id(allow_demo=True):
    """Returns the user_id of the currently logged in user, or throws a response.
    if allow_demo==False, then do not allow the user to be a demo user
    """
    userdict = get_user_dict()
    if 'id' not in userdict:
        logging.info("no ID in userdict = %s", userdict)
        raise bottle.HTTPResponse(body='user_id is not valid', status=501, headers={ 'Location': '/'})
    if userdict['demo'] and not allow_demo:
        logging.info("demo account blocks requeted action")
        raise bottle.HTTPResponse(body='{"Error":true,"message":"demo accounts not allowed to execute requested action."}',
                                  status=503, headers={ 'Location': '/'})
    return userdict['id']


################################################################
# HTML Pages served with template system
################################################################

def page_dict(title='', *, require_auth=False, logout=False, lookup=True):
    """Returns a dictionary that can be used by post of the templates.
    :param: title - the title we should give the page
    :param: require_auth  - if true, the user must already be authenticated, or throws an error
    :param: logout - if true, force the user to log out by issuing a clear-cookie command
    """
    logging.debug("page_dict require_auth=%s logout=%s lookup=%s",require_auth,logout,lookup)
    o = urlparse(request.url)
    if lookup:
        api_key = auth.get_user_api_key()
        if api_key is None and require_auth is True:
            logging.debug("api_key is None and require_auth is True")
            raise bottle.HTTPResponse(body='', status=303, headers={ 'Location': '/'})
    else:
        api_key = None

    if (api_key is not None) and (logout is False):
        auth.set_cookie(api_key)
        user_dict = get_user_dict()
        user_name = user_dict['name']
        user_email = user_dict['email']
        user_demo  = user_dict['demo']
        user_id = user_dict['id']
        user_primary_course_id = user_dict['primary_course_id']
        primary_course_name = db.lookup_course(course_id=user_primary_course_id)['course_name']
        admin = db.check_course_admin(user_id=user_id, course_id=user_primary_course_id)
        # If this is a demo account, the user cannot be an admin
        if user_demo:
            assert not admin

    else:
        user_name  = None
        user_email = None
        user_demo  = 0
        user_id    = None
        user_primary_course_id = None
        primary_course_name = None
        admin = None

    try:
        movie_id = int(request.query.get('movie_id'))
    except (AttributeError, KeyError, TypeError):
        movie_id = 0            # to avoid errors

    if logout:
        auth.clear_cookie()

    logging.debug("returning dict")
    return {'api_key': api_key,
            'user_id': user_id,
            'user_name': user_name,
            'user_email': user_email,
            'user_demo':  user_demo,
            'admin':admin,
            'user_primary_course_id': user_primary_course_id,
            'primary_course_name': primary_course_name,
            'title':'Plant Tracer '+title,
            'hostname':o.hostname,
            'movie_id':movie_id,
            'MAX_FILE_UPLOAD': C.MAX_FILE_UPLOAD,
            'dbreader_host':get_dbreader().host,
            'version':__version__,
            'git_head_time':git_head_time(),
            'git_last_commit':git_last_commit()}


@bottle.route('/', method=GET_POST)
@view('index.html')
def func_root():
    """/ - serve the home page"""
    logging.info("func_root")
    demo_users = db.list_demo_users()
    demo_api_key = False
    if len(demo_users)>0:
        demo_api_key   = demo_users[0].get('api_key',False)
        logging.debug("demo_api_key=%s",demo_api_key)
    return {**page_dict(),
            **{'demo_api_key':demo_api_key}}

@bottle.route('/about', method=GET_POST)
@view('about.html')
def func_about():
    return page_dict('About')

@bottle.route('/error', method=GET_POST)
@view('error.html')
def func_error():
    logging.debug("/error")
    auth.clear_cookie()
    return page_dict('Error', lookup=False)

@bottle.route('/audit', method=GET_POST)
@view('audit.html')
def func_audit():
    """/audit - view the audit logs"""
    return page_dict("Audit", require_auth=True)

@bottle.route('/list', method=GET_POST)
@view('list.html')
def func_list():
    """/list - list movies and edit them and user info"""
    return page_dict('List Movies', require_auth=True)

@bottle.route('/analyze', method=GET)
@view('analyze.html')
def func_analyze():
    """/analyze?movie_id=<movieid> - Analyze a movie, optionally annotating it."""
    return page_dict('Analyze Movie', require_auth=True)

##
## Login page includes the api keys of all the demo users.
##
@bottle.route('/login', method=GET_POST)
@view('login.html')
def func_login():
    demo_users = db.list_demo_users()
    logging.debug("demo_users=%s",demo_users)
    demo_api_key = False
    if len(demo_users)>0:
        demo_api_key   = demo_users[0].get('api_key',False)

    return {**page_dict('Login'),
            **{'demo_api_key':demo_api_key}}

@bottle.route('/logout', method=GET_POST)
@view('logout.html')
def func_logout():
    """/list - list movies and edit them and user info"""
    return page_dict('Logout',logout=True)

@bottle.route('/privacy', method=GET_POST)
@view('privacy.html')
def func_privacy():
    return page_dict('Privacy')

@bottle.route('/register', method=GET)
@view('register.html')
def func_register():
    """/register sends the register.html template which loads register.js with register variable set to True
     Note: register and resend both need the endpint so that they can post it to the server
     for inclusion in the email. This is the only place where the endpoint needs to be explicitly included.
    """
    o = urlparse(request.url)
    return {'title': 'Plant Tracer Registration Page',
            'hostname': o.hostname,
            'register': True
            }

@bottle.route('/resend', method=GET)
@view('register.html')
def func_resend():
    """/resend sends the register.html template which loads register.js with register variable set to False"""
    o = urlparse(request.url)
    return {'title': 'Plant Tracer Resend Registration Link',
            'hostname': o.hostname,
            'register': False
            }


@bottle.route('/tos', method=GET_POST)
@view('tos.html')
def func_tos():
    return page_dict('Terms of Service')

@bottle.route('/upload', method=GET_POST)
@view('upload.html')
def func_upload():
    """/upload - Upload a new file"""
    return page_dict('Upload a Movie', require_auth=True)

@bottle.route('/users', method=GET_POST)
@view('users.html')
def func_users():
    """/users - provide a users list"""
    return page_dict('List Users', require_auth=True)

@bottle.route('/ver', method=GET_POST)
@view('version.txt')
def func_ver():
    """Demo for reporting python version. Allows us to validate we are using Python3.
    Run the dictionary below through the VERSION_TEAMPLTE with jinja2.
    """
    return {'__version__': __version__, 'sys_version': sys.version}


################################################################
# Bottle App
##

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Run Bottle App with Bottle's built-in server unless a command is given",
                                     formatter_class=argparse.ArgumentDefaultsHelpFormatter)

    parser.add_argument( '--dbcredentials', help='Specify .ini file with [dbreader] and [dbwriter] sections')
    parser.add_argument('--port', type=int, default=8080)
    parser.add_argument('--multi', help='Run multi-threaded server (no auto-reloader)', action='store_true')
    clogging.add_argument(parser, loglevel_default='WARNING')
    args = parser.parse_args()
    clogging.setup(level=args.loglevel)

    if args.dbcredentials:
        os.environ[C.DBCREDENTIALS_PATH] = args.dbcredentials

    # Now make sure that the credentials work
    # We only do this with the standalone program
    # the try/except is for when we run under a fixture in the pytest unit tests, which messes up ROOT_DIR
    try:
        from tests.dbreader_test import test_db_connection
        test_db_connection()
    except ModuleNotFoundError:
        pass

    if args.multi:
        import wsgiserver
        httpd = wsgiserver.Server(app, listen='localhost', port=args.port)
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("")
            sys.exit(0)

    bottle.default_app().run(host='localhost', debug=True, reloader=True, port=args.port)

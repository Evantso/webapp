"""
WSGI file used for bottle interface.

The goal is to only have the bottle code in this file and nowhere else.

Debug on Dreamhost:
(cd ~/apps.digitalcorpora.org/;make touch)
https://downloads.digitalcorpora.org/
https://downloads.digitalcorpora.org/ver
https://downloads.digitalcorpora.org/reports

Debug locally:

"""

import sys
import os
import datetime
import logging
from urllib.parse import urlparse

import mistune
import magic
import bottle
from bottle import request
from validate_email_address import validate_email

# pylint: disable=no-member


import db
from paths import STATIC_DIR,TEMPLATE_DIR,view
from lib.ctools import clogging

assert os.path.exists(TEMPLATE_DIR)

__version__='0.0.1'
VERSION_TEMPLATE='version.txt'

TOS_MD_FILE     = os.path.join(STATIC_DIR, 'tos.md')
PRIVACY_MD_FILE = os.path.join(STATIC_DIR, 'privacy.md')
PAGE_TEMPLATE   = 'page.html'
PAGE_STYLE = "<style>\ndiv.mypage { max-width: 600px;}\n</style>\n"

DEFAULT_OFFSET = 0
DEFAULT_ROW_COUNT = 1000000
DEFAULT_SEARCH_ROW_COUNT = 1000
MIN_SEND_INTERVAL = 60
DEFAULT_CAPABILITIES = ""

NEW_MEMFILE_MAX = 1024*1024*16

INVALID_API_KEY = {'error':True, 'message':'Invalid api_key'}
INVALID_EMAIL  = {'error':True, 'message':'Invalid email address'}
INVALID_MOVIE_ACCESS = {'error':True, 'message':'User does not have access to requested movie.'}
INVALID_COURSE_KEY = {'error':True, 'message':'There is no course for that course key.'}
NO_REMAINING_REGISTRATIONS = {'error':True, 'message':'That course has no remaining registrations. Please contact your faculty member.'}

def expand_memfile_max():
    logging.info("Changing MEMFILE_MAX from %d to %d",bottle.BaseRequest.MEMFILE_MAX, NEW_MEMFILE_MAX)
    bottle.BaseRequest.MEMFILE_MAX = NEW_MEMFILE_MAX


def datetime_to_str(obj):
    if isinstance(obj, datetime.datetime):
        return obj.isoformat()  # or str(obj) if you prefer
    elif isinstance(obj, dict):
        return {k: datetime_to_str(v) for k, v in obj.items()}
    elif isinstance(obj, (list, tuple)):
        return [datetime_to_str(elem) for elem in obj]
    else:
        return obj

################################################################
## Bottle endpoints


@bottle.route('/ver', method=['POST','GET'])
@view(VERSION_TEMPLATE)         # run the dictionary below through the VERSION_TEAMPLTE with jinja2
def func_ver():
    """Demo for reporting python version. Allows us to validate we are using Python3"""
    return {'__version__':__version__,'sys_version':sys.version}

@bottle.route('/tos', method=['GET'])
@view(PAGE_TEMPLATE)
def func_tos():
    """Fill the page template with the terms of service produced with markdown to HTML translation"""
    with open(TOS_MD_FILE,"r") as f:
        return {'page':mistune.html(f.read()), 'style':PAGE_STYLE }

@bottle.route('/privacy', method=['GET'])
@view(PAGE_TEMPLATE)
def func_privacy():
    """Fill the page template with the terms of service produced with markdown to HTML translation"""
    with open(PRIVACY_MD_FILE,"r") as f:
        return {'page':mistune.html(f.read()), 'style':PAGE_STYLE }

### Local Static
@bottle.get('/static/<path:path>')
def static_path(path):
    return bottle.static_file(path, root=STATIC_DIR, mimetype=magic.from_file(os.path.join(STATIC_DIR,path)))

## TEMPLATE VIEWS
@bottle.route('/')
@view('index.html')
def func_root():
    o = urlparse(request.url)
    return {'title':'ROOT',
            'hostname':o.hostname}

@bottle.route('/register')
@view('register.html')
def func_register():
    o = urlparse(request.url)
    return {'title':'ROOT',
            'hostname':o.hostname,
            'register':True
            }

@bottle.route('/resend')
@view('register.html')
def func_resend():
    o = urlparse(request.url)
    return {'title':'ROOT',
            'hostname':o.hostname,
            'register':False
            }


################################################################
## API

@bottle.route('/api/check-api_key', method='POST')
def api_check_api_key( api_key ):
    userdict = db.validate_api_key( request.forms.get('api_key') )
    logging.info( "api_key[0:9]=%s userdict=%s", api_key[0:9], userdict )
    if userdict:
        return { 'error':False, 'userinfo': datetime_to_str( userdict ) }
    return INVALID_API_KEY


################################################################
## Registration
@bottle.route('/api/register', method='POST')
def api_register():
    """Register the email address if it does not exist. Send a login and upload link"""
    email = request.forms.get('email')
    if not validate_email(email, check_mx=True):
        return INVALID_EMAIL
    course_key = request.forms.get('course_key')
    if not db.validate_course_key( course_key ):
        return INVALID_COURSE_KEY
    if db.remaining_course_registrations( course_key ) < 1:
        return NO_REMAINING_REGISTRATIONS
    db.register_email( email, course_key )
    db.send_links( email )
    return {'error':False}


@bottle.route('/api/resend-link', method='POST')
def api_send_link():
    """Register the email address if it does not exist. Send a login and upload link"""
    email = request.forms.get('email')
    if not validate_email(email, check_mx=True):
        return INVALID_EMAIL
    db.send_links(email)
    return {'error':False}




################################################################
## Movies
@bottle.route('/api/new-movie', method='POST')
def api_new_movie():
    """Creates a new movie for which we can upload frame-by-frame or all at once.
    :param api_key: the user's api_key
    :param title: The movie's title
    :param description: The movie's description
    :param base64_data: If present, the movie data.
    """

    user_id = db.validate_api_key( request.forms.get('api_key') )
    if user_id:
        movie_id = db.create_new_movie( user_id, request.forms.get('title'), request.forms.get('description'), request.forms.get('movie_base64_data'))
        return {'error':False,'movie_id':movie_id}
    return INVALID_API_KEY

@bottle.route('/api/new-frame', method='POST')
def api_new_frame():
    user_id = db.validate_api_key( request.forms.get('api_key'))
    if user_id:
        frame_id = db.create_new_frame( user_id, request.forms.get('movie_id'), request.forms.get('frame_msec'), request.forms.get('frame_base64_data'))
        if not frame_id:
            return INVALID_MOVIE_ACCESS
        return {'error':False,'frame_id':frame_id}
    return INVALID_API_KEY

@bottle.route('/api/delete-movie', method='POST')
def api_delete_movie():
    """ delete a movie
    :param movie_id: the id of the movie to delete
    :param delete: 1 (default) to delete the movie, 0 to undelete the movie.
    """
    user_id = db.validate_api_key( request.forms.get('api_key'))
    if user_id:
        db.delete_movie( request.forms.get('movie_id'), request.forms.get('delete',1) )
        return {'error':False}
    return INVALID_API_KEY

@bottle.route('/api/list-movies', method=['POST','GET'])
def api_list_movies():
    user_id = db.validate_api_key( request.forms.get('api_key'))
    if user_id:
        movies = db.list_movies( user_id )
        return {'error':False, 'movies':movies}
    return INVALID_API_KEY


################################################################
## Demo and debug
@bottle.route('/api/add', method='POST')
def api_add():
    a = request.forms.get('a')
    b = request.forms.get('b')
    try:
        return {'result':float(a)+float(b), 'error':False}
    except (TypeError,ValueError):
        return {'error':True}

################################################################
## App


def app():
    """The application"""
    # Set up logging for a bottle app
    # https://stackoverflow.com/questions/2557168/how-do-i-change-the-default-format-of-log-messages-in-python-app-engine
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    #root.setLevel(logging.DEBUG)
    hdlr = root.handlers[0]
    fmt = logging.Formatter(clogging.LOG_FORMAT)
    hdlr.setFormatter(fmt)

    expand_memfile_max()
    return bottle.default_app()

if __name__=="__main__":
    bottle.default_app().run(host='localhost',debug=True, reloader=True)

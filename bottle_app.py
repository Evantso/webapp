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

import sys
import os
import io
import datetime
import logging
import base64
from urllib.parse import urlparse

import magic
import bottle
from bottle import request
from validate_email_address import validate_email

# pylint: disable=no-member

import db
import paths
import auth

from paths import view, STATIC_DIR, TEMPLATE_DIR
from lib.ctools import clogging
from errors import INVALID_API_KEY,INVALID_EMAIL,INVALID_MOVIE_ACCESS,INVALID_COURSE_KEY,NO_REMAINING_REGISTRATIONS,NO_EMAIL_REGISTER

assert os.path.exists(TEMPLATE_DIR)

__version__ = '0.0.1'

DEFAULT_OFFSET = 0
DEFAULT_ROW_COUNT = 1000000
DEFAULT_SEARCH_ROW_COUNT = 1000
MIN_SEND_INTERVAL = 60
DEFAULT_CAPABILITIES = ""
LOAD_MESSAGE = "Error: JavaScript did not execute. Please open JavaScript console and report a bug."
MAX_FILE_UPLOAD = 1024*1024*16

CHECK_MX = False                # True didn't work


def expand_memfile_max():
    logging.info("Changing MEMFILE_MAX from %d to %d",
                 bottle.BaseRequest.MEMFILE_MAX, MAX_FILE_UPLOAD)
    bottle.BaseRequest.MEMFILE_MAX = MAX_FILE_UPLOAD


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
    response = bottle.static_file(
        path, root=STATIC_DIR, mimetype=magic.from_file(os.path.join(STATIC_DIR, path)))
    response.set_header('Cache-Control', 'public, max-age=5')
    return response


@bottle.route('/favicon.ico', method=['GET'])
def favicon():
    static_path('favicon.ico')

def get_user_dict():
    """Returns the user_id of the currently logged in user, or throws a response"""
    api_key = auth.get_user_api_key()
    if api_key is None:
        logging.warning("api_key is none")
        raise bottle.HTTPResponse(body='', status=303, headers={ 'Location': '/'})
    userdict = db.validate_api_key(api_key)
    if not userdict:
        logging.warning("api_key %s is invalid",api_key)
        raise bottle.HTTPResponse(body='', status=303, headers={ 'Location': '/error'})
    return userdict

def get_user_id():
    """Returns the user_id of the currently logged in user, or throws a response"""
    userdict = get_user_dict()
    if 'id' not in userdict:
        logging.warning("no ID in userdict = %s", userdict)
        raise bottle.HTTPResponse(body='', status=303, headers={ 'Location': '/'})
    return userdict['id']


################################################################
# HTML Pages served with template system
################################################################

def page_dict(title='Plant Tracer', *, require_auth=False, logout=False):
    """Fill in data that goes to templates below and also set the cookie in a response
    :param: title - the title we should give the page
    :param: auth  - if true, the user must already be authenticated
    :param: logout - if true, log out the user
    """
    o = urlparse(request.url)
    api_key = auth.get_user_api_key()
    if api_key is None and require_auth is True:
        raise bottle.HTTPResponse(body='', status=303, headers={ 'Location': '/'})

    if (api_key is not None) and (logout is False):
        auth.set_cookie(api_key)
        user_dict = get_user_dict()
        user_name = user_dict['name']
        user_email = user_dict['email']
        user_id = user_dict['id']
        user_primary_course_id = user_dict['primary_course_id']
        primary_course_name = db.lookup_course(course_id=user_primary_course_id)['course_name']
        admin = db.check_course_admin(user_id=user_id, course_id=user_primary_course_id)
    else:
        user_name = None
        user_email = None
        user_id = None
        user_primary_course_id = None
        primary_course_name = None
        admin = None

    try:
        movie_id = int(request.query.get('movie_id'))
    except (AttributeError, KeyError, TypeError):
        movie_id = None

    if logout:
        auth.clear_cookie()

    return {'api_key': api_key,
            'user_id': user_id,
            'user_name': user_name,
            'user_email': user_email,
            'admin':admin,
            'user_primary_course_id': user_primary_course_id,
            'primary_course_name': primary_course_name,
            'title':'Plant Tracer '+title,
            'hostname':o.hostname,
            'movie_id':movie_id,
            'MAX_FILE_UPLOAD': MAX_FILE_UPLOAD}

GET='GET'
POST='POST'
GET_POST = [GET,POST]

@bottle.route('/', method=GET_POST)
@view('index.html')
def func_root():
    """/ - serve the home page"""
    return page_dict()

@bottle.route('/error', method=GET_POST)
@view('error.html')
def func_error():
    auth.clear_cookie()
    return {}



@bottle.route('/about', method=GET_POST)
@view('about.html')
def func_about():
    return page_dict('About')

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

@bottle.route('/login', method=GET_POST)
@view('login.html')
def func_login():
    return page_dict('Login')

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
# /api URLs
################################################################


@bottle.route('/api/check-api_key', method=['GET', 'POST'])
def api_check_api_key():
    """API to check the user key and, if valid, return usedict or returns an error."""

    userdict = db.validate_api_key(auth.get_user_api_key())
    if userdict:
        return {'error': False, 'userinfo': datetime_to_str(userdict)}
    return INVALID_API_KEY


@bottle.route('/api/get-logs', method=['POST'])
def api_get_logs():
    """Get logs and return in JSON. The database function does all of the security checks, but we need to have a valid user."""
    kwargs = {}
    for kw in ['start_time','end_time','course_id','course_key',
               'movie_id','log_user_id','ipaddr','count','offset']:
        if kw in request.forms.keys():
            kwargs[kw] = request.forms.get(kw)

    logs    = db.get_logs(user_id=get_user_id(),**kwargs)
    return {'error':False, 'logs': logs}

@bottle.route('/api/register', method=['GET', 'POST'])
def api_register():
    """Register the email address if it does not exist. Send a login and upload link"""
    email = request.forms.get('email')
    planttracer_endpoint = request.forms.get('planttracer_endpoint')
    if not validate_email(email, check_mx=False):
        logging.warning("email not valid: %s", email)
        return INVALID_EMAIL
    course_key = request.forms.get('course_key')
    if not db.validate_course_key(course_key=course_key):
        return INVALID_COURSE_KEY
    if db.remaining_course_registrations(course_key=course_key) < 1:
        return NO_REMAINING_REGISTRATIONS
    name = request.forms.get('name')
    db.register_email(email=email, course_key=course_key, name=name)
    db.send_links(email=email, planttracer_endpoint=planttracer_endpoint)
    return {'error': False, 'message': 'Registration key sent to '+email}

@bottle.route('/api/resend-link', method=['GET', 'POST'])
def api_send_link():
    """Register the email address if it does not exist. Send a login and upload link"""
    email = request.forms.get('email')
    planttracer_endpoint = request.forms.get('planttracer_endpoint')
    logging.info("/api/resend-link email=%s planttracer_endpoint=%s",email,planttracer_endpoint)
    if not validate_email(email, check_mx=CHECK_MX):
        logging.warning("email not valid: %s", email)
        return INVALID_EMAIL
    db.send_links(email=email, planttracer_endpoint=planttracer_endpoint)
    return {'error': False, 'message': 'If you have an account, a link was sent. If you do not receive a link within 60 seconds, you may need to <a href="/register">register</a> your email address.'}

@bottle.route('/api/bulk-register', method=['POST'])
def api_bulk_register():
    """Allow an admin to register people in the class, increasing the class size as necessary to do so."""
    course_id =  int(request.forms.get('course_id'))
    user_id   = get_user_id()
    planttracer_endpoint = request.forms.get('planttracer_endpoint')
    if not db.check_course_admin(course_id = course_id, user_id=user_id):
        return INVALID_COURSE_ACCESS

    email_addresses = request.forms.get('email-addresses').replace(","," ").replace(";"," ").replace(" ","\n").split("\n")
    for email in email_addresses:
        if not validate_email(email, check_mx=CHECK_MX):
            return INVALID_EMAIL
        db.register_email(email=email, course_id=course_id, name="")
        db.send_links(email=email, planttracer_endpoint=planttracer_endpoint)
    return {'error':False, 'message':f'Registered {count} email addresses'}

##
# Movie APIs. All of these need to only be POST to avoid an api_key from being written into the logfile
##


@bottle.route('/api/new-movie', method='POST')
def api_new_movie():
    """Creates a new movie for which we can upload frame-by-frame or all at once.
    :param api_key: the user's api_key
    :param title: The movie's title
    :param description: The movie's description
    :param movie: If present, the movie file
    """

    # pylint: disable=unsupported-membership-test
    movie_data = None
    # First see if a file named movie was uploaded
    if 'movie' in request.files:
        with io.BytesIO() as f:
            request.files['movie'].save(f)
            movie_data = f.getvalue()
            if len(movie_data) > MAX_FILE_UPLOAD:
                return {'error': True, 'message': f'Upload larger than larger than {MAX_FILE_UPLOAD} bytes.'}
        logging.debug("api_new_movie: movie uploaded as a file")

    # Now check to see if it is in the post
    if movie_data is None:
        movie_data = request.forms.get('movie_data',None)
        logging.debug("api_new_movie: movie_data from request.forms.get")
    else:
        logging.debug("api_new_movie: movie_data is None")


    if (movie_data is not None) and (len(movie_data) > MAX_FILE_UPLOAD):
        logging.debug("api_new_movie: movie length %s bigger than %s",len(movie_data), MAX_FILE_UPLOAD)
        return {'error': True, 'message': f'Upload larger than larger than {MAX_FILE_UPLOAD} bytes.'}

    movie_id = db.create_new_movie(user_id=get_user_id(),
                                   title=request.forms.get('title'),
                                   description=request.forms.get('description'),
                                   movie_data=movie_data)['movie_id']
    return {'error': False, 'movie_id': movie_id}


@bottle.route('/api/new-frame', method='POST')
def api_new_frame():
    if db.can_access_movie(user_id=get_user_id(), movie_id=request.forms.get('movie_id')):
        frame_data = base64.b64decode( request.forms.get('frame_base64_data'))
        res = db.create_new_frame( movie_id = request.forms.get('movie_id'),
                                   frame_msec = request.forms.get('frame_msec'),
                                   frame_data = frame_data)
        frame_id = res['frame_id']
        return {'error': False, 'frame_id': frame_id}
    return INVALID_MOVIE_ACCESS


@bottle.route('/api/get-frame', method='POST')
def api_get_frame():
    """
    :param api_keuy:   authentication
    :param movie_id:   movie
    :param frame_msec: the frame specified
    :param msec_delta:      0 - this frame; +1 - next frame; -1 is previous frame
    :return:
    """
    if db.can_access_movie(user_id=get_user_id(), movie_id=request.forms.get('movie_id')):
        return {'error': False, 'frame': db.get_frame(movie_id=request.forms.get('movie_id'),
                                                      frame_msec = request.forms.get('frame_msec'),
                                                      msec_delta = request.forms.get('msec_delta'))}
    return INVALID_MOVIE_ACCESS


@bottle.route('/api/get-movie-data', method=['POST','GET'])
def api_get_movie_data():
    """
    :param api_keuy:   authentication
    :param movie_id:   movie
    """
    if db.can_access_movie(user_id=get_user_id(), movie_id=auth.get_movie_id()):
        bottle.response.set_header('Content-Type', 'video/quicktime')
        return db.get_movie(movie_id=auth.get_movie_id())
    return INVALID_MOVIE_ACCESS


@bottle.route('/api/delete-movie', method='POST')
def api_delete_movie():
    """ delete a movie
    :param movie_id: the id of the movie to delete
    :param delete: 1 (default) to delete the movie, 0 to undelete the movie.
    """
    if db.can_access_movie(user_id=get_user_id(), movie_id=request.forms.get('movie_id')):
        db.delete_movie(movie_id=request.forms.get('movie_id'),
                        delete=request.forms.get('delete', 1))
        return {'error': False}
    return INVALID_MOVIE_ACCESS


@bottle.route('/api/list-movies', method=['POST'])
def api_list_movies():
    return {'error': False, 'movies': db.list_movies(get_user_id())}



##
# Log API
#
@bottle.route('/api/get-log', method=['POST'])
def api_get_log():
    """TODO: Add additional fields"""
    return {'error':False, 'logs': db.get_log(user_id=get_user_id()) }

##
# Metadata
##


def converter(x):
    if (x == 'null') or (x is None):
        return None
    return int(x)


@bottle.route('/api/get-metadata', method='POST')
def api_get_metadata():
    gmovie_id = converter(request.forms.get('get_movie_id'))
    guser_id = converter(request.forms.get('get_user_id'))

    if (gmovie_id is None) and (guser_id is None):
        return {'error': True, 'result': 'Either get_movie_id or get_user_id is required'}

    return {'error': False, 'result': db.get_metadata(user_id=get_user_id(),
                                                      get_movie_id=gmovie_id,
                                                      get_user_id=guser_id,
                                                      property=request.forms.get(
                                                          'property'),
                                                      value=request.forms.get('value'))}


@bottle.route('/api/set-metadata', method='POST')
def api_set_metadata():
    """ set some aspect of the metadata
    :param api_key: authorization key
    :param movie_id: movie ID - if present, we are setting movie metadata
    :param user_id:  user ID  - if present, we are setting user metadata. (May not be the user_id from the api key)
    :param prop: which piece of metadata to set
    :param value: what to set it to
    """
    logging.warning("request.forms=%s", list(request.forms.keys()))
    logging.warning("api_key=%s", request.forms.get('api_key'))
    logging.warning("get_user_id()=%s", get_user_id())

    set_movie_id = converter(request.forms.get('set_movie_id'))
    set_user_id = converter(request.forms.get('set_user_id'))

    if (set_movie_id is None) and (set_user_id is None):
        return {'error': True, 'result': 'Either set_movie_id or set_user_id is required'}

    result = db.set_metadata(user_id=get_user_id(),
                             set_movie_id=set_movie_id,
                             set_user_id=set_user_id,
                             prop=request.forms.get('property'),
                             value=request.forms.get('value'))

    return {'error': False, 'result': result}


##
## All of the users that this person can see
##
@bottle.route('/api/list-users', method=['POST'])
def api_list_users():
    return {**{'error': False}, **db.list_users(user_id=get_user_id())}


##
## Demo and debug
##
@bottle.route('/api/add', method=['GET', 'POST'])
def api_add():
    a = request.forms.get('a')
    b = request.forms.get('b')
    try:
        return {'result': float(a)+float(b), 'error': False}
    except (TypeError, ValueError):
        return {'error': True, 'message': 'arguments malformed'}

################################################################
# Bottle App
##


def app():
    """The application"""
    # Set up logging for a bottle app
    # https://stackoverflow.com/questions/2557168/how-do-i-change-the-default-format-of-log-messages-in-python-app-engine
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    # root.setLevel(logging.DEBUG)
    hdlr = root.handlers[0]
    fmt = logging.Formatter(clogging.LOG_FORMAT)
    hdlr.setFormatter(fmt)

    expand_memfile_max()
    return bottle.default_app()


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Run Bottle App with Bottle's built-in server unless a command is given",
                                     formatter_class=argparse.ArgumentDefaultsHelpFormatter)

    parser.add_argument(
        '--dbcredentials', help='Specify .ini file with [dbreader] and [dbwriter] sections')
    parser.add_argument('--port', type=int, default=8080)
    clogging.add_argument(parser, loglevel_default='WARNING')
    args = parser.parse_args()
    clogging.setup(level=args.loglevel)

    if args.dbcredentials:
        if not os.path.exists(args.dbcredentials):
            raise FileNotFoundError(args.dbcredentials)
        paths.BOTTLE_APP_INI = args.dbcredentials
    bottle.default_app().run(host='localhost', debug=True, reloader=True, port=args.port)

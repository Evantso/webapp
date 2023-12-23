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
import json
import datetime
import logging
import base64
#import copy
import tempfile
from urllib.parse import urlparse
from collections import defaultdict

import magic
import bottle
from bottle import request
from validate_email_address import validate_email


# Bottle creates a large number of no-member errors, so we just remove the warning
# pylint: disable=no-member

import numpy as np

from lib.ctools import clogging

import db
import auth

from paths import view, STATIC_DIR
from constants import C,E
import mailer
import tracker

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
    """Given an object that might be a dictionary, convert all datetime objects to JSON strings"""
    if isinstance(obj, datetime.datetime):
        return obj.isoformat()  # or str(obj) if you prefer
    elif isinstance(obj, dict):
        return {k: datetime_to_str(v) for k, v in obj.items()}
    elif isinstance(obj, (list, tuple)):
        return [datetime_to_str(elem) for elem in obj]
    elif isinstance(obj,(np.float64,np.float32,np.float16)):
        return float(obj)
    else:
        return obj

def is_true(s):
    return str(s)[0:1] in 'yY1tT'

# define get(), which gets a variable from either the forms request or the query string
def get(key, default=None):
    return request.forms.get(key, request.query.get(key, default))

def get_json(key):
    try:
        return json.loads(request.forms.get(key))
    except (TypeError,json.decoder.JSONDecodeError):
        return None

def get_int(key, default=None):
    try:
        return int(get(key))
    except TypeError:
        return default

def get_float(key, default=None):
    try:
        return float(get(key))
    except TypeError:
        return default

def get_bool(key, default=None):
    v = get(key)
    if v is None:
        return default
    try:
        return v[0:1] in 'yYtT1'
    except TypeError:
        return False

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
    return static_path('favicon.ico')

def get_user_dict():
    """Returns the user_id of the currently logged in user, or throws a response"""
    api_key = auth.get_user_api_key()
    if api_key is None:
        logging.info("api_key is none")
        raise bottle.HTTPResponse(body='', status=303, headers={ 'Location': '/'})
    userdict = db.validate_api_key(api_key)
    if not userdict:
        logging.info("api_key %s is invalid",api_key)
        raise bottle.HTTPResponse(body='', status=303, headers={ 'Location': '/error'})
    return userdict

def get_user_id():
    """Returns the user_id of the currently logged in user, or throws a response"""
    userdict = get_user_dict()
    if 'id' not in userdict:
        logging.info("no ID in userdict = %s", userdict)
        raise bottle.HTTPResponse(body='', status=303, headers={ 'Location': '/'})
    return userdict['id']


################################################################
# HTML Pages served with template system
################################################################

def page_dict(title='', *, require_auth=False, logout=False):
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
        movie_id = 0            # to avoid errors

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


@bottle.route('/api/check-api_key', method=GET_POST)
def api_check_api_key():
    """API to check the user key and, if valid, return usedict or returns an error."""

    userdict = db.validate_api_key(auth.get_user_api_key())
    if userdict:
        return {'error': False, 'userinfo': datetime_to_str(userdict)}
    return E.INVALID_API_KEY


@bottle.route('/api/get-logs', method=POST)
def api_get_logs():
    """Get logs and return in JSON. The database function does all of the security checks, but we need to have a valid user."""
    kwargs = {}
    for kw in ['start_time','end_time','course_id','course_key',
               'movie_id','log_user_id','ipaddr','count','offset']:
        if kw in request.forms.keys():
            kwargs[kw] = request.forms.get(kw)

    logs    = db.get_logs(user_id=get_user_id(),**kwargs)
    return {'error':False, 'logs': logs}

@bottle.route('/api/register', method=GET_POST)
def api_register():
    """Register the email address if it does not exist. Send a login and upload link"""
    email = request.forms.get('email')
    planttracer_endpoint = request.forms.get('planttracer_endpoint')
    if not validate_email(email, check_mx=False):
        logging.info("email not valid: %s", email)
        return E.INVALID_EMAIL
    course_key = request.forms.get('course_key')
    if not db.validate_course_key(course_key=course_key):
        return E.INVALID_COURSE_KEY
    if db.remaining_course_registrations(course_key=course_key) < 1:
        return E.NO_REMAINING_REGISTRATIONS
    name = request.forms.get('name')
    db.register_email(email=email, course_key=course_key, name=name)
    new_api_key = db.make_new_api_key(email=email)
    link_html = f"<p/><p>You can also log in by clicking this link: <a href='/list?api_key={new_api_key}'>login</a></p>"
    try:
        db.send_links(email=email, planttracer_endpoint=planttracer_endpoint, new_api_key=new_api_key)
    except mailer.InvalidMailerConfiguration:
        return {'error':True, 'message':'Mailer not properly configured.'+link_html}
    return {'error': False, 'message': 'Registration key sent to '+email+link_html}

@bottle.route('/api/resend-link', method=GET_POST)
def api_send_link():
    """Register the email address if it does not exist. Send a login and upload link"""
    email = request.forms.get('email')
    planttracer_endpoint = request.forms.get('planttracer_endpoint')
    logging.info("/api/resend-link email=%s planttracer_endpoint=%s",email,planttracer_endpoint)
    if not validate_email(email, check_mx=CHECK_MX):
        logging.info("email not valid: %s", email)
        return E.INVALID_EMAIL
    db.send_links(email=email, planttracer_endpoint=planttracer_endpoint)
    return {'error': False, 'message': 'If you have an account, a link was sent. If you do not receive a link within 60 seconds, you may need to <a href="/register">register</a> your email address.'}

@bottle.route('/api/bulk-register', method=POST)
def api_bulk_register():
    """Allow an admin to register people in the class, increasing the class size as necessary to do so."""
    course_id =  int(request.forms.get('course_id'))
    user_id   = get_user_id()
    planttracer_endpoint = request.forms.get('planttracer_endpoint')
    if not db.check_course_admin(course_id = course_id, user_id=user_id):
        return E.INVALID_COURSE_ACCESS

    email_addresses = request.forms.get('email-addresses').replace(","," ").replace(";"," ").replace(" ","\n").split("\n")
    for email in email_addresses:
        if not validate_email(email, check_mx=CHECK_MX):
            return E.INVALID_EMAIL
        db.register_email(email=email, course_id=course_id, name="")
        db.send_links(email=email, planttracer_endpoint=planttracer_endpoint)
    return {'error':False, 'message':f'Registered {len(email_addresses)} email addresses'}

################################################################
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

    #
    # It turns out that you can upload arbitrary data in an HTTP POST
    # provided that it is a file upload, but not in POST fields. That
    # is why I it has to be base64-encoded.
    if movie_data is None:
        movie_base64_data = request.forms.get('movie_base64_data',None)
        if movie_base64_data is not None:
            movie_data = base64.b64decode(movie_base64_data)
        logging.debug("api_new_movie: movie_base64_data from request.forms.get")
    else:
        logging.debug("api_new_movie: movie_base64_data is None")


    if (movie_data is not None) and (len(movie_data) > MAX_FILE_UPLOAD):
        logging.debug("api_new_movie: movie length %s bigger than %s",len(movie_data), MAX_FILE_UPLOAD)
        return {'error': True, 'message': f'Upload larger than larger than {MAX_FILE_UPLOAD} bytes.'}

    movie_id = db.create_new_movie(user_id=get_user_id(),
                                   title=request.forms.get('title'),
                                   description=request.forms.get('description'),
                                   movie_data=movie_data)
    return {'error': False, 'movie_id': movie_id}


@bottle.route('/api/get-movie-data', method=GET_POST)
def api_get_movie_data():
    """
    :param api_keuy:   authentication
    :param movie_id:   movie
    """
    if db.can_access_movie(user_id=get_user_id(), movie_id=get_int('movie_id')):
        bottle.response.set_header('Content-Type', 'video/quicktime')
        return db.get_movie_data(movie_id=get_int('movie_id'))
    return E.INVALID_MOVIE_ACCESS

@bottle.route('/api/download-movie-trackpoints',method=GET_POST)
def api_download_movie_trackpoints():
    """Downloads the movie trackpoints as a CSV
    :param api_keuy:   authentication
    :param movie_id:   movie
    """
    if db.can_access_movie(user_id=get_user_id(), movie_id=get_int('movie_id')):
        bottle.response.set_header('Content-Type', 'text/csv')
        trackpoint_dicts = db.get_movie_trackpoints(movie_id=get_int('movie_id'))
        numbers  = sorted(set([tp['frame_number'] for tp in trackpoint_dicts]))
        labels = sorted(set([tp['label'] for tp in trackpoint_dicts])) # get all labels
        data   = dict()
        # Now get the (x,y) for each time/label pair
        for tp in trackpoint_dicts:
            data[ (tp['frame_number'],tp['label']) ] = tp
        # Now generate the output
        with io.StringIO() as f:
            # write the header
            f.write('frame')
            for label in labels:
                f.write(f',{label} x,{label} y')
            f.write('\n')
            # Now write each time
            for num in numbers:
                f.write(f"{num}")
                for label in labels:
                    try:
                        tp = data[ (num,label) ]
                        f.write(f",{tp['x']},{tp['y']}")
                    except KeyError:
                        f.write(",,")
                f.write("\n")
            return f.getvalue()
    return E.INVALID_MOVIE_ACCESS


@bottle.route('/api/delete-movie', method='POST')
def api_delete_movie():
    """ delete a movie
    :param movie_id: the id of the movie to delete
    :param delete: 1 (default) to delete the movie, 0 to undelete the movie.
    """
    if db.can_access_movie(user_id=get_user_id(), movie_id=get_int('movie_id')):
        db.delete_movie(movie_id=get_int('movie_id'),
                        delete=get_bool('delete',True))
        return {'error': False}
    return E.INVALID_MOVIE_ACCESS


@bottle.route('/api/list-movies', method=POST)
def api_list_movies():
    return {'error': False, 'movies': db.list_movies(get_user_id())}


@bottle.route('/api/track-movie', method='POST')
def api_track_movie():
    """Tracks a movie that has been uploaded.
    :param api_key: the user's api_key
    :param movie_id: the movie to track; a new movie will be created
    :param frame_start: the frame to start tracking; frames 0..(frame_start-1) have track points copied.
    :param engine_name: string description tracking engine to use. May be omitted to get default engine.
    :param engine_version - string to describe which version number of engine to use. May be omitted for default version.
    :return: dict['error'] = True/False
             dict['message'] = message to display
    """

    # pylint: disable=unsupported-membership-test
    movie_id       = get_int('movie_id')
    if not db.can_access_movie(user_id=get_user_id(), movie_id=movie_id):
        return E.INVALID_MOVIE_ACCESS

    engine_name    = get('engine_name')
    engine_version = get('engine_version')
    frame_start    = get_int('frame_start')

    # Get the trackpoints for frame_start
    # write the movie
    # Write the trackpoints
    movie_metadata = db.get_movie_metadata(movie_id=movie_id, user_id=get_user_id())[0]

    # Find trackpoints we are tracking or retracking
    input_trackpoints = db.get_movie_trackpoints(movie_id=movie_id)
    logging.debug("input_trackpoints=%s",input_trackpoints)

    if len(input_trackpoints)==0:
        return E.NO_TRACKPOINTS

    # Write the movie to a tempfile, because OpenCV has to read movies from files.
    with tempfile.NamedTemporaryFile(suffix='.mp4',mode='wb') as infile:
        infile.write( db.get_movie_data(movie_id=movie_id) )
        infile.flush()

        # Create an output file, becuase OpenCV has to write movies to files
        with tempfile.NamedTemporaryFile(suffix='.mp4', mode='rb') as outfile:

            # Track the movie
            ret = tracker.track_movie(engine_name=engine_name,
                                      engine_version=engine_version,
                                      input_trackpoints = input_trackpoints,
                                      frame_start = frame_start,
                                      moviefile_input  = infile.name,
                                      moviefile_output = outfile.name)

            # Compute the new trackpoints
            new_movie_data       = outfile.read()
            output_trackpoints   = ret['output_trackpoints']
            output_trackpoints_by_frame = defaultdict(list)
            for tp in output_trackpoints:
                output_trackpoints_by_frame[tp['frame_number']].append(tp)

            # Save the movie
            new_title = movie_metadata['title']
            if "TRACKED" in new_title:
                new_title += "+"
            else:
                new_title += " TRACKED"
            new_movie_id = db.create_new_movie(user_id = get_user_id(),
                                               title = new_title,
                                               description = movie_metadata['description'],
                                               movie_data = new_movie_data)

            # Now write all of the trackpoints by frame that were after those tracked:
            for frame_number in output_trackpoints_by_frame.keys():
                if frame_number >= frame_start:
                    frame_id = db.create_new_frame(movie_id=new_movie_id, frame_number=frame_number)
                    db.put_frame_trackpoints(frame_id = frame_id,
                                             trackpoints=output_trackpoints_by_frame[frame_number])

    ret = {'error': False, 'output_trackpoints_by_frame': output_trackpoints_by_frame,'new_movie_id':new_movie_id}
    return datetime_to_str(ret)

##
# Movie analysis API
#
@bottle.route('/api/new-movie-analysis', method=POST)
def api_new_movie_analysis():
    """Creates a new movie analysis
    :param api_key: the user's api_key
    :param movie_id: The movie to associate this movie analysis with
    :param engine_id: The nngine used to create the analyis
    :param annotations: The movie analysis's annotations, that is, a JSON document containing analysis data
    """

    movie_analysis_id = db.create_new_movie_analysis(movie_id=request.forms.get('movie_id'),
                                   engine_id=request.forms.get('engine_id'),
                                   annotations=request.forms.get(
                                       'annotations')
                                   )['movie_analysis_id']
    return {'error': False, 'movie_analysis_id': movie_analysis_id}


################################################################
### Frame API

@bottle.route('/api/new-frame', method=POST)
def api_new_frame():
    """Create a new frame and return its frame_id.
    If frame exists, just update the frame_data (if frame data is provided).
    Returns frame_id.
    :param: api_key  - api_key
    :param: movie_id - the movie
    :param: frame_number - the frame to create
    :param: frame_data - if provided, it's uploaded; otherwise we just enter the frame into the dfatabase if it doesn't exist
    :return: frame_id - that's what we care about

    """
    if not db.can_access_movie(user_id=get_user_id(), movie_id=request.forms.get('movie_id')):
        return E.INVALID_MOVIE_ACCESS
    try:
        frame_data = base64.b64decode( request.forms.get('frame_base64_data'))
    except TypeError:
        frame_data = None
    frame_id = db.create_new_frame( movie_id = get_int('movie_id'),
                               frame_number = get_int('frame_number'),
                               frame_data = frame_data)
    return {'error': False, 'frame_id': frame_id}

@bottle.route('/api/get-frame', method=GET_POST)
def api_get_frame():
    """
    Get a frame and its annotation from a movie. Return from the frame database. If not there, grab it from the movie

    :param api_key:   authentication
    :param movie_id:   movie
    :param frame_id:   just get by frame_id
    :param frame_number: get the frame by frame_number (starting with 0)
    :param format:     jpeg - just get the image;
                       json (default) - get the image (default), json annotation and trackpoints
                       // todo - frame_id - just get the frame_id

    :return: - either the image (as a JPEG) or a JSON object. With JSON, includes:
      movie_id     - the movie (always returned)
      frame_id     - the id of the frame (always returned)
      frame_number - the number of the frame (always returned)
      annotations - a JSON object of annotations from the databsae.
      trackpoints - a list of the trackpoints
    """
    user_id      = get_user_id()
    frame_id     = get_int('frame_id')
    frame_number = get_int('frame_number')
    movie_id     = get_int('movie_id')
    fmt          = get('format', 'jpeg').lower()

    logging.debug("api_get_frame fmt=%s movie_id=%s frame_number=%s",fmt,movie_id,frame_number)
    if fmt not in ['jpeg', 'json']:
        logging.info("fmt is not in jpeg or json")
        return E.INVALID_FRAME_FORMAT

    if not db.can_access_movie(user_id=user_id, movie_id=movie_id):
        logging.info("User %s cannot access movie_id %s",user_id, movie_id)
        return E.INVALID_MOVIE_ACCESS

    if fmt=='jpeg':
        # is frame_id provided?
        if (frame_id is not None) and db.can_access_frame(user_id = get_user_id(), frame_id=frame_id):
            row =  db.get_frame(frame_id=frame_id)
            return row.get('frame_data',None)
        # Is there a movie we can access?
        if frame_number is not None and db.can_access_movie(user_id = get_user_id(), movie_id=movie_id):
            return tracker.extract_frame(movie_data = db.get_movie_data(movie_id = movie_id),
                                       frame_number = frame_number,
                                       fmt = 'jpeg')
        logging.info("fmt=jpeg but INVALID_FRAME_ACCESS with frame_id=%s and frame_number=%s and movie_id=%s",frame_id,frame_number,movie_id)
        return E.INVALID_FRAME_ACCESS

    # See if get_frame can find the movie frame
    ret = db.get_frame(movie_id=movie_id, frame_id = frame_id, frame_number=frame_number)
    logging.debug("ret=%s",ret)
    if ret:
        # Get any frame annotations and trackpoints
        ret['annotations'] = db.get_frame_annotations(frame_id=ret['frame_id'])
        ret['trackpoints'] = db.get_frame_trackpoints(frame_id=ret['frame_id'])

    else:
        # plant_dev is not in the database, so we need to make it
        frame_id = db.create_new_frame(movie_id = movie_id, frame_number = frame_number)
        ret = {'movie_id':movie_id,
               'frame_id':frame_id,
               'frame_number':frame_number}

    # If we do not have frame_data, extract it from the movie (but don't store in database)
    if ret.get('frame_data',None) is None:
        ret['frame_data'] = tracker.extract_frame(movie_data=db.get_movie_data(movie_id=movie_id),
                                                  frame_number=frame_number,
                                                  fmt='jpeg')

    # Convert the frame_data to a data URL
    ret['data_url'] = f'data:image/jpeg;base64,{base64.b64encode(ret["frame_data"]).decode()}'
    del ret['frame_data']

    #
    # Need to convert all datetimes to strings. We then return the dictionary, which bottle runs json.dumps() on
    # and returns MIME type of "application/json"
    # JQuery will then automatically decode this JSON into a JavaScript object, without having to call JSON.parse()
    return datetime_to_str(ret)

@bottle.route('/api/put-frame-analysis', method=POST)
def api_put_frame_analysis():
    """
    Writes analysis and trackpoints for specific frames; frame_id is required
    :param: api_key  - the api_key
    :param: frame_id - the frame.
    :param: engine_name - the engine name (if you don't; new engine_id created automatically)
    :param: engine_version - the engine version.
    :param: annotations - JSON string, must be an array or a dictionary, if provided
    :param: trackpoints - JSON string, must be an array of trackpoints, if provided
    """
    logging.debug("put_frame_analysis")
    frame_id  = get_int('frame_id')
    logging.debug("frame_id=%s",frame_id)
    if not db.can_access_frame(user_id=get_user_id(), frame_id=frame_id):
        logging.debug("user %s cannot access frame_id %s",get_user_id(), frame_id)
        return {'error':False, 'message':f'User {get_user_id()} cannot access frame_id={frame_id}'}
    annotations=get_json('annotations')
    trackpoints=get_json('trackpoints')
    logging.debug("put_frame_analysis. annotations=%s trackpoints=%s",annotations,trackpoints)
    if annotations is not None:
        db.put_frame_annotations(frame_id=frame_id,
                                 annotations=annotations,
                                 engine_name=get('engine_name'),
                                 engine_version=get('engine_version'))
    if trackpoints is not None:
        db.put_frame_trackpoints(frame_id=frame_id, trackpoints=trackpoints)
    return {'error': False, 'message':'Analysis recorded.'}


################################################################

##
# Log API
#
@bottle.route('/api/get-log', method=POST)
def api_get_log():
    """Get what log entries we can. get_user_id() provides access control.
    TODO - add search capabilities.
    """
    return {'error':False, 'logs': db.get_log(user_id=get_user_id()) }

##
# Metadata
##


################################################################
## Metdata Management (movies and users, it's a common API!)

@bottle.route('/api/get-metadata', method='POST')
def api_get_metadata():
    gmovie_id = get_bool('get_movie_id')
    guser_id  = get_bool('get_user_id')

    if (gmovie_id is None) and (guser_id is None):
        return {'error': True, 'result': 'Either get_movie_id or get_user_id is required'}

    return {'error': False, 'result': db.get_metadata(user_id=get_user_id(),
                                                      get_movie_id=gmovie_id,
                                                      get_user_id=guser_id,
                                                      property=request.forms.get('property'),
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
    set_movie_id = get_int('set_movie_id')
    set_user_id  = get_int('set_user_id')

    if (set_movie_id is None) and (set_user_id is None):
        return {'error': True, 'result': 'Either set_movie_id or set_user_id is required'}

    result = db.set_metadata(user_id=get_user_id(),
                             set_movie_id=set_movie_id,
                             set_user_id=set_user_id,
                             prop=get('property'),
                             value=get('value'))

    return {'error': False, 'result': result}


################################################################
## User management

##
## All of the users that this person can see
##
@bottle.route('/api/list-users', method=POST)
def api_list_users():
    return {**{'error': False}, **db.list_users(user_id=get_user_id())}


################################################################
##
## Demo and debug
##
@bottle.route('/api/add', method=GET_POST)
def api_add():
    a = get_float('a')
    b = get_float('b')
    try:
        return {'result': a+b, 'error': False}
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

    parser.add_argument( '--dbcredentials', help='Specify .ini file with [dbreader] and [dbwriter] sections')
    parser.add_argument('--port', type=int, default=8080)
    clogging.add_argument(parser, loglevel_default='WARNING')
    args = parser.parse_args()
    clogging.setup(level=args.loglevel)

    if args.dbcredentials:
        os.path.environ[C.DBCREDENTIALS_PATH] = args.dbcredentials

    # Now make sure that the credentials work
    # We only do this with the standalone program
    # the try/except is for when we run under a fixture, which messes up ROOT_DIR
    try:
        from tests.dbreader_test import test_db_connection
        test_db_connection()
    except ModuleNotFoundError:
        pass

    bottle.default_app().run(host='localhost', debug=True, reloader=True, port=args.port)

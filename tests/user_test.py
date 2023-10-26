"""
Test the various functions in the database involving user creation and movie creation
"""

from boddle import boddle
import sys
import os
import uuid
import logging
import pytest
import uuid
import base64
import time
import bottle
import copy
import hashlib
from os.path import abspath, dirname

sys.path.append(dirname(dirname(abspath(__file__))))


import db
import movietool
import bottle_app
import ctools.dbfile as dbfile

MYDIR = dirname(abspath(__file__))

MAX_ENROLLMENT = 10

TEST_USER_EMAIL = 'simsong@gmail.com'           # from configure
TEST_USER_NAME = 'Test User Name'
TEST_ADMIN_EMAIL = 'simsong+admin@gmail.com'     # configuration
TEST_ADMIN_NAME = 'Test User Name'

MOVIE_FILENAME = os.path.join(MYDIR, "data", "2019-07-31 plantmovie.mov")

# keys for scaffolding dictionary
ADMIN_EMAIL = 'admin_email'
ADMIN_ID = 'admin_id'
API_KEY  = 'api_key'
COURSE_KEY = 'course_key'
COURSE_NAME = 'course_name'
USER_EMAIL = 'user_email'
USER_ID    = 'user_id'
MOVIE_ID = 'movie_id'
MOVIE_TITLE = 'movie_title'
DBREADER = 'dbreader'
DBWRITER = 'dbwriter'

################################################################

@pytest.fixture
def new_course():
    """Fixture to create a new course and then delete it.
    New course creates a new course admin and a new user for it"""

    course_key = str(uuid.uuid4())[0:4]
    admin_email = TEST_ADMIN_EMAIL.replace('@', '+'+str(uuid.uuid4())[0:4]+'@')
    course_name = course_key + "course name"

    ct = db.create_course(course_key=course_key,
                          course_name=course_name,
                          max_enrollment=MAX_ENROLLMENT)['course_id']

    admin_id = db.register_email(email=admin_email, course_key=course_key, name=TEST_ADMIN_NAME)['user_id']

    logging.info("generated course_key=%s  admin_email=%s admin_id=%s",course_key,admin_email,admin_id)
    db.make_course_admin(email=admin_email, course_key=course_key)

    yield {COURSE_KEY:course_key,
           COURSE_NAME:course_name,
           ADMIN_EMAIL:admin_email,
           ADMIN_ID:admin_id,
           DBREADER:db.get_dbreader(),
           DBWRITER:db.get_dbwriter()
           }
    db.remove_course_admin(email=admin_email, course_key=course_key)
    db.delete_user(email=admin_email)
    ct = db.delete_course(course_key=course_key)
    assert ct == 1                # returns number of courses deleted

@pytest.fixture
def new_user(new_course):
    """Creates a new course and a new user and yields (USER_EMAIL, api_key)
    Then deletes them. The course gets deleted by the new_course fixture.
    """
    cfg = copy.copy(new_course)

    user_email = TEST_USER_EMAIL.replace('@', '+'+str(uuid.uuid4())[0:6]+'@')
    user_id = db.register_email(email=user_email,
                                course_key=cfg[COURSE_KEY],
                                name=TEST_USER_NAME)['user_id']
    logging.info("generated user_email=%s user_id=%s",user_email, user_id)

    api_key = db.make_new_api_key(email=user_email)
    assert len(api_key) > 8

    cfg[API_KEY] = api_key
    cfg[USER_EMAIL] = user_email
    cfg[USER_ID] = user_id

    yield cfg
    ct = db.delete_api_key(api_key)
    assert ct == 1
    db.delete_user(email=user_email)

@pytest.fixture
def api_key(new_user):
    """Simple fixture that just returns a valid api_key"""
    yield new_user[API_KEY]

@pytest.fixture
def new_movie(new_user):
    """Create a new movie_id and return it"""
    cfg = copy.copy(new_user)

    api_key = cfg[API_KEY]
    api_key_invalid = api_key+"invalid"

    movie_title = 'test movie title ' + str(uuid.uuid4())

    logging.debug("new_movie fixture: Opening %s",MOVIE_FILENAME)
    with open(MOVIE_FILENAME, "rb") as f:
        movie_data = f.read()
    assert len(movie_data) == os.path.getsize(MOVIE_FILENAME)
    assert len(movie_data) > 0

    logging.debug("new_movie fixture: Try to uplaod the movie with an invalid key")
    with boddle(params={"api_key": api_key_invalid,
                        "title": movie_title,
                        "description": "test movie description",
                        "movie_base64_data": base64.b64encode(movie_data)}):
        bottle_app.expand_memfile_max()
        with pytest.raises(bottle.HTTPResponse):
            res = bottle_app.api_new_movie()

    logging.debug("new_movie fixture: Create the movie in the database and upload the movie_data all at once")
    with boddle(params={"api_key": api_key,
                        "title": movie_title,
                        "description": "test movie description",
                        "movie_base64_data": base64.b64encode(movie_data)}):
        res = bottle_app.api_new_movie()
    assert res['error'] == False
    movie_id = res['movie_id']
    assert movie_id > 0

    cfg[MOVIE_ID] = movie_id
    cfg[MOVIE_TITLE] = movie_title

    logging.debug("new_movie fixture: movie_id=%s",movie_id)
    logging.debug("new_movie fixture: Make sure that the correct movie is actually in the database")

    retrieved_movie_data = db.get_movie_data(movie_id=movie_id)
    assert len(movie_data) == len(retrieved_movie_data)
    assert movie_data == retrieved_movie_data
    logging.debug("new_movie fixture: yield %s",cfg)
    yield cfg

    logging.debug("new_movie fixture: Delete the movie we uploaded")
    with boddle(params={'api_key': api_key,
                        'movie_id': movie_id}):
        res = bottle_app.api_delete_movie()
    assert res['error'] == False

    logging.debug("Purge the movie that we have deleted")
    db.purge_movie(movie_id=movie_id)


@pytest.fixture
def new_movie_uploaded(new_movie):
    cfg = copy.copy(new_movie)
    movie_id = cfg[MOVIE_ID]
    movie_title = cfg[MOVIE_TITLE]
    api_key = cfg[API_KEY]

    # Did the movie appear in the list?
    movies = movie_list(api_key)
    assert len([movie for movie in movies if movie['deleted'] ==
               0 and movie['published'] == 0 and movie['title'] == movie_title]) == 1

    # Make sure that we cannot delete the movie with a bad key
    with boddle(params={'api_key': 'invalid',
                        'movie_id': movie_id}):
        with pytest.raises(bottle.HTTPResponse):
            res = bottle_app.api_delete_movie()

    yield cfg

################################################################
## fixutre tests
################################################################


def test_new_course(new_course):
    cfg = copy.copy(new_course)
    course_key = cfg[COURSE_KEY]
    admin_email = cfg[ADMIN_EMAIL]
    logging.info("Created course %s", course_key)

def test_new_user(new_user):
    cfg = copy.copy(new_user)
    user_email = cfg[USER_EMAIL]
    api_key = cfg[API_KEY]
    logging.info("user_email=%s api_key=%s", user_email, api_key)

    # Try looking up the user
    ret1 = db.lookup_user(email=user_email)
    ret2 = db.lookup_user(user_id=ret1['user_id'], get_admin=True)
    ret3 = db.lookup_user(user_id=ret1['user_id'], get_courses=True)

    assert 'admin' in ret2
    assert 'courses' in ret3

def test_new_movie(new_movie):
    """Create a new user, upload the movie, delete the movie, and shut down"""
    cfg = copy.copy(new_movie)
    movie_id = cfg[MOVIE_ID]
    logging.info("movie_id=%s",movie_id)

def test_new_movie_upload(new_movie_uploaded):
    """Create a new user, upload the movie, delete the movie, and shut down"""
    data = db.get_movie_data(movie_id=new_movie_uploaded[MOVIE_ID])
    logging.info("movie size: %s written",len(data))

def test_movie_update_metadata(new_movie):
    """try updating the metadata, and making sure some updates fail."""
    cfg = copy.copy(new_movie)
    movie_id = cfg[MOVIE_ID]
    movie_title = cfg[MOVIE_TITLE]
    api_key = cfg[API_KEY]

    # Validate the old title
    assert get_movie(api_key, movie_id)['title'] == movie_title

    new_title = 'special new title ' + str(uuid.uuid4())
    with boddle(params={'api_key': api_key,
                        'set_movie_id': movie_id,
                        'property': 'title',
                        'value': new_title}):
        res = bottle_app.api_set_metadata()
    assert res['error'] == False

    # Get the list of movies
    assert get_movie(api_key, movie_id)['title'] == new_title

    new_description = 'special new description ' + str(uuid.uuid4())
    with boddle(params={'api_key': api_key,
                        'set_movie_id': movie_id,
                        'property': 'description',
                        'value': new_description}):
        res = bottle_app.api_set_metadata()
    assert res['error'] == False
    assert get_movie(api_key, movie_id)['description'] == new_description

    # Try to delete the movie
    with boddle(params={'api_key': api_key,
                        'set_movie_id': movie_id,
                        'property': 'deleted',
                        'value': 1}):
        res = bottle_app.api_set_metadata()
    assert res['error'] == False
    assert get_movie(api_key, movie_id)['deleted'] == 1

    # Undelete the movie
    with boddle(params={'api_key': api_key,
                        'set_movie_id': movie_id,
                        'property': 'deleted',
                        'value': 0}):
        res = bottle_app.api_set_metadata()
    assert res['error'] == False
    assert get_movie(api_key, movie_id)['deleted'] == 0

    # Try to publish the movie under the user's API key. This should not work
    assert get_movie(api_key, movie_id)['published'] == 0
    with boddle(params={'api_key': api_key,
                        'set_movie_id': movie_id,
                        'property': 'published',
                        'value': 1}):
        res = bottle_app.api_set_metadata()
    assert res['error'] == False
    assert get_movie(api_key, movie_id)['published'] == 0

    # Try to publish the movie with the course admin's API key. This should work

def test_movie_extract(new_movie_uploaded):
    """Try extracting movie frames and the frame-by-frame access"""
    cfg = copy.copy(new_movie_uploaded)
    movie_id = cfg[MOVIE_ID]
    movie_title = cfg[MOVIE_TITLE]
    api_key = cfg[API_KEY]
    user_id = cfg[USER_ID]
    frames = movietool.extract(cfg[DBWRITER], movie_id=movie_id, user_id=user_id)
    assert frames>0

    def sha256(x):
        hasher = hashlib.sha256()
        hasher.update(x)
        return hasher.hexdigest()

    # Grab three frames and see if they are correct
    res0 = db.get_frame(movie_id=movie_id, frame_msec=0, msec_delta = 0)
    assert res0 is not None
    logging.info("res0: movie_id-%s frame_msec=%s sha256(frame_data)=%s",res0['movie_id'],res0['frame_msec'], sha256(res0['frame_data']))
    res1 = db.get_frame(movie_id=movie_id, frame_msec=0, msec_delta = 1)
    assert res1 is not None
    logging.info("res1: movie_id-%s frame_msec=%s sha256(frame_data)=%s",res1['movie_id'],res1['frame_msec'], sha256(res1['frame_data']))
    res2 = db.get_frame(movie_id=movie_id, frame_msec=res2['frame_msec'], msec_delta = 1)
    assert res2 is not None
    logging.info("res2: movie_id-%s frame_msec=%s sha256(frame_data)=%s",res2['movie_id'],res2['frame_msec'], sha256(res2['frame_data']))
    res0b = db.get_frame(movie_id=movie_id, frame_msec=res2['frame_msec'], msec_delta = -1)
    assert res0b is not None
    logging.info("res0b: movie_id-%s frame_msec=%s sha256(frame_data)=%s",res0b['movie_id'],res0b['frame_msec'], sha256(res0b['frame_data']))
    assert res0['frame_msec'] < res1['frame_msec']
    assert res1['frame_msec'] < res2['frame_msec']
    assert res0['frame_msec'] == res0b['frame_msec']




################################################################
## support functions
################################################################


def movie_list(api_key):
    """Return a list of the movies"""
    with boddle(params={"api_key": api_key}):
        res = bottle_app.api_list_movies()
    assert res['error'] == False
    return res['movies']

def get_movie(api_key, movie_id):
    """Used for testing. Just pull the specific movie"""
    movies = movie_list(api_key)
    for movie in movies:
        return movie

    user_id = db.validate_api_key(api_key)['user_id']
    logging.error("api_key=%s movie_id=%s user_id=%s",
                  api_key, movie_id, user_id)
    logging.error("len(movies)=%s", len(movies))
    for movie in movies:
        logging.error("%s", str(movie))
    dbreader = db.get_dbreader()
    logging.error("Full database: (dbreader: %s)", dbreader)
    for movie in dbfile.DBMySQL.csfr(dbreader, "select * from movies", (), asDicts=True):
        logging.error("%s", str(movie))
    raise RuntimeError(f"No movie has movie_id {movie_id}")


def test_get_logs():
    """Incrementally test each part of the get_logs functions"""
    dbreader = db.get_dbreader()
    for security in [False,True]:
        logging.info("security=%s",security)
        db.get_logs( user_id=0 , security=security)
        db.get_logs( user_id=0, start_time = 0 , security=security)
        db.get_logs( user_id=0, end_time = 0 , security=security)
        db.get_logs( user_id=0, course_key = 0 , security=security)
        db.get_logs( user_id=0, movie_id = 0, security=security)
        db.get_logs( user_id=0, log_user_id = 0, security=security)
        db.get_logs( user_id=0, ipaddr = "", security=security)

def test_course_list(new_user):
    cfg        = copy.copy(new_user)
    user_email = cfg[USER_EMAIL]
    api_key    = cfg[API_KEY]

    user_dict = db.validate_api_key(api_key)
    user_id   = user_dict['user_id']
    primary_course_id = user_dict['primary_course_id']

    recs1 = db.list_users(user_id=user_id)
    users1 = recs1['users']

    matches = [user for user in users1 if user['user_id']==user_id]
    assert(len(matches)>0)

    # Make sure that there is an admin in the course who is not the user
    recs2 = db.list_admins()
    matches = [rec for rec in recs2 if rec['course_id']==primary_course_id and rec['user_id']!=user_id]
    assert len(matches)==1

    # Make sure that the endpoint works
    with boddle(params={'api_key': api_key}):
        res = bottle_app.api_list_users()
    assert res['error'] is False
    users2 = res['users']
    assert len(users2)==2
    assert users1[0]['name'] == users2[0]['name']
    assert users1[0]['email'] == users2[0]['email']


def test_log_search_user(new_user):
    """Currently we just run logfile queries and count the number of results."""
    cfg        = copy.copy(new_user)
    user_email = cfg[USER_EMAIL]
    api_key    = cfg[API_KEY]

    user_id  = db.validate_api_key(api_key)['user_id']
    dbreader = db.get_dbreader()

    ret = db.get_logs( user_id=user_id )
    logging.info("search for user_email=%s user_id=%s returns %s logs",user_email,user_id, len(ret))

    assert len(ret) > 0
    assert len(db.get_logs( user_id=user_id, start_time = 10)) > 0
    assert len(db.get_logs( user_id=user_id, end_time = time.time())) > 0

    # Make sure that restricting the time to something that happened more than a day ago fails,
    # because we just created this user.
    assert len(db.get_logs( user_id=user_id, end_time = time.time()-24*60*60)) ==0

    # Find the course that this user is in
    res = dbfile.DBMySQL.csfr(dbreader, "select primary_course_id from users where id=%s", (user_id,))
    assert(len(res)==1)
    course_id = res[0][0]

    res = dbfile.DBMySQL.csfr(dbreader, "select course_key from courses where id=%s", (course_id,))
    assert(len(res)==1)
    course_key = res[0][0]

    assert(len(db.get_logs( user_id=user_id, course_id = course_id)) > 0)
    assert(len(db.get_logs( user_id=user_id, course_key = course_key)) > 0)

    # Test to make sure that the course admin gets access to this user
    admin_id = dbfile.DBMySQL.csfr(dbreader,
                                   "SELECT user_id FROM admins WHERE course_id=%s LIMIT 1",
                                   (course_id,))[0]
    assert(len(db.get_logs( user_id=admin_id, log_user_id=user_id, course_id = course_id)) > 0)
    assert(len(db.get_logs( user_id=admin_id, log_user_id=user_id, course_key = course_key)) > 0)

    # We should have nothing with this IP address
    assert(len(db.get_logs( user_id=user_id, ipaddr="0.0.0.0"))==0)

def test_log_search_movie(new_movie):
    cfg        = copy.copy(new_movie)
    api_key    = cfg[API_KEY]
    movie_id   = cfg[MOVIE_ID]
    movie_title= cfg[MOVIE_TITLE]

    dbreader = db.get_dbreader()
    res = dbfile.DBMySQL.csfr(dbreader, "select user_id from movies where id=%s", (movie_id,))
    user_id = res[0][0]
    res = db.get_logs( user_id=user_id, movie_id = movie_id)
    logging.info("log entries for movie:")
    for r in res:
        logging.info("%s",r)

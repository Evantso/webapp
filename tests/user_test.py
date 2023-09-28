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

from os.path import abspath, dirname


sys.path.append(dirname(dirname(abspath(__file__))))

import db
import bottle_app
import ctools.dbfile as dbfile

MYDIR = dirname(abspath(__file__))

MAX_ENROLLMENT = 10

TEST_USER_EMAIL = 'simsong@gmail.com'           # from configure
TEST_USER_NAME = 'Test User Name'
TEST_ADMIN_EMAIL = 'simsong+admin@gmail.com'     # configuration
TEST_ADMIN_NAME = 'Test User Name'

MOVIE_FILENAME = os.path.join(MYDIR, "data", "2019-07-31 plantmovie.mov")

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



################################################################

@pytest.fixture
def new_course():
    """Fixture to create a new course and then delete it. New course creates a new course admin and a new user for it"""
    course_key = str(uuid.uuid4())[0:4]
    admin_email = TEST_ADMIN_EMAIL.replace('@', '+'+str(uuid.uuid4())[0:4]+'@')

    ct = db.create_course(course_key=course_key, course_name=course_key + "course name", max_enrollment=MAX_ENROLLMENT)['course_id']
    admin_id = db.register_email(email=admin_email, course_key=course_key, name=TEST_ADMIN_NAME)['user_id']
    logging.info("generated course_key=%s  admin_email=%s admin_id=%s",course_key,admin_email,admin_id)
    db.make_course_admin(email=admin_email, course_key=course_key)
    yield (course_key,admin_email)
    db.remove_course_admin(email=admin_email, course_key=course_key)
    db.delete_user(email=admin_email)
    ct = db.delete_course(course_key=course_key)
    assert ct == 1                # returns number of courses deleted


@pytest.fixture
def new_user(new_course):
    """Creates a new course and a new user and yields (USER_EMAIL, api_key)
    Then deletes them. The course gets deleted by the new_course fixture.
    """
    (course_key, admin_email) = new_course

    user_email = TEST_USER_EMAIL.replace('@', '+'+str(uuid.uuid4())[0:6]+'@')
    user_id = db.register_email(email=user_email, course_key=course_key, name=TEST_USER_NAME)['user_id']
    logging.info("generated user_email=%s user_id=%s",user_email, user_id)

    api_key = db.make_new_api_key(email=user_email)
    assert len(api_key) > 8
    yield (user_email, api_key)
    ct = db.delete_api_key(api_key)
    assert ct == 1
    db.delete_user(email=user_email)


@pytest.fixture
def new_movie(new_user):
    """Create a new movie_id and return it"""
    (email, api_key) = new_user

    MOVIE_TITLE = 'test movie title ' + str(uuid.uuid4())

    with open(MOVIE_FILENAME, "rb") as f:
        movie_base64_data = base64.b64encode(f.read())

   # Try to uplaod the movie with an invalid key
    with boddle(params={"api_key": api_key+'invalid',
                        "title": MOVIE_TITLE,
                        "description": "test movie description",
                        "movie_base64_data": movie_base64_data}):
        bottle_app.expand_memfile_max()
        with pytest.raises(bottle.HTTPResponse):
            res = bottle_app.api_new_movie()

    # Try to uplaod the movie all at once
    with boddle(params={"api_key": api_key,
                        "title": MOVIE_TITLE,
                        "description": "test movie description",
                        "movie_base64_data": movie_base64_data}):
        res = bottle_app.api_new_movie()
    assert res['error'] == False
    movie_id = res['movie_id']
    assert movie_id > 0
    yield (movie_id, MOVIE_TITLE, api_key)

    # Delete the movie we uploaded
    with boddle(params={'api_key': api_key,
                        'movie_id': movie_id}):
        res = bottle_app.api_delete_movie()
    assert res['error'] == False

    # And purge the movie that we have deleted
    db.purge_movie(movie_id=movie_id)


def test_new_course(new_course):
    (course_key, admin_email) = new_course
    logging.info("Created course %s", course_key)

def test_new_user(new_user):
    (email, api_key) = new_user
    logging.info("email=%s api_key=%s", email, api_key)

def test_movie_upload(new_movie):
    """Create a new user, upload the movie, delete the movie, and shut down"""
    (movie_id, movie_title, api_key) = new_movie

    # Did the movie appear in the list?
    movies = movie_list(api_key)
    assert len([movie for movie in movies if movie['deleted'] ==
               0 and movie['published'] == 0 and movie['title'] == movie_title]) == 1

    # Make sure that we cannot delete the movie with a bad key
    with boddle(params={'api_key': 'invalid',
                        'movie_id': movie_id}):
        with pytest.raises(bottle.HTTPResponse):
            res = bottle_app.api_delete_movie()


def test_movie_update_metadata(new_movie):
    """try updating the metadata, and making sure some updates fail."""

    (movie_id, movie_title, api_key) = new_movie

    # Validate the old title
    assert get_movie(api_key, movie_id)['title'] == movie_title

    new_title = 'special new title ' + str(uuid.uuid4())
    with boddle(params={'api_key': api_key,
                        'set_movie_id': movie_id,
                        'property': 'title',
                        'value': new_title}):
        res = bottle_app.api_set_metadata()
    logging.error('res=%s', res)
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

def test_log_search_user(new_user):
    """Currently we just run logfile queries and count the number of results."""
    (user_email, api_key) = new_user
    user_id = db.validate_api_key(api_key)['user_id']
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
    admin_id = dbfile.DBMySQL.csfr(dbreader, "select user_id from admins where course_id=%s LIMIT 1", (course_id,))[0]
    assert(len(db.get_logs( user_id=admin_id, log_user_id=user_id, course_id = course_id)) > 0)
    assert(len(db.get_logs( user_id=admin_id, log_user_id=user_id, course_key = course_key)) > 0)

    # We should have nothing with this IP address
    assert(len(db.get_logs( user_id=user_id, ipaddr="0.0.0.0"))==0)

def test_log_search_movie(new_movie):
    (movie_id, movie_title, api_key) = new_movie
    dbreader = db.get_dbreader()
    res = dbfile.DBMySQL.csfr(dbreader, "select user_id from movies where id=%s", (movie_id,))
    user_id = res[0][0]
    res = db.get_logs( user_id=user_id, movie_id = movie_id)
    logging.info("log entries for movie:")
    for r in res:
        logging.info("%s",r)

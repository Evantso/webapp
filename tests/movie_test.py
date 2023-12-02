"""
Test the various functions in the database involving movie creation.
"""

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
import magic
import json
from os.path import abspath, dirname

from boddle import boddle

sys.path.append(dirname(dirname(abspath(__file__))))

from paths import TEST_DATA_DIR
import lib.ctools.dbfile as dbfile
import db
import movietool
import bottle_app

# Get the fixtures from user_test
from user_test import new_user,new_course,API_KEY,MOVIE_ID,MOVIE_TITLE,USER_ID,DBWRITER
from endpoint_test import TEST_MOVIE_FILENAME
from constants import MIME

@pytest.fixture
def new_movie(new_user):
    """Create a new movie_id and return it"""
    cfg = copy.copy(new_user)

    api_key = cfg[API_KEY]
    api_key_invalid = api_key+"invalid"

    movie_title = 'test movie title ' + str(uuid.uuid4())

    logging.debug("new_movie fixture: Opening %s",TEST_MOVIE_FILENAME)
    with open(TEST_MOVIE_FILENAME, "rb") as f:
        movie_data = f.read()
    assert len(movie_data) == os.path.getsize(TEST_MOVIE_FILENAME)
    assert len(movie_data) > 0

    # This generates an error, which is why it needs to be caught with pytest.raises():
    logging.debug("new_movie fixture: Try to uplaod the movie with an invalid key")
    with boddle(params={"api_key": api_key_invalid,
                        "title": movie_title,
                        "description": "test movie description",
                        "movie_base64_data": base64.b64encode(movie_data)}):
        bottle_app.expand_memfile_max()
        with pytest.raises(bottle.HTTPResponse):
            res = bottle_app.api_new_movie()

    # This does not raise an error
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



def test_new_movie(new_movie):
    """Create a new user, upload the movie, delete the movie, and shut down"""
    cfg = copy.copy(new_movie)
    api_key = cfg[API_KEY]
    movie_id = cfg[MOVIE_ID]
    with boddle(params={'api_key': api_key,
                        'movie_id': movie_id}):
        res = bottle_app.api_get_movie_data()
    # res must be a movie
    assert len(res)>0

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

    # Before we start, movie_id should be a movie with no frames
    assert movie_id in [item['movie_id'] for item in db.list_movies(0, no_frames=True)]

    frames = movietool.extract_frames(movie_id=movie_id, user_id=user_id)
    assert frames>0

    # Now, it should not be in the list
    assert movie_id not in [item['movie_id'] for item in db.list_movies(0, no_frames=True)]

    def sha256(x):
        hasher = hashlib.sha256()
        hasher.update(x)
        return hasher.hexdigest()

    # Grab three frames and see if they are correct
    res0 = db.get_frame(movie_id=movie_id, frame_msec=0, msec_delta = 0)
    assert res0 is not None
    res1 = db.get_frame(movie_id=movie_id, frame_msec=0, msec_delta = 1)
    assert res1 is not None
    res2 = db.get_frame(movie_id=movie_id, frame_msec=res1['frame_msec'], msec_delta = 1)
    assert res2 is not None
    res0b = db.get_frame(movie_id=movie_id, frame_msec=res1['frame_msec'], msec_delta = -1)
    assert res0b is not None
    assert res0['frame_msec'] < res1['frame_msec']
    assert res1['frame_msec'] < res2['frame_msec']
    assert res0['frame_msec'] == res0b['frame_msec']

    # Make sure can_access frame is true
    assert db.can_access_frame(user_id=user_id, frame_id = res0['frame_id'])
    # Make sure a different user cannot access the frame
    assert not db.can_access_frame(user_id=user_id+1, frame_id = res0['frame_id'])

    # get the frame with the JPEG interface
    with boddle(params={"api_key": api_key,
                        'movie_id': str(movie_id),
                        'frame_msec': '0',
                        'msec_delta': '0'}):
        ret = bottle_app.api_get_frame()
    assert res0['frame_data'] == ret
    assert magic.from_buffer(ret,mime=True)== MIME.JPEG

    # get the frame with the JSON interface.
    # get_frame now relies on bottle to turn the dictionary into a JSON object, so boddle gets the raw dictionary and
    # does not need json.loads
    with boddle(params={"api_key": api_key,
                        'movie_id': str(movie_id),
                        'frame_msec': '0',
                        'msec_delta': '0',
                        'format':'json' }):
        ret = bottle_app.api_get_frame()
    assert ret['data_url'].startswith('data:image/jpeg;base64,')
    assert base64.b64decode(ret['data_url'][23:])==res0['frame_data']

    # get the frame with the JSON interface
    with boddle(params={"api_key": api_key,
                        'movie_id': str(movie_id),
                        'frame_msec': '0',
                        'msec_delta': '0',
                        'format':'json'}):
        ret = bottle_app.api_get_frame()
    assert 'analysis' not in ret
    frame_id = ret['frame_id']

    # Check to make sure get-frame-id works
    with boddle(params={"api_key": api_key,
                        "frame_id": frame_id}):
        ret = bottle_app.get_frame_id()
    assert ret['frame_data']==res0['frame_data']

    # Create a random engine and upload two analysis for it
    engine_name = "engine " + str(uuid.uuid4())[0:8]
    annotations1 = {'guid':str(uuid.uuid4()),
                 "key1": "value with 'single' quotes",
                 "key2": 'value with "double" quotes',
                 "key3": "value with 'single' and \"double\" quotes" }
    annotations2 = {'guid':str(uuid.uuid4()),
                 "key1": "value with 'single' quotes",
                 "key2": 'value with "double" quotes',
                 "key3": "value with 'single' and \"double\" quotes" }


    # Test various error conditions first

    # Check for error if all three are none
    with pytest.raises(RuntimeError):
        db.put_frame_analysis(frame_id=frame_id, annotations=annotations1)

    # Check for error if engine_name is provided but engine_version is not
    with pytest.raises(RuntimeError):
        db.put_frame_analysis(frame_id=frame_id, engine_name=engine_name, annotations=annotations1)

    # Check for error if both engine_id and engine_name are provided
    with pytest.raises(RuntimeError):
        db.put_frame_analysis(frame_id=frame_id, engine_id=1, engine_name=engine_name, engine_version='1', annotations=annotations1)

    # Now test putting frame analysis
    db.put_frame_analysis(frame_id=frame_id,
                          engine_name=engine_name,
                          engine_version="1",
                          annotations=annotations1)

    # Now test with the Bottle API
    with boddle(params={'api_key': api_key,
                        'frame_id': str(frame_id),
                        'engine_name': engine_name,
                        'engine_version':'2',
                        'annotations':json.dumps(annotations2)}):
        bottle_app.api_put_frame_analysis()

    # get the frame with the JSON interface, asking for annotations
    with boddle(params={"api_key": api_key,
                        'movie_id': str(movie_id),
                        'frame_msec': '0',
                        'msec_delta': '0',
                        'format':'json',
                        'get_analysis':True}):
        ret = bottle_app.api_get_frame()
    analysis_stored = ret['analysis']
    # analysis_stored is a list of dictionaries where each dictionary contains a JSON string called 'annotations'
    # turn the strings into dictionary objects and compare then with our original dictionaries to see if we can
    # effectively round-trip through multiple layers of parsers, unparsers, encoders and decoders
    assert analysis_stored[0]['annotations']==annotations1
    assert analysis_stored[1]['annotations']==annotations2

    # See if we can get the frame by id without the analysis
    r2 = db.get_frame_id(frame_id=frame_id,get_analysis=False)
    assert r2['frame_id'] == frame_id
    assert magic.from_buffer(r2['frame_data'],mime=True)==MIME.JPEG
    assert 'analysis' not in r2

    # See if we can get the frame by id with the analysis
    r2 = db.get_frame_id(frame_id=frame_id,get_analysis=True)
    assert 'analysis' in r2

    # Validate the bottle interface

    # See if we can get the frame by id without the analysis
    r2 = db.get_frame_id(frame_id=frame_id,get_analysis=False)
    assert 'analysis' not in r2
    assert r2['frame_id'] == frame_id

    # See if we can save two trackpoints in the frame and get them back
    tp0 = {'x':10,'y':11,'label':'label1'}
    tp1 = {'x':20,'y':21,'label':'label2'}
    db.put_frame_trackpoints(frame_id=frame_id, trackpoints=[ tp0, tp1 ])

    # See if I can get it back
    tps = db.get_frame_trackpoints(frame_id=frame_id)
    assert len(tps)==2

    # Ask the API to track the trackpoints between frames!
    with boddle(params={"api_key": api_key,
                        'movie_id': str(movie_id),
                        'frame_msec': '0',
                        'msec_delta': '+1',
                        'format':'json',
                        'get_trackpoints':True,
                        'engine_name':'NULL' }):
        ret = bottle_app.api_get_frame()
    logging.debug("ret1.trackpoints-engine=%s",ret['trackpoints-engine'])
    assert ret['trackpoints-engine'][0]==tp0
    assert ret['trackpoints-engine'][1]==tp1

    # Now track with CV2
    with boddle(params={"api_key": api_key,
                        'movie_id': str(movie_id),
                        'frame_msec': '0',
                        'msec_delta': '1',
                        'format':'json',
                        'get_trackpoints':True,
                        'engine_name':'CV2' }):
        ret = bottle_app.api_get_frame()
    logging.debug("ret2.trackpoints=%s",ret['trackpoints-engine'])
    assert 9.0 < ret['trackpoints-engine'][0]['x'] < 10.0
    assert 9.0 < ret['trackpoints-engine'][0]['y'] < 10.0
    assert ret['trackpoints-engine'][0]['label'] == 'label1'

    assert 18.0 < ret['trackpoints-engine'][1]['x'] < 19.0
    assert 21.0 < ret['trackpoints-engine'][1]['y'] < 22.0
    assert ret['trackpoints-engine'][1]['label'] == 'label2'

    # Delete the trackpoints
    db.put_frame_trackpoints(frame_id=frame_id, trackpoints=[])

    # Make sure they are deleted
    assert db.get_frame_trackpoints(frame_id=frame_id)==[]

    # Delete the analysis
    logging.info("deleting frame analsys engine_id %s name %s",analysis_stored[0]['engine_id'],analysis_stored[0]['engine_name'])
    db.delete_frame_analysis(engine_id=analysis_stored[0]['engine_id'])
    db.delete_frame_analysis(engine_id=analysis_stored[1]['engine_id'])

    # delete the analysis engine
    db.delete_analysis_engine(engine_name=engine_name)


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

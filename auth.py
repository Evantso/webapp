"""Authentication Layer

This layer is necessarily customized to bottle.
"""
import sys
import os
import io
import datetime
import logging
from urllib.parse import urlparse
import json

import bottle
from bottle import request

API_KEY_COOKIE_NAME = 'api_key'

################################################################
# Authentication API
##


def get_user_api_key():
    """Gets the user APIkey from either the URL or the cookie or the form, but does not validate it.
    :return: None if user is not logged in
    """

    # check the query string
    try:
        api_key = request.query.get(API_KEY_COOKIE_NAME, None)
    except KeyError:
        return None             # not running in WSGI

    if api_key:
        return api_key

    # check for a form submission
    try:
        api_key = request.forms.get('api_key', None)
    except KeyError:
        return None             # not running in WSGI

    if api_key:
        return api_key
    # Check for a cookie
    api_key = request.get_cookie('api_key', None)
    if api_key:
        return api_key
    return None


def get_user_ipaddr():
    """This is the only place where db.py knows about bottle."""
    return request.environ.get('REMOTE_ADDR')


def get_movie_id():
    movie_id = request.query.get('movie_id', None)
    if movie_id is not None:
        return movie_id
    movie_id = request.forms.get('movie_id', None)
    if movie_id is not None:
        return movie_id
    raise bottle.HTTPResponse(body=json.dumps(INVALID_MOVIE_ID), status=200, headers={
                              'Content-type': 'application/json'})

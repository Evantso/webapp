"""
Test functions to verify the title of the Plant Tracer webapp home/index page

This module also serves to illustrate how to use Selenium and Pytest together.

The two tests here test the same thing, but one uses the pytest-selenium
package and the other uses the selenium package directly.
"""

import os
import logging
import functools

import pytest
import pytest_selenium

# not needed for using pytest-selenium, just for using selenium directly
from selenium import webdriver
from selenium.webdriver.chrome.options import Options

PLANTTRACER_TITLE = 'Plant Tracer'

@functools.cache
def on_dreamhost():
    """If we are running on dreamhost, the word 'dreamhost' is in /etc/hosts a lot.
    I can't find any other way to know if we are running on dreamhost.
    """
    with open("/etc/hosts","r") as f:
        hosts = f.read().lower()
        return hosts.count("dreamhost")>1



# test function illustrating the use of selenium package directly
@pytest.mark.skipif(on_dreamhost(), reason='Selenium test does not work on dreamhost')
def test_sitetitle_just_selenium(http_endpoint):

    logging.info("http_endpoint %s", http_endpoint)

    options = Options()
    options.add_argument("--headless")
    #
    # Following added per ChatGPT-4:
    options.add_argument("--no-sandbox")  # This option is often necessary in Docker or CI environments
    options.add_argument("--disable-gpu")  # This option is recommended for headless mode
    options.add_argument("--window-size=1920,1080")  # Specify window size
    # per https://pytest-selenium.readthedocs.io/en/latest/user_guide.html#quick-start
    if 'CHROME_PATH' in os.environ:
        logging.info('CHROME_PATH=%s',os.environ['CHROME_PATH'])
        options.binary_location = os.environ['CHROME_PATH']

    browser_driver = webdriver.Chrome(options = options) # TODO: externalize browser type, if possible
    browser_driver.get(http_endpoint)
    assert browser_driver.title == PLANTTRACER_TITLE
    browser_driver.close()
    browser_driver.quit()

# test function illustrating the use of pytest-selenium package
# pytest-selenium itself uses the selenium package
#
# Using pytest-selenium requires the --driver command line argument to pytest
# --driver may be specified in pytest.ini using addopts Configuration option
#
# NOTE: --driver causes pytest to crash if pytest-selenium is not installed (SLG)
#
# At the moment, using pytest-selenium for PlantTracer isn't the first choice
# It's harder to debug and there are no public examples of how to use the fixtures
# in test modules. There are plenty of examples of just using selenium to
# create one's own fixtures, so that's the direction for now.
#
# TODO: test should probably be headless, or at least clean up their browser processes

@pytest.mark.skip(reason='not using pytest-selenium')
def test_sitetitle_pytest_selenium(http_endpoint, selenium):
    selenium.get(http_endpoint) # TODO: externalize site URL
    assert selenium.title == PLANTTRACER_TITLE

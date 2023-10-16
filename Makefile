#
# Note: when this runs on Dreamhost, we need to use the python in $HOME/opt/bin
#

PYLINT_FILES=$(shell /bin/ls *.py  | grep -v bottle.py | grep -v app_wsgi.py)
PYTHON=python3.11

# By default, PYLINT generates an error if your code does not rank 10.0.
# This makes us tolerant of minor problems.
PYLINT_THRESHOLD=9.5

all:
	@echo verify syntax and then restart
	make pylint
	make touch

check:
	make pylint
	make pytest

touch:
	touch tmp/restart.txt

pylint:
	pylint --rcfile .pylintrc --fail-under=$(PYLINT_THRESHOLD) --verbose $(PYLINT_FILES)

flake8:
	flake8 $(PYLINT_FILES)

pytest:
	make launch-local-mail
	make touch
	$(PYTHON) -m pytest . -v --log-cli-level=INFO

pytest-debug:
	make launch-local-mail
	make touch
	$(PYTHON) -m pytest . -v --log-cli-level=DEBUG

pytest-quiet:
	make launch-local-mail
	make touch
	$(PYTHON) -m pytest . --log-cli-level=ERROR

create_localdb:
	$(PYTHON) dbmaint.py --rootconfig etc/github_actions_mysql_rootconfig.ini --createdb actions_test --writeconfig etc/actions_test.ini
	cat etc/actions_test.ini

remove_localdb:
	$(PYTHON) dbmaint.py --rootconfig etc/github_actions_mysql_rootconfig.ini --dropdb actions_test --writeconfig etc/actions_test.ini
	/bin/rm -f etc/actions_test.ini

coverage:
	make launch-local-mail
	$(PYTHON) -m pip install pytest pytest_cov
	$(PYTHON) -m pytest -v --cov=. --cov-report=xml tests

debug:
	python bottle_app.py

clean:
	find . -name '*~' -exec rm {} \;

################################################################
## Local mail server

LOCALMAIL_PID=twistd.pid
LOCALMAIL_MBOX=/tmp/localmail.mbox
kill-local-mail:
	if [ -r $(LOCALMAIL_PID) ]; then echo kill -9 `cat $(LOCALMAIL_PID)` ; kill -9 `cat $(LOCALMAIL_PID)` ; /bin/rm -f $(LOCALMAIL_PID) ; fi
	/bin/rm -f $(LOCALMAIL_MBOX)

launch-local-mail:
	make kill-local-mail
	twistd localmail --imap 10001 --smtp 10002 --http 10003 --file $(LOCALMAIL_MBOX)

dump-local-mail:
	if [ -r $(LOCALMAIL_MBOX) ]; then echo == BEGIN EMAIL TRANSCRIPT == ; cat $(LOCALMAIL_MBOX) ; echo == END EMAIL TRANSCRIPT == ; fi

################################################################
# Installations are used by the CI pipeline:
# Generic:
install-python-dependencies:
	$(PYTHON) -m pip install --upgrade pip
	if [ -r requirements.txt ]; then $(PYTHON) -m pip install --user -r requirements.txt ; else echo no requirements.txt ; fi

# Includes ubuntu dependencies
install-ubuntu:
	echo on GitHub, we use this action instead: https://github.com/marketplace/actions/setup-ffmpeg
	which ffmpeg || sudo apt install ffmpeg
	$(PYTHON) -m pip install --upgrade pip
	if [ -r requirements-ubuntu.txt ]; then $(PYTHON) -m pip install --user -r requirements-ubuntu.txt ; else echo no requirements-ubuntu.txt ; fi
	if [ -r requirements.txt ]; then $(PYTHON) -m pip install --user -r requirements.txt ; else echo no requirements.txt ; fi

# Includes MacOS dependencies managed through Brew
install-macos:
	brew update
	brew upgrade
	brew install python3
	brew install libmagic
	brew install ffmpeg
	$(PYTHON) -m pip install --upgrade pip
	if [ -r requirements-macos.txt ]; then $(PYTHON) -m pip install --user -r requirements-macos.txt ; else echo no requirements-macos.txt ; fi
	if [ -r requirements.txt ]; then $(PYTHON) -m pip install --user -r requirements.txt ; else echo no requirements.txt ; fi

# Includes Windows dependencies
install-windows:
	$(PYTHON) -m pip install --upgrade pip
	if [ -r requirements-windows.txt ]; then $(PYTHON) -m pip install --user -r requirements-ubuntu.txt ; else echo no requirements-ubuntu.txt ; fi
	if [ -r requirements.txt ]; then $(PYTHON) -m pip install --user -r requirements.txt ; else echo no requirements.txt ; fi

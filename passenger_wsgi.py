"""
passenger_wsgi.py script to switch to python3 and use Bottle

To reload:

$ touch tmp/restart.txt
(or)
$ make touch
"""

import sys
import os
import os.path

DESIRED_PYTHON = 'python3'
HOME = os.getenv('HOME')
DREAMHOST_PYTHON_BINDIR = os.path.join( HOME, 'opt/bin')
DUMP_VARS = False

def dump_vars(f):
    """Send the list of variables to output for debugging"""
    for (k,v) in os.environ.items():
        f.write(k + "=" + v + "\n")
        f.flush()

def redirect_stderr():
    """Make stderr go to a file"""
    # pylint: disable=unspecified-encoding
    with open( os.path.join( os.getenv('HOME'), 'error.log') ,'a') as errfile:
        os.close(sys.stderr.fileno())
        os.dup2(errfile.fileno(), sys.stderr.fileno())
        if DUMP_VARS:
            dump_vars(errfile)

def redirect_stdout():
    """Make stderr go to a file"""
    # pylint: disable=unspecified-encoding
    with open( os.path.join( os.getenv('HOME'), 'access.log.app') ,'a') as accfile:
        os.close(sys.stdout.fileno())
        os.dup2(accfile.fileno(), sys.stdout.fileno())

if 'IN_PASSENGER' in os.environ:
    # Send error to error.log, but not when running under pytest
    redirect_stderr()
    #redirect_stdout()

    # Use python of choice
    if DREAMHOST_PYTHON_BINDIR not in os.environ['PATH']:
        os.environ['PATH'] = DREAMHOST_PYTHON_BINDIR + ":" + os.environ['PATH']

    os.environ['PYTHONDONTWRITEBYTECODE'] = os.path.join( HOME, '.__pycache__')

    if DESIRED_PYTHON not in sys.executable:
        os.execlp(DESIRED_PYTHON, DESIRED_PYTHON, *sys.argv)
    else:
        # If we get here, we are running under the DESIRED_PYTHON
        import bottle_app
        application = bottle_app.app()

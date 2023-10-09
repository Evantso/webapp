from jinja2.nativetypes import NativeEnvironment
import time
import mailer
import sys
import os
import uuid
import logging
import pytest
import configparser

from os.path import abspath, dirname, join

sys.path.append(dirname(dirname(abspath(__file__))))

MSG = """to: {{ to_addrs }}
from: {{ from_addr }}
subject: This is a test subject {{ guid }}

This is a test message.
"""

guid = str(uuid.uuid4())

# https://realpython.com/python-sleep/#adding-a-python-sleep-call-with-decorators

# SKIP_IF = ('GITHUB_JOB' in os.environ) or ('SKIP_MAILER_TEST' in os.environ)
SKIP_IF = False

USE_LOCALMAIL = True

if USE_LOCALMAIL:
    localmail_config = configparser.ConfigParser()
    FNAME = join(dirname(__file__),"localmail_config.ini")
    localmail_config.read( FNAME )
    if 'smtp' not in localmail_config:
        logging.error('LOCALMAIL FNAME: %s',FNAME)
        logging.error('LOCALMMAIL config: %s',localmail_config)
        logging.error('LOCALMAIL file: %s',open(FNAME).read())


@pytest.mark.skipif(SKIP_IF, reason="does not run on GitHub - outbound SMTP is blocked")
def test_send_message():
    TEST_USER_EMAIL = os.environ['TEST_USER_EMAIL']
    DO_NOT_REPLY_EMAIL = 'do-not-reply@planttracer.com'

    TO_ADDRS = [TEST_USER_EMAIL]
    msg_env = NativeEnvironment().from_string(MSG)
    msg = msg_env.render(to_addrs=",".join(TO_ADDRS),
                         from_addr=TEST_USER_EMAIL,
                         guid=guid)

    DRY_RUN = False
    if USE_LOCALMAIL:
        smtp_config = localmail_config['smtp']
    else:
        smtp_config = mailer.smtp_config_from_environ()
        smtp_config['SMTP_DEBUG'] = 'YES'
    mailer.send_message(from_addr=DO_NOT_REPLY_EMAIL,
                        to_addrs=TO_ADDRS,
                        smtp_config=smtp_config,
                        dry_run=DRY_RUN,
                        msg=msg
                        )

    # Now let's see if the message got delivered evey 100 msec and then delete it
    # Wait for up to 5 seconds
    def cb(num, M):
        if guid in M['subject']:
            return mailer.DELETE

    if USE_LOCALMAIL:
        imap_config = localmail_config['imap']
    else:
        imap_config = mailer.imap_config_from_environ()
    for i in range(50):
        deleted = mailer.imap_inbox_scan(imap_config, cb)
        if deleted > 0:
            break

        logging.warning("response %s not found. Sleep again count %d", guid, i)
        time.sleep(0.1)
    if deleted == 0:
        raise RuntimeError("Could not delete test message")


if __name__ == "__main__":
    # Test program for listing, deleting a message by number, or deleting all messages in imap box
    import argparse
    parser = argparse.ArgumentParser(description='IMAP cli',
                                     formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('--list', action='store_true')
    parser.add_argument('--delete_all', action='store_true')
    args = parser.parse_args()

    def m_lister(num, M):
        print(num, M['subject'])

    def m_delete_all(num, M):
        print("will delete", num, M['subject'])
        return mailer.DELETE

    if args.list:
        func = m_lister
    elif args.delete_all:
        func = m_delete_all
    else:
        raise RuntimeError("specify an action")
    mailer.imap_inbox_scan(mailer.imap_config_from_environ(), func)

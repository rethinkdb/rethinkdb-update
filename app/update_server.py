from flask import Flask, jsonify, request, current_app
from functools import wraps
from werkzeug.routing import BaseConverter
from werkzeug.contrib.fixers import ProxyFix
import yaml
import re
import datetime
import logging
import os
import sys
import Queue
import threading


# Configuration and static variables
def open_yaml(f):
    return open(os.path.join(os.path.dirname(os.path.realpath(__file__)), f))
try:
    config = yaml.load(open_yaml('config.yaml'))
except IOError:
    print "No configuration file found (see " \
        + "config.example.yaml for a sample configuration.)"
    sys.exit()

LOG_DIR = config['log_dir']
SCRIPT_DIR = os.path.dirname(os.path.realpath(__file__))


minor_queue = Queue.Queue()
periodic_queue = Queue.Queue()


def checkin_logger(path, queue):
    """Log checkins on specified queue."""
    logger = logging.getLogger("%s-consumer" % path)
    log_dir = os.path.abspath(os.path.join(SCRIPT_DIR, LOG_DIR, path))
    logger.debug("Log directory %s", log_dir)
    if not os.path.exists(log_dir):
        logger.warning("Log directory %s didn't exist: making it", log_dir)
        os.makedirs(log_dir)

    last_checkin = None
    log_file = None
    while True:
        list = queue.get()
        now = datetime.datetime.now()
        if now != last_checkin:
            logger.info("Rotating log files")
            if log_file is not None:
                log_file.close()
            pathname = os.path.join(log_dir, now.strftime("%Y-%m-%d") + ".log")
            log_file = open(pathname, "a", 1)  # line buffering
        log_file.write('\t'.join([str(now)] + list))
        log_file.write('\n')
        queue.task_done()


t = threading.Thread(target=checkin_logger, args=("minor", minor_queue))
t.daemon = True
t.start()
t = threading.Thread(target=checkin_logger, args=("periodic", periodic_queue))
t.daemon = True
t.start()


# The version is of the type X.Y.Z-...
def convert_version(raw_version):
    match = re.search('^([0-9]+\.[0-9]+\.[0-9]+).*', raw_version)
    version = None
    if match is not None and len(match.groups()) >= 1:
        version = match.group(1)

    split_version = []
    if version is not None:
        str_split_version = version.split('.')
        for string_version in str_split_version:
            split_version.append(int(string_version))
    return split_version


def support_jsonp(func):
    """Wraps JSONified output for JSONP requests."""
    @wraps(func)
    def decorated_function(*args, **kwargs):
        callback = request.args.get('callback', False)
        if callback:
            data = str(func(*args, **kwargs).data)
            content = str(callback) + '(' + data + ')'
            mimetype = 'application/javascript'
            return current_app.response_class(content, mimetype=mimetype)
        else:
            return func(*args, **kwargs)
    return decorated_function


# Load data
with open(os.path.join(SCRIPT_DIR, 'version.yaml'), 'r') as f:
    data = yaml.load(f)
last_version = convert_version(data['last_version'])
last_version_str = data['last_version']
link_changelog = data['changelog_link']

app = Flask(__name__)

if config['proxy']:
    print 'Behind a proxy.'
    app.wsgi_app = ProxyFix(app.wsgi_app)


class RegexConverter(BaseConverter):
    def __init__(self, url_map, *items):
        super(RegexConverter, self).__init__(url_map)
        self.regex = items[0]

app.url_map.converters['regex'] = RegexConverter


@app.route('/update_for/<regex("[0-9\.]+.*"):version>')
@support_jsonp
def update_for(version):
    minor_queue.put([version, request.remote_addr or '',
                     request.headers.get('User-Agent') or '',
                     request.headers.get('Accept-Language') or ''])

    user_version = convert_version(version)
    if len(user_version) == 0:
        return jsonify(status="error",
                       error="Could not parse the version of RethinkDB")
    elif user_version < last_version:
        return jsonify(status="need_update",
                       last_version=last_version_str,
                       link_changelog=link_changelog)
    else:
        return jsonify(status="ok")


def munge(form, key):
    """Appropriately process form data for our use.

    Currently uses 'NA' if no data was given, and strips whitespace.
    """
    return form.get(key, 'NA').strip()


@app.route("/checkin", methods=['POST'])
def process_checkin():
    """Process periodic checkins from servers."""
    app.logger.debug("Saw request %s", request.form)
    version = request.form['Version']
    periodic_queue.put([version, request.remote_addr or '',
                        munge(request.form, 'Number-Of-Servers'),
                        munge(request.form, 'Uname'),
                        munge(request.form, 'Cooked-Number-Of-Tables'),
                        munge(request.form, 'Cooked-Size-Of-Shards')])

    user_version = convert_version(version)
    if len(user_version) == 0:
        return jsonify(status="error",
                       error="Could not parse the version of RethinkDB")
    elif user_version < last_version:
        return jsonify(status="need_update",
                       last_version=last_version_str,
                       link_changelog=link_changelog)
    else:
        return jsonify(status="ok")


# Turn logging on by uncommenting this line
if config['logging']:
    loglevel = logging.DEBUG
else:
    loglevel = logging.CRITICAL
logging.basicConfig(level=loglevel)

# Kick everything off
if __name__ == '__main__':
    import cherrypy
    # We use the CherryPy server because it's easy to deploy,
    # more robust than the Flask dev server, and doesn't have
    # problems with Python threads (aka APScheduler)
    cherrypy.tree.graft(app, '/')
    cherrypy.config.update({
        'server.socket_host': config['server']['host'],
        'server.socket_port': config['server']['port'],
        })
    cherrypy.engine.start()
    cherrypy.engine.block()

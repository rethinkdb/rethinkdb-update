import yaml
import re
import datetime
import logging
import os
import sys
import queue
import threading

from flask import Flask, jsonify, request, current_app
from functools import wraps
from werkzeug.routing import BaseConverter
from werkzeug.middleware.proxy_fix import ProxyFix


# Configuration and static variables
def load_config(file_name):
    config_path = os.path.join(os.path.dirname(os.path.realpath(__file__)), file_name)
    try:
        with open(config_path, "r") as f:
            return yaml.safe_load(f)
    except IOError:
        print(f"No configuration file found (see {file_name}.example for a sample configuration.)")
        sys.exit()


config = load_config("config.yaml")
LOG_DIR = config["log_dir"]
SCRIPT_DIR = os.path.dirname(os.path.realpath(__file__))

minor_queue = queue.Queue()
periodic_queue = queue.Queue()


def setup_logger(path, queue):
    """Log checkins on specified queue."""
    logger = logging.getLogger(f"{path}-consumer")
    log_dir = os.path.abspath(os.path.join(SCRIPT_DIR, LOG_DIR, path))
    logger.debug(f"Log directory {log_dir}")
    if not os.path.exists(log_dir):
        logger.warning(f"Log directory {log_dir} didn't exist: making it")
        os.makedirs(log_dir)

    last_checkin = None
    log_file = None
    while True:
        log_data = queue.get()
        now = datetime.datetime.now()
        if now != last_checkin:
            logger.info("Rotating log files")
            if log_file:
                log_file.close()
            pathname = os.path.join(log_dir, now.strftime("%Y-%m-%d") + ".log")
            log_file = open(pathname, "a", 1)  # line buffering
            log_file.write("\t".join([str(now)] + log_data) + "\n")
        queue.task_done()


def start_logger_thread(path, queue):
    t = threading.Thread(target=setup_logger, args=(path, queue))
    t.daemon = True
    t.start()


start_logger_thread("minor", minor_queue)
start_logger_thread("periodic", periodic_queue)


def convert_version(raw_version):
    match = re.search(r"^([0-9]+\.[0-9]+\.[0-9]+).*", raw_version)
    if match:
        return [int(part) for part in match.group(1).split(".")]
    return []


def support_jsonp(func):
    """Wraps JSONified output for JSONP requests."""

    @wraps(func)
    def decorated_function(*args, **kwargs):
        callback = request.args.get("callback")
        if callback:
            data = func(*args, **kwargs).data.decode("utf-8")
            content = f"{callback}({data})"
            return current_app.response_class(
                content, mimetype="application/javascript"
            )
        return func(*args, **kwargs)

    return decorated_function


def load_version_data(file_name):
    with open(os.path.join(SCRIPT_DIR, file_name), "r") as f:
        return yaml.safe_load(f)


version_data = load_version_data("version.yaml")
last_version = convert_version(version_data["last_version"])
last_version_str = version_data["last_version"]
link_changelog = version_data["changelog_link"]

app = Flask(__name__)

if config.get("proxy"):
    print("Behind a proxy.")
    app.wsgi_app = ProxyFix(app.wsgi_app)


class RegexConverter(BaseConverter):
    def __init__(self, url_map, *items):
        super().__init__(url_map)
        self.regex = items[0]


app.url_map.converters["regex"] = RegexConverter


@app.route('/update_for/<regex("[0-9.]+.*"):version>')
@support_jsonp
def update_for(version):
    minor_queue.put(
        [
            version,
            request.remote_addr or "",
            request.headers.get("User-Agent") or "",
            request.headers.get("Accept-Language") or "",
        ]
    )

    user_version = convert_version(version)
    if not user_version:
        return jsonify(status="error", error="Could not parse the version of RethinkDB")
    if user_version < last_version:
        return jsonify(
            status="need_update",
            last_version=last_version_str,
            link_changelog=link_changelog,
        )
    return jsonify(status="ok")


def munge(form, key):
    """Appropriately process form data for our use."""
    return form.get(key, "NA").strip()


@app.route("/checkin", methods=["POST"])
def process_checkin():
    """Process periodic checkins from servers."""
    app.logger.debug(f"Saw request {request.form}")
    version = request.form["Version"]
    periodic_queue.put(
        [
            version,
            request.remote_addr or "",
            munge(request.form, "Number-Of-Servers"),
            munge(request.form, "Uname"),
            munge(request.form, "Cooked-Number-Of-Tables"),
            munge(request.form, "Cooked-Size-Of-Shards"),
        ]
    )

    user_version = convert_version(version)
    if not user_version:
        return jsonify(status="error", error="Could not parse the version of RethinkDB")
    if user_version < last_version:
        return jsonify(
            status="need_update",
            last_version=last_version_str,
            link_changelog=link_changelog,
        )
    return jsonify(status="ok")


if config.get("logging"):
    loglevel = logging.DEBUG
else:
    loglevel = logging.CRITICAL
logging.basicConfig(level=loglevel)

if __name__ == "__main__":
    import cherrypy

    cherrypy.tree.graft(app, "/")
    cherrypy.config.update({
        "server.socket_host": config["server"]["host"],
        "server.socket_port": config["server"]["port"],
    })
    cherrypy.engine.start()
    cherrypy.engine.block()

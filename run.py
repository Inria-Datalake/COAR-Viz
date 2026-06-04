import os
from app.app import app
from flask import url_for as flask_url_for

# URL prefix the app is served under. Empty locally; set URL_PREFIX=/software in
# production where a reverse proxy mounts the app at /software.
URL_PREFIX = os.environ.get('URL_PREFIX', '')

# 🔧 Force every url_for() to include the configured prefix
def prefixed_url_for(endpoint, **values):
    return URL_PREFIX + flask_url_for(endpoint, **values)

# Apply globally in Jinja templates, and expose the raw prefix so templates can
# hand it to client-side JS (window.URL_PREFIX).
app.jinja_env.globals['url_for'] = prefixed_url_for
app.jinja_env.globals['url_prefix'] = URL_PREFIX

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8040)

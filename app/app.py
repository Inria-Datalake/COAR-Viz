from flask import Flask, render_template
from pyArango.connection import Connection
from dotenv import load_dotenv
from Utils.home import home_data
from Utils.db import ensure_indexes
import os

# Load variables from a local .env (if present) before they are read below.
# Real environment variables (e.g. those injected by Docker) take precedence.
load_dotenv()

app = Flask(__name__,template_folder='templates',static_folder='static')

#app.config['ARANGO_HOST'] = 'arangodb'
app.config['ARANGO_HOST'] = os.environ.get('ARANGO_HOST')
app.config['ARANGO_PORT'] = os.environ.get('ARANGO_PORT')
app.config['ARANGO_DB'] = 'SOF-viz-COAR'
app.config['ARANGO_USERNAME'] = os.getenv('ARANGO_LOGIN', 'root')
app.config['ARANGO_PASSWORD'] = os.getenv('ARANGO_PASSWORD', 'changeme')
def init_db():
    global db
    db = Connection(
        arangoURL='http://{host}:{port}'.format(
            host=app.config['ARANGO_HOST'],
            port=app.config['ARANGO_PORT']
        ),
        username=app.config['ARANGO_USERNAME'],
        password=app.config['ARANGO_PASSWORD']
    )
    if not db.hasDatabase('SOF-viz-COAR'):
        db.createDatabase('SOF-viz-COAR')
    db = Connection(
        arangoURL='http://{host}:{port}'.format(
            host=app.config['ARANGO_HOST'],
            port=app.config['ARANGO_PORT']
        ),
        username=app.config['ARANGO_USERNAME'],
        password=app.config['ARANGO_PASSWORD']
    )[app.config['ARANGO_DB']]

init_db()  # Call the init_db function to initialize the db variable
ensure_indexes(db)  # Create the secondary indexes the FILTER-by-field AQL relies on
#sync_to_elasticsearch(db)

structure = None
global data_dashboard
data_dashboard = None
#data_dashboard = dashboard(db, structure)

from app.routes import doc_route, dashboard_route,blacklist_route, software_route, api_route, disambiguate_route, author_route, search_route, inbox

@app.route('/')
def home():
    data = home_data(db)
    return render_template('pages/home.html', data=data[0])
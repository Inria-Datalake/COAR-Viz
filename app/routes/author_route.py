from app.app import app, db
from flask import render_template, jsonify, abort
from utils.author import author_info_from_id


@app.route('/author')
def author():
    return render_template('pages/author.html')

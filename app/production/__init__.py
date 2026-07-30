from flask import Blueprint

bp = Blueprint('production', __name__, template_folder='templates')

from app.production import routes

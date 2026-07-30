from flask import Blueprint

bp = Blueprint('settings', __name__, template_folder='templates')

from app.settings import routes

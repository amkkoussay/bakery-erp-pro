from flask import Blueprint

bp = Blueprint('pos', __name__, template_folder='templates')

from app.pos import routes

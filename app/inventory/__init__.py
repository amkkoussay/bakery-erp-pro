from flask import Blueprint

bp = Blueprint('inventory', __name__, template_folder='templates')

from app.inventory import routes

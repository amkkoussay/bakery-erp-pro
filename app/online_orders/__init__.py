from flask import Blueprint

bp = Blueprint('online_orders', __name__, template_folder='templates')

from app.online_orders import routes

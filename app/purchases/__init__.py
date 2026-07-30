from flask import Blueprint

bp = Blueprint('purchases', __name__, template_folder='templates')

from app.purchases import routes

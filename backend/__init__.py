from flask import Blueprint

backend_bp = Blueprint('backend', __name__, template_folder='../templates')

from . import views  # Make sure to import the routes
from flask import Blueprint, request, current_app, jsonify
from flask_jwt_extended import jwt_required
from app.reddit import Reddit
from app._errors import Errors

mailer = Blueprint('mailer', __name__, url_prefix='/mailer')


@mailer.route('/send', methods=['POST'])
@jwt_required
def send_message():
    if not request.is_json:
        return jsonify({"error": Errors.MISSING_JSON}), 400
    username = request.json.get('username', None)
    subject = request.json.get('subject', None)
    body = request.json.get('body', None)
    if not username:
        return jsonify({"error": Errors.NO_REQUIRED_FIELD + 'username.'}), 400
    if not subject:
        return jsonify({"error": Errors.NO_REQUIRED_FIELD + 'subject.'}), 400
    if not body:
        return jsonify({"error": Errors.NO_REQUIRED_FIELD + 'body.'}), 400
    reddit = Reddit(None, current_app.config['REDDIT'])
    reddit.send_message(username, subject, body)

    return jsonify({'success': 'Sent a message to {}.'.format(request.form['username'])}), 200
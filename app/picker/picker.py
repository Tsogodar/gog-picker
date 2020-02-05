from flask import Blueprint, request, current_app, jsonify
from flask_jwt_extended import jwt_required
from app.picker.random_org import Random
from app.reddit import Reddit
import praw

picker = Blueprint('picker', __name__, url_prefix='/picker')


class GogPicker:
    random = Random(current_app.config['RANDOM_ORG_API_KEY'])

    def _remove_duplicates(self, items):
        return list(dict.fromkeys(items))

    def pick_winners(self, items, n):
        no_duplicates = self._remove_duplicates(items)
        if n >= len(no_duplicates):
            return self.random.items(no_duplicates, len(no_duplicates))
        return self.random.items(no_duplicates, n)


@picker.route('/pick', methods=['POST'])
@jwt_required
def pick_winners():
    if not request.is_json:
        return jsonify({"error": "Missing JSON in request."}), 400
    usernames = request.json.get('usernames', None)
    n = request.json.get('n', None)
    if not usernames:
        return jsonify({'error': 'No required JSON field: usernames.'}), 400
    if not n:
        return jsonify({'error': 'No required JSON fied: n.'}), 400
    gog_picker = GogPicker()

    return jsonify(gog_picker.pick_winners(usernames, n)), 200


@picker.route('/url/valid', methods=['POST'])
@jwt_required
def is_url_valid():
    if not request.is_json:
        return jsonify({"error": "Missing JSON in request."}), 400
    url = request.json.get('url', None)
    if not url:
        return jsonify({'error': 'No required JSON field: url.'}), 400
    reddit = Reddit(None, current_app.config['REDDIT'])
    submission = reddit.get_submission(url)
    if 'error' in submission:
        return jsonify(submission), 400

    return jsonify({'success': 'Valid URL.'}), 200
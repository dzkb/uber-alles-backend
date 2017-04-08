from flask import Flask
from flask import request
import decorators.flask_decorators as decorators
import requests
from config.config import Firebase as Firebase_config
from firebase import Firebase
import json

app = Flask(__name__)

@app.route('/', methods=['GET', 'POST'])
def hello_world():
    return Firebase_config.SERVER_KEY

@app.route('/fares/<fare_id>', methods=['DELETE'])
def handle_fares_id(fare_id):
    return "to_delete: " + fare_id

@app.route('/fares', methods=['GET', 'POST'])
def handle_fares():
    return "fares"

@app.route('/acceptedFares/<fare_id>', methods=['POST', 'DELETE'])
def handle_accepted_fares_id(fare_id):
    return "accepted_fares: " + fare_id

@app.route('/acceptedFares', methods=['GET'])
def handle_accepted_fares():
    return "accepted_fares"

@app.route('/test/messaging', methods=['GET'])
@decorators.content_type(type="application/json")
def handle_test_messaging():
    to_device = request.args.get('to')
    notification = request.args.get('notification')

    headers = {"Content-type": "application/json", "Authorization": "key=" + Firebase_config.SERVER_KEY}
    payload = {"to": to_device, "notification": {"title": "Powiadomienie", "body": notification}}
    message_request = requests.post('https://fcm.googleapis.com/fcm/send', headers=headers, data=json.dumps(payload))
    return message_request.content
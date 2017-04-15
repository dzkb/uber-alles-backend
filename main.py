from flask import Flask
from flask import request
from flask import Response
import decorators.flask_decorators as decorators
import requests
from config.config import Firebase as Firebase_config
from firebase import Firebase
import json
import pyrebase

app = Flask(__name__)
firebase = pyrebase.initialize_app(Firebase_config.CONFIG)
firebase_auth = firebase.auth()
firebase_db = firebase.database()

@app.route('/', methods=['GET', 'POST'])
# @decorators.content_type(type="application/json")
def hello_world():
    return str(request.authorization)
    return str(firebase_auth.sign_in_with_email_and_password("608132320@dzakub.com", "123456"))
    # return firebase_auth.create_user_with_email_and_password("608132320@dzakub.com", "123456")


@app.route('/fares/<fare_id>', methods=['DELETE'])
@decorators.content_type(type="application/json")
def handle_fares_id(fare_id):
    return "to_delete: " + fare_id


@app.route('/fares', methods=['GET', 'POST'])
@decorators.content_type(type="application/json")
def handle_fares():
    return "fares"


@app.route('/acceptedFares/<fare_id>', methods=['POST', 'DELETE'])
@decorators.content_type(type="application/json")
def handle_accepted_fares_id(fare_id):
    return "accepted_fares: " + fare_id


@app.route('/acceptedFares', methods=['GET'])
@decorators.content_type(type="application/json")
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

@app.route('/users', methods=['POST'])
@decorators.content_type(type="application/json")
def handler_users():
    userdata = request.get_json()
    assert userdata["phoneNumber"] is not None

    userToken = None
    try:
        firebase_response = firebase_auth.create_user_with_email_and_password(
            str(userdata["phoneNumber"]) + "@dzakub.com",
            userdata["password"])
    except:
        response = Response(json.dumps({"error" : "Invalid data or user already exists"}), status=400)
        return response

    userToken = firebase_response["idToken"]
    assert userToken is not None

    del userdata["password"]
    firebase_db.child("users").child(userdata["phoneNumber"]).set(userdata, userToken)

    return str(firebase_response)

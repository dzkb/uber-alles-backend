from flask import Flask
from flask import request
from flask import Response
import decorators.flask_decorators as decorators
import requests
import json
import pyrebase
import pytz
import time
from pyfcm import FCMNotification
from uberlogic import messaging
from datetime import datetime
from config.config import Firebase as Firebase_config
from config.responses import Responses

app = Flask(__name__)
firebase = pyrebase.initialize_app(Firebase_config.CONFIG)
firebase_auth = firebase.auth()
firebase_db = firebase.database()
firebase_messaging_service = FCMNotification(api_key=Firebase_config.SERVER_KEY)

swagger_uri = "https://app.swaggerhub.com/apis/dzkb/UberAlles-backend/1.0.0"

@app.route('/', methods=['GET', 'POST'])
# @decorators.content_type(type="application/json")
def hello_world():
    return Response(status=303, headers={"Location": swagger_uri})


@app.route('/fares/<fare_id>', methods=['DELETE'])
@decorators.content_type(type="application/json")
def handle_fares_id(fare_id):
    if request.authorization is None:
        return Response(json.dumps({"error": Responses.AUTH_REQUIRED}), status=401)

    user_token = authenticate(request.authorization.username + Firebase_config.USER_DOMAIN,
                             request.authorization.password)
    if user_token is None:
        return Response(json.dumps({"error": Responses.AUTH_ERROR}), status=401)

    user_phone = request.authorization.username

    fare_data = firebase_db.child("fares").child(fare_id).get(user_token).val()

    if fare_data is None:
        return Response(json.dumps({"error": Responses.FARE_NOT_FOUND}), status=404)
    if fare_data["clientPhone"] != user_phone:
        return Response(json.dumps({"error": Responses.AUTH_NOT_PERMITTED}), status=401)
    if fare_data["status"] == "cancelled":
        return Response(json.dumps({"error": Responses.FARE_ALREADY_CANCELLED}), status=400)

    fare_data["status"] = "cancelled"
    firebase_db.child("fares").child(fare_id).set(fare_data, user_token)

    return json.dumps(fare_data)


@app.route('/fares', methods=['GET', 'POST'])
@decorators.content_type(type="application/json")
def handle_fares():
    if request.authorization is None:
        return Response(json.dumps({"error": Responses.AUTH_REQUIRED}), status=401)

    user_token = authenticate(request.authorization.username + Firebase_config.USER_DOMAIN,
                             request.authorization.password)
    if user_token is None:
        return Response(json.dumps({"error": Responses.AUTH_ERROR}), status=401)

    user_phone = request.authorization.username

    if request.method == "GET":
        fare_data = firebase_db.child("fares").get(user_token).val()
        return json.dumps(fare_data)

    elif request.method == "POST":
        firebase_messaging = messaging.UberMessaging(firebase_messaging_service, firebase_db, user_token)
        fare_data = request.get_json()
        datetime_now = localize_datetime(datetime.now())
        datetime_now_iso = datetime_now.isoformat()

        fare_data["status"] = "placed"
        fare_data["clientPhone"] = user_phone
        fare_data["placedDate"] = datetime_now_iso
        fare_data["driverPhone"] = ""

        pushed_data = firebase_db.child("fares").push(fare_data, user_token)

        try:
            drivers_locs = firebase_db.child("localisations")\
                .order_by_child("timestamp")\
                .start_at(time.time() - 90)\
                .get(token=user_token).val()
        except IndexError:
            return Response(json.dumps({"error": Responses.NO_DRIVERS}), status=400)

        drivers_tokens = [x["registrationToken"] for x in list(drivers_locs.values())]
        payload = {"clientPhone": user_phone,
                   "startingPoint": fare_data["startingPoint"],
                   "endingPoint": fare_data["endingPoint"],
                   "startingDate": fare_data["startingDate"]}
        firebase_messaging.send_to_many(drivers_tokens, payload)
        response_data = {"id": pushed_data["name"], "requestDate": datetime_now_iso}

        return json.dumps(response_data)


@app.route('/acceptedFares/<fare_id>', methods=['POST', 'DELETE'])
@decorators.content_type(type="application/json")
def handle_accepted_fares_id(fare_id):
    if request.authorization is None:
        return Response(json.dumps({"error": Responses.AUTH_REQUIRED}), status=401)

    user_token = authenticate(request.authorization.username + Firebase_config.USER_DOMAIN,
                             request.authorization.password)
    if user_token is None:
        return Response(json.dumps({"error": Responses.AUTH_ERROR}), status=401)

    username = request.authorization.username
    if request.method == "POST":
        fare_data = firebase_db.child("fares").child(fare_id).get(user_token).val()

        if fare_data is None:
            return Response(json.dumps({"error": Responses.FARE_NOT_FOUND}), status=404)
        if fare_data["status"] == "in_progress":
            return Response(json.dumps({"error": Responses.FARE_ALREADY_IN_PROGRESS}), status=400)

        payload = {"driverPhone": username, "status": "in_progress"}

        firebase_db.child("fares").child(fare_id).update(payload, user_token)

        fare_data = firebase_db.child("fares").child(fare_id).get(user_token).val()
        return json.dumps(fare_data)
    elif request.method == "DELETE":
        pass

    return "accepted_fares: " + fare_id


@app.route('/acceptedFares', methods=['GET'])
@decorators.content_type(type="application/json")
def handle_accepted_fares():
    if request.authorization is None:
        return Response(json.dumps({"error": Responses.AUTH_REQUIRED}), status=401)

    user_token = authenticate(request.authorization.username + Firebase_config.USER_DOMAIN,
                             request.authorization.password)
    if user_token is None:
        return Response(json.dumps({"error": Responses.AUTH_ERROR}), status=401)

    user_phone = request.authorization.username
    try:
        fare_data = firebase_db.child("fares")\
            .order_by_child("driverPhone").equal_to(user_phone)\
            .order_by_child("status").equal_to("in_progress")\
            .get(user_token).val()
    except:
        return  json.dumps({})

    return json.dumps(fare_data)
        #

    # return json.dumps(fare_data)


@app.route('/test/messaging', methods=['GET'])
@decorators.content_type(type="application/json")
def handle_test_messaging():
    to_device = request.args.get('to')
    notification = request.args.get('notification')

    headers = {"Content-type": "application/json", "Authorization": "key=" + Firebase_config.SERVER_KEY}
    payload = {"to": to_device, "notification": {"title": "Powiadomienie", "body": notification}}
    message_request = requests.post('https://fcm.googleapis.com/fcm/send', headers=headers, data=json.dumps(payload))
    return message_request.content


@app.route('/localisation', methods=['PUT'])
@decorators.content_type(type="application/json")
def handle_localisation():
    if request.authorization is None:
        return Response(json.dumps({"error": Responses.AUTH_REQUIRED}), status=401)

    user_token = authenticate(request.authorization.username + Firebase_config.USER_DOMAIN,
                             request.authorization.password)
    if user_token is None:
        return Response(json.dumps({"error": Responses.AUTH_ERROR}), status=401)

    firebase_messaging = messaging.UberMessaging(firebase_messaging_service, firebase_db, user_token)

    user_phone = request.authorization.username
    localisation_data = request.get_json()
    localisation_data["timestamp"] = int(time.time())
    localisation_data["registrationToken"] = firebase_messaging.resolve_registration_id(user_phone)

    firebase_db.child("localisations").child(user_phone).set(localisation_data, token=user_token)
    return json.dumps(localisation_data)


@app.route('/users', methods=['POST', 'GET'])
@decorators.content_type(type="application/json")
def handler_users():
    if request.method == 'POST':
        userdata = request.get_json()
        assert userdata["phoneNumber"] is not None

        user_token = None
        try:
            firebase_response = firebase_auth.create_user_with_email_and_password(
                str(userdata["phoneNumber"]) + Firebase_config.USER_DOMAIN,
                userdata["password"])
        except requests.RequestException as e:
            firebase_error_response = json.dumps({"error": json.loads(e.args[1])["error"]["message"]})
            response = Response(firebase_error_response, status=400)
            return response

        user_token = firebase_response["idToken"]
        assert user_token is not None

        del userdata["password"]
        firebase_db.child("users").child(userdata["phoneNumber"]).set(userdata, user_token)

        return json.dumps(userdata)
    else:
        if request.authorization is None:
            return Response(json.dumps({"error": Responses.AUTH_REQUIRED}), status=401)

        user_token = authenticate(request.authorization.username + Firebase_config.USER_DOMAIN,
                                 request.authorization.password)
        if user_token is None:
            return Response(json.dumps({"error": Responses.AUTH_ERROR}), status=401)

        username = request.authorization.username
        user = firebase_db.child("users").child(username).get(user_token).val()
        return json.dumps(user)


def authenticate(username, password):
    try:
        firebase_response = firebase_auth.sign_in_with_email_and_password(username, password)
        return firebase_response["idToken"]
    except requests.RequestException as e:
        return None


def localize_datetime(dt):
    dt = dt.replace(microsecond=0)
    timezone = pytz.timezone(Firebase_config.TIMEZONE)

    return timezone.localize(dt)

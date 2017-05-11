from flask import Flask
from flask import request
from flask import Response
import decorators.flask_decorators as decorators
import requests
import json
import pyrebase
import pytz
import time
import utils.math_tools as math_tools
from pyfcm import FCMNotification
from uberlogic import messaging, GoogleDistanceMatrix
from datetime import datetime
from config.config import Firebase as Firebase_config
from config.config import Google
from config.responses import Responses

app = Flask(__name__)
firebase = pyrebase.initialize_app(Firebase_config.CONFIG)
firebase_auth = firebase.auth()
firebase_db = firebase.database()
firebase_messaging_service = FCMNotification(api_key=Firebase_config.SERVER_KEY)
google_distance_service = GoogleDistanceMatrix.DistanceMatrix(Google.MAPS_API)

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


@app.route('/arrivalTimes', methods=['GET'])
@decorators.content_type(type="application/json")
def handle_arrival_times():
    if request.authorization is None:
        return Response(json.dumps({"error": Responses.AUTH_REQUIRED}), status=401)

    user_token = authenticate(request.authorization.username + Firebase_config.USER_DOMAIN,
                             request.authorization.password)
    if user_token is None:
        return Response(json.dumps({"error": Responses.AUTH_ERROR}), status=401)

    customer_latitude = request.args.get('lat')
    customer_longitude = request.args.get('lon')
    distance_matrix = GoogleDistanceMatrix.DistanceMatrix(Google.MAPS_API)

    try:
        drivers_locs = firebase_db.child("localisations")\
            .order_by_child("timestamp")\
            .start_at(time.time() - 90)\
            .get(token=user_token).val()
    except IndexError:
        return Response(json.dumps({"error": Responses.NO_DRIVERS}), status=400)

    for key in drivers_locs:
        driver_latitude = drivers_locs[key]["latitude"]
        driver_longitude = drivers_locs[key]["longitude"]
        distance_estimation = math_tools.distance2d(float(customer_latitude),
                                                    float(customer_longitude),
                                                    float(driver_latitude),
                                                    float(driver_longitude))
        drivers_locs[key]["distance_estimation"] = distance_estimation

    n = 5
    closest_n_drivers = sorted(drivers_locs.items(), key=lambda item: item[1]["distance_estimation"])[:n]
    destinations = [str(x[1]["latitude"]) + "," + str(x[1]["longitude"]) for x in closest_n_drivers]
    origins = [str(customer_latitude) + "," + str(customer_longitude)]
    distances = distance_matrix.get_distances(origins, destinations)

    if len(distances) == 0:
        return Response(json.dumps({"error": Responses.NO_ETAS}), status=400)

    etas_in_seconds = [route["duration"]["value"] for route in distances]
    etas_response = {"min": min(etas_in_seconds),
                     "max": max(etas_in_seconds),
                     "avg": sum(etas_in_seconds)/len(etas_in_seconds)}
    return json.dumps(etas_response)


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
        fare_data_query = firebase_db.child("fares").get(user_token)
        fares_list = list()
        for fare_data_item in fare_data_query.each():
            fare_data = fare_data_item.val()
            fare_data["id"] = fare_data_item.key()
            fares_list.append(fare_data)
        return json.dumps(fares_list)

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
        fare_id = pushed_data["name"]

        try:
            drivers_locs = firebase_db.child("localisations")\
                .order_by_child("timestamp")\
                .start_at(time.time() - 90)\
                .get(token=user_token).val()
        except IndexError:
            return Response(json.dumps({"error": Responses.NO_DRIVERS}), status=400)

        drivers_tokens = [x["registrationToken"] for x in list(drivers_locs.values())]
        payload = {"type": "CMFareRequest",
                   "fareID": fare_id,
                   "clientPhone": user_phone,
                   "startingPoint": fare_data["startingPoint"],
                   "endingPoint": fare_data["endingPoint"],
                   "startingDate": fare_data["startingDate"]}
        print(json.dumps(payload))
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

    fare_data = firebase_db.child("fares").child(fare_id).get(user_token).val()
    if fare_data is None:
        return Response(json.dumps({"error": Responses.FARE_NOT_FOUND}), status=404)

    firebase_messaging = messaging.UberMessaging(firebase_messaging_service, firebase_db, user_token)

    if request.method == "POST":
        if fare_data["status"] == "in_progress":
            return Response(json.dumps({"error": Responses.FARE_ALREADY_IN_PROGRESS}), status=400)

        payload = {"driverPhone": username, "status": "in_progress"}

        firebase_db.child("fares").child(fare_id).update(payload, user_token)

        fare_data = firebase_db.child("fares").child(fare_id).get(user_token).val()

        payload = {"type": "CMFareConfirmation",
                   "id": fare_id,
                   "driverPhone": fare_data["driverPhone"],
                   "driverName": "Not Implemented",
                   "carName": "Not Implemented",
                   "carPlateNumber": "Not Implemented"}

        notification = ("Informacja", "Kierowca zaakcaptował Twój przejazd")

        print(firebase_messaging.send_to_user(fare_data["clientPhone"], payload=payload, notification=notification))

        return json.dumps(fare_data)
    elif request.method == "DELETE":
        if fare_data["status"] != "in_progress":
            return Response(json.dumps({"error": Responses.FARE_CANNOT_CANCEL}), status=400)

        payload = {"status": "cancelled"}
        firebase_db.child("fares").child(fare_id).update(payload, user_token)

        fare_data = firebase_db.child("fares").child(fare_id).get(user_token).val()
        return json.dumps(fare_data)

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
    except IndexError:
        return json.dumps({})

    return json.dumps(fare_data)


@app.route('/completedFares/<fare_id>', methods=['POST'])
@decorators.content_type(type="application/json")
def handle_completed_fares(fare_id):
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

    if fare_data["status"] == "completed":
        return Response(json.dumps({"error": Responses.FARE_ALREADY_COMPLETED}), status=401)

    if fare_data["driverPhone"] != user_phone:
        return Response(json.dumps({"error": Responses.AUTH_NOT_PERMITTED}), status=400)

    firebase_messaging = messaging.UberMessaging(firebase_messaging_service, firebase_db, user_token)
    fare_data["status"] = "completed"

    firebase_db.child("fares").child(fare_id).update(fare_data, user_token)
    payload = {"type": "CMFareCompletion",
               "id": fare_id}
    notification = ("Przejazd zakończony!", "Dziękujemy za wspólną podróż")
    firebase_messaging.send_to_user(fare_data["clientPhone"], payload=payload, notification=notification)

    return json.dumps({"status": "ok"})


@app.route('/test/messaging', methods=['GET'])
@decorators.content_type(type="application/json")
def handle_test_messaging():
    to_device = request.args.get('to')
    notification = request.args.get('notification')

    headers = {"Content-type": "application/json", "Authorization": "key=" + Firebase_config.SERVER_KEY}
    payload = {"to": to_device, "notification": {"title": "Powiadomienie", "body": notification}}
    message_request = requests.post('https://fcm.googleapis.com/fcm/send', headers=headers, data=json.dumps(payload))
    return message_request.content


@app.route('/test/data/<device_id>', methods=['POST'])
@decorators.content_type(type="application/json")
def handle_test_data_messaging(device_id):
    data = request.get_json()

    headers = {"Content-type": "application/json", "Authorization": "key=" + Firebase_config.SERVER_KEY}
    payload = {"to": device_id, "data": data}
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
    # TODO: send message directly to client
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
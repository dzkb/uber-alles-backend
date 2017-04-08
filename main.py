from flask import Flask
from flask import request
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
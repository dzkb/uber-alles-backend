import requests


class DistanceMatrix:
    request_address = "https://maps.googleapis.com/maps/api/distancematrix/json"

    def __init__(self, key):
        self.api_key = key

    def make_request(self, origins_string, destinations_string):
        payload = {"origins": origins_string, "destinations": destinations_string, "key": self.api_key}
        return requests.get(self.request_address, params=payload)

    def get_distances(self, origins, destinations):
        origins_string = "|".join(origins)
        destinations_string = "|".join(destinations)

        request = self.make_request(origins_string, destinations_string)
        response = request.json()

        destination_addresses = response["destination_addresses"]
        origin_addresses = response["origin_addresses"]

        result_distances = list()
        for i in range(len(response["rows"])):
            row_elements = response["rows"][i]["elements"]
            for j in range(len(row_elements)):
                if (row_elements[j]["status"] != "ZERO_RESULTS"):
                    distance_item = dict()
                    distance_item["origin"] = origin_addresses[i]
                    distance_item["destination"] = destination_addresses[j]
                    distance_item["distance"] = response["rows"][i]["elements"][j]["distance"]
                    distance_item["duration"] = response["rows"][i]["elements"][j]["duration"]
                    result_distances.append(distance_item)

        return result_distances

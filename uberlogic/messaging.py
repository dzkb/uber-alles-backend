class UberMessaging:

    def __init__(self, fcm_service, db_service, user_token, username):
        self.fcm = fcm_service
        self.db = db_service
        self.user_token = user_token
        self.username = username

    def send_to_user(self, recipient_phone, payload):
        registration_id = self.resolve_registration_id(recipient_phone)
        result = self.fcm.notify_single_device(registration_id=registration_id, data_message=payload)
        return result

    def resolve_registration_id(self, phone_number):
        registration_id = self.db\
            .child("users")\
            .child(phone_number)\
            .child("registrationToken")\
            .get(token=self.user_token).val()
        return registration_id
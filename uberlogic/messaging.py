class UberMessaging:

    def __init__(self, fcm_service, db_service, user_token):
        self.fcm = fcm_service
        self.db = db_service
        self.user_token = user_token

    def send_to_user(self, recipient_phone, payload=None, notification=None):
        title = body = None
        if notification is not None:
            title, body = notification
        registration_id = self.resolve_registration_id(recipient_phone)
        result = self.fcm.notify_single_device(registration_id=registration_id,
                                               data_message=payload,
                                               message_title=title,
                                               message_body=body)
        return result

    def send_to_many(self, recipient_ids, payload=None, notification=None):
        title = body = None
        if notification is not None:
            title, body = notification
        result = self.fcm.notify_multiple_devices(registration_ids=recipient_ids,
                                                  data_message=payload,
                                                  message_title=title,
                                                  message_body=body)
        return result

    def send_to_many_by_phones(self, recipient_phones, payload=None, notification = None):
        recipient_ids = [self.resolve_registration_id(phone) for phone in recipient_phones]
        self.send_to_many(recipient_ids, payload=payload, notification=notification)

    def resolve_registration_id(self, phone_number):
        registration_id = self.db\
            .child("users")\
            .child(phone_number)\
            .child("registrationToken")\
            .get(token=self.user_token).val()
        return registration_id

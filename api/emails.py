from _common import JsonHandler, list_emails


class handler(JsonHandler):
    GET_FN = staticmethod(lambda: {"files": list_emails()})

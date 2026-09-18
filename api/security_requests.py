from _common import JsonHandler, list_security_requests


class handler(JsonHandler):
    GET_FN = staticmethod(lambda: {"files": list_security_requests()})

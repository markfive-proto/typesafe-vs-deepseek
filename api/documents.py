from _common import JsonHandler, list_docs


class handler(JsonHandler):
    GET_FN = staticmethod(lambda: {"files": list_docs()})

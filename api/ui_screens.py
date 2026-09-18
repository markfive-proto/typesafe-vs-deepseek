from _common import JsonHandler, list_ui_screens


class handler(JsonHandler):
    GET_FN = staticmethod(lambda: {"files": list_ui_screens()})

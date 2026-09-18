from _common import JsonHandler, list_design_screens


class handler(JsonHandler):
    GET_FN = staticmethod(lambda: {"files": list_design_screens()})

from _common import JsonHandler, R


class handler(JsonHandler):
    GET_FN = staticmethod(lambda: {"queries": {k: v["text"] for k, v in R.QUERIES.items()}})

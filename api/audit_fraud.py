from _common import JsonHandler, F


class handler(JsonHandler):
    POST_FN = (lambda body: body.get("file", ""), F.classify, "file")

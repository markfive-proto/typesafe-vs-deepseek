from _common import JsonHandler, S


class handler(JsonHandler):
    POST_FN = (lambda body: body.get("file", ""), S.classify, "file")

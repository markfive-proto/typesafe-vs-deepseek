from _common import JsonHandler, N


class handler(JsonHandler):
    POST_FN = (lambda body: body.get("file", ""), N.classify, "file")

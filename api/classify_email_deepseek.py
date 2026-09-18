from _common import JsonHandler, E


class handler(JsonHandler):
    POST_FN = (lambda body: body.get("file", ""), E.classify_via_deepseek, "file")

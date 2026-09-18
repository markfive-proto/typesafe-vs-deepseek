from _common import JsonHandler, G


class handler(JsonHandler):
    POST_FN = (lambda body: body.get("file", ""), G.classify_via_deepseek, "file")

from _common import JsonHandler, D


class handler(JsonHandler):
    POST_FN = (lambda body: body.get("file", ""), D.classify_via_openai, "file")

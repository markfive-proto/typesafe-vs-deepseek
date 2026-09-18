from _common import JsonHandler, U


class handler(JsonHandler):
    POST_FN = (lambda body: body.get("file", ""), U.classify_via_openai, "file")

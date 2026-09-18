from _common import JsonHandler, R


class handler(JsonHandler):
    POST_FN = (lambda body: body.get("query", ""), R.rerank_deepseek, "query")

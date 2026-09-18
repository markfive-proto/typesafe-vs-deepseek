from _common import JsonHandler, list_fraud_transactions


class handler(JsonHandler):
    GET_FN = staticmethod(lambda: {"files": list_fraud_transactions()})

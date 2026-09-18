from _common import JsonHandler, list_recon_pairs


class handler(JsonHandler):
    GET_FN = staticmethod(lambda: {"files": list_recon_pairs()})

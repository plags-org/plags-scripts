class approx:
    def __init__(self, places=7, *, delta=None):
        assert (places is None) ^ (delta is None)
        self.places = places
        self.delta = delta


class printed:
    def __init__(self, *args, sep=' ', end='\n'):
        import io
        out = io.StringIO()
        print(*args, sep=sep, end=end, file=out)
        self.output = out.getvalue()


class stdout:
    def __init__(self, obj):
        self.output = str(obj)

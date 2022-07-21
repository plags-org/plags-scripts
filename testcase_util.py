class approx:
    def __init__(self, places=7, *, delta=None):
        assert (places is None) ^ (delta is None)
        self.places = places
        self.delta = delta

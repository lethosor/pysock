import pysock, pickle, zlib
class PickleProtocol(pysock.Protocol):
    def encode(self, msg):
        return zlib.compress(pickle.dumps(msg, protocol=2))
    def decode(self, msg):
        return pickle.loads(zlib.decompress(msg))
    
    

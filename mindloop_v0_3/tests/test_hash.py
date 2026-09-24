from mindloop.evomap_gep import EvoMapGEPClient

def test_hash_is_deterministic():
    c = EvoMapGEPClient()
    a = {"type":"Gene","summary":"x","model_name":"a"}
    b = {"summary":"x","type":"Gene","model_name":"b"}
    assert c._canonical_hash(a) == c._canonical_hash(b)

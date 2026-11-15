"""Three-resource admission and independent raw hashes; Python-only decoder."""
from .formats import need, sha

PACKED = (
    ('6d5583b6c26f6a60fe1326d550e8272091bcb980d41eefacac21799e050d3047', 49464),
    ('c02ccb4ac8f003facabc444d38fab41387cb9965c594ee5a3abdc025f4732585', 33128),
    ('8b22dfc8334b16283673474271f7714382f2a8ae52d315bcf58c868c55d9347d', 1333),
)


RAW_SHA = (
    '0f58c2a30b34303bb65be5845573b9118f1d95b26c0327ccb774067525416034',
    '4f38df0a6cc361bae9e129afa12074535dbbfd1b1d8b5296307d88c88de1fd5c',
    'bda8d8d2012dfc0c8371cd18de89ee33dcd4a454084f475ceb6bbb999656c288',
)


def require_backend():
    return PythonCodec()


class PythonCodec:
    def decode(self, packed, expected):
        need(type(packed) is bytes and type(expected) is int and
             0 < len(packed) <= 65536 and (sha(packed), expected) in PACKED,
             'Unrecognized compressed resource; decoder was not called.')
        index = PACKED.index((sha(packed), expected))
        from .kraken import decode
        raw = decode(packed, expected)
        need(len(raw) == expected and sha(raw) == RAW_SHA[index],
             'Decoded resource integrity mismatch.')
        return raw

    def close(self):
        pass  # Uniform builder lifecycle; Python decoding holds no resources.

# UUID

**Symbol:** `ü`

## Description

Instances of the UUID class represent UUIDs as specified in RFC 4122.
UUID objects are immutable, hashable, and usable as dictionary keys.
Converting a UUID to a string with str() yields something in the form
'12345678-1234-1234-1234-123456789abc'.  The UUID constructor accepts
five possible forms: a similar string of hexadecimal digits, or a tuple
of six integer fields (with 32-bit, 16-bit, 16-bit, 8-bit, 8-bit, and
48-bit values respectively) as an argument named 'fields', or a string
of 16 bytes (with all the integer fields in big-endian order) as an
argument named 'bytes', or a string of 16 bytes (with the first three
fields in little-endian order) as an argument named 'bytes_le', or a
single 128-bit integer as an argument named 'int'.

UUIDs have these read-only attributes:

    bytes       the UUID as a 16-byte string (containing the six
                integer fields in big-endian byte order)

    bytes_le    the UUID as a 16-byte string (with time_low, time_mid,
                and time_hi_version in little-endian byte order)

    fields      a tuple of the six integer fields of the UUID,
                which are also available as six individual attributes
                and two derived attributes:

        time_low                the first 32 bits of the UUID
        time_mid                the next 16 bits of the UUID
        time_hi_version         the next 16 bits of the UUID
        clock_seq_hi_variant    the next 8 bits of the UUID
        clock_seq_low           the next 8 bits of the UUID
        node                    the last 48 bits of the UUID

        time                    the 60-bit timestamp
        clock_seq               the 14-bit sequence number

    hex         the UUID as a 32-character hexadecimal string

    int         the UUID as a 128-bit integer

    urn         the UUID as a URN as specified in RFC 4122

    variant     the UUID variant (one of the constants RESERVED_NCS,
                RFC_4122, RESERVED_MICROSOFT, or RESERVED_FUTURE)

    version     the UUID version number (1 through 5, meaningful only
                when the variant is RFC_4122)

    is_safe     An enum indicating whether the UUID has been generated in
                a way that is safe for multiprocessing applications, via
                uuid_generate_time_safe(3).

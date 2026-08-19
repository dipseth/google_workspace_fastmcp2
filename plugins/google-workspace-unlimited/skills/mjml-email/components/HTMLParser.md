# HTMLParser

## Description

Find tags and other markup and call handler functions.

Usage:
    p = HTMLParser()
    p.feed(data)
    ...
    p.close()

Start tags are handled by calling self.handle_starttag() or
self.handle_startendtag(); end tags by self.handle_endtag().  The
data between tags is passed from the parser to the derived class
by calling self.handle_data() with the data as argument (the data
may be split up in arbitrary chunks).  If convert_charrefs is
True the character references are converted automatically to the
corresponding Unicode character (and self.handle_data() is no
longer split in chunks), otherwise they are passed by calling
self.handle_entityref() or self.handle_charref() with the string
containing respectively the named or numeric reference as the
argument.

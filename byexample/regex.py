import sre_parse
import sre_compile

try:
    import cPickle as pickle
except ImportError:
    import pickle

class RegexCache(object):
    def __init__(self, filename):
        self.filename = filename
        self.dirty = False

        try:
            with open(filename, 'rb') as f:
                self._cache = pickle.loads(f.read())
        except:
            self._cache = {}
            self.dirty = True

    def sync(self):
        if self.dirty:
            with open(self.filename, 'wb') as f:
                f.write(pickle.dumps(self._cache))

            self.dirty = False

    def get(self, pattern, flags=0):
        ''' RegexCache.get compiles a pattern into a regex object like
            re.compile does.

            At difference with re.compile, RegexCache.get caches the
            bytecode, the internal representation of the regex
            instead of caching the whole regex object.

            If multiple times the same pattern is built, this is slower
            but enables us to serialize (pickle) the bytecode to disk.

                >>> import re
                >>> from byexample.regex import RegexCache

                >>> get = RegexCache().get

                >>> r1 = re.compile(r'foo.*bar', re.DOTALL)
                >>> r2 = get(r'foo.*bar', re.DOTALL)

                >>> r1.pattern == r2.pattern
                True

                >>> r3 = re.compile(r2) # from another regex
                >>> r4 = get(r2)  # but we don't support this
                Traceback <...>
                <...>
                ValueError: Regex pattern must be a string or bytes but it is <...>

            RegexCache.get uses internal, undocumented functions from re module.

        '''
        if not isinstance(pattern, (str, bytes)):
            raise ValueError("Regex pattern must be a string or bytes but it is %s"
                                % type(pattern))

        key = (pattern, flags)
        try:
            bytecode = self._cache[key]
        except KeyError:
            bytecode = self._pattern_to_bytecode(pattern, flags)
            self._cache[key] = bytecode
            self.dirty = True

        return self._bytecode_to_regex(pattern, bytecode)

    def _pattern_to_bytecode(self, pattern, flags=0):
        if not isinstance(pattern, (str, bytes)):
            raise ValueError("Regex pattern must be a string or bytes but it is %s"
                                % type(pattern))

        p = sre_parse.parse(pattern, flags)
        code = [i.real for i in sre_compile._code(p, flags)]

        flags = flags | p.pattern.flags
        ngroups = p.pattern.groups

        return (flags, code, ngroups, p.pattern.groupdict)

    def _bytecode_to_regex(self, pattern, bytecode):
        flags, code, ngroups, groupindex = bytecode

        # map in either direction
        indexgroup = [None] * ngroups
        for k, i in groupindex.items():
            indexgroup[i] = k

        return sre_compile._sre.compile(
            pattern, flags, code,
            ngroups-1,
            groupindex, indexgroup
        )

    def __enter__(self):
        # PATCH! TODO is a better way?!?
        self._original__sre_compile__compile = sre_compile.compile
        sre_compile.compile = self.get

        #print("Cache [%s]: %i regexs on enter" % (self.filename, len(self._cache)))
        return self

    def __exit__(self, *args, **kargs):
        sre_compile.compile = self._original__sre_compile__compile
        self.sync()
        #print("Cache [%s]: %i regexs on exit" % (self.filename, len(self._cache)))


"""
Example:
  >>> def hello():
  ...     print("hello bla world")

  >>> hello()
  hello<...>world

  ```python

  j = 2
  for i in range(4):
      j += i

  j + 3

  out:
  11
  ```

"""

import re, pexpect, sys, time
from byexample.common import log, build_exception_msg
from byexample.parser import ExampleParser
from byexample.finder import ExampleFinder
from byexample.runner import ExampleRunner, PexepctMixin

class PythonPromptFinder(ExampleFinder):
    target = 'python-prompt'

    def example_regex(self):
        return re.compile(r'''
            # Snippet consists of a PS1 line >>>
            # followed by zero or more PS2 lines.
            (?P<snippet>
                (?:^(?P<indent> [ ]*) >>>[ ]     .*)    # PS1 line
                (?:\n           [ ]*  \.\.\.   .*)*)    # PS2 lines
            \n?
            # The expected output consists of any non-blank lines
            # that do not start with PS1
            (?P<expected> (?:(?![ ]*$)     # Not a blank line
                          (?![ ]*>>>)      # Not a line starting with PS1
                         .+$\n?            # But any other line
                      )*)
            ''', re.MULTILINE | re.VERBOSE)

    def get_language_of(self, *args, **kargs):
        return 'python'

    def get_snippet_and_expected(self, match, where):
        snippet, expected = ExampleFinder.get_snippet_and_expected(self, match, where)

        snippet = self._remove_prompts(snippet, where)
        return snippet, expected

    def _remove_prompts(self, snippet, where):
        lines = snippet.split("\n")

        # all the lines starts with a prompt
        ok = all(l.startswith(">>>") or l.startswith("...") for l in lines)
        if not ok:
            raise ValueError("Incorrect prompts")

        # a space follows a prompt except when the line is just a prompt
        ok = all(l[3] == ' ' for l in lines if len(l) >= 4)
        if not ok:
            raise ValueError("Missing space after the prompt")

        # remove the prompts
        lines = (l[4:] for l in lines)

        return '\n'.join(lines)


###############################################################################
# : : : : : : : : : : : : : : : : : : : : : : : : : : : : : : : : : : : : : : #
###############################################################################
#
# The following is an extract of the doctest.py module from Python 2.7.
#
# I copied some parts verbatim as they are as private members of the doctest
# module.
# The code was released to the public domain by Tim Peters.
#
# I don't claim any right over this copied piece of code, it is copied
# for convenience
#
# I copied the license too for the records.


# Module doctest.
# Released to the public domain 16-Jan-2001, by Tim Peters (tim@python.org).
# Major enhancements and refactoring by:
#     Jim Fulton
#     Edward Loper

# Provided as-is; use at your own risk; no warranty; no promises; enjoy!


# A regular expression for handling `want` strings that contain
# expected exceptions.  It divides `want` into three pieces:
#    - the traceback header line (`hdr`)
#    - the traceback stack (`stack`)
#    - the exception message (`msg`), as generated by
#      traceback.format_exception_only()
# `msg` may have multiple lines.  We assume/require that the
# exception message is the first non-indented line starting with a word
# character following the traceback header line.
_EXCEPTION_RE = re.compile(r"""
    # Grab the traceback header.  Different versions of Python have
    # said different things on the first traceback line.
    ^(?P<hdr> Traceback\ \(
        (?: most\ recent\ call\ last
        |   innermost\ last
        ) \) :
    )
    \s* $                # toss trailing whitespace on the header.
    (?P<stack> .*?)      # don't blink: absorb stuff until...
    ^ (?P<msg> \w+ .*)   #     a line *starts* with alphanum.
    """, re.VERBOSE | re.MULTILINE | re.DOTALL)

#
#
# This is the end of the verbatim copy of some pieces of code from doctest.py
#
###############################################################################
# : : : : : : : : : : : : : : : : : : : : : : : : : : : : : : : : : : : : : : #
###############################################################################

class PythonParser(ExampleParser):
    language = 'python'

    def example_options_string_regex(self):
        # anything of the form:
        #   #  byexample:  +FOO -BAR +ZAZ=42
        if self.compatibility_mode:
            keyword = r'(?:doctest|byexample)'
        else:
            keyword = r'byexample'

        return re.compile(r'#\s*%s:\s*([^\n\'"]*)$' % keyword,
                                                    re.MULTILINE)

    def extend_option_parser(self, parser):
        '''
        Add a few extra options and if self.compatibility_mode is True,
        add all the Python doctest's options.
        '''
        parser.add_flag("py-doctest", help="enable the compatibility with doctest.")
        parser.add_flag("py-pretty-print", help="enable the pretty print enhancement.")
        parser.add_flag("py-remove-empty-lines", help="enable the deletion of empty lines (enabled by default).")

        if getattr(self, 'compatibility_mode', True):
            parser.add_flag("NORMALIZE_WHITESPACE", help="[doctest] alias for +norm-ws.")
            parser.add_flag("SKIP", help="[doctest] alias for +skip.")
            parser.add_flag("ELLIPSIS", help="[doctest] enables the ... capture.")
            parser.add_flag("DONT_ACCEPT_BLANKLINE", help="[doctest] take <BLANKLINE> as literal.")
            parser.add_flag("DONT_ACCEPT_TRUE_FOR_1", help="[doctest] ignored.")
            parser.add_flag("IGNORE_EXCEPTION_DETAIL", help="[doctest] ignore the exception details.")
            parser.add_flag("REPORT_UDIFF", help="[doctest] alias for +diff unified.")
            parser.add_flag("REPORT_CDIFF", help="[doctest] alias for +diff context.")
            parser.add_flag("REPORT_NDIFF", help="[doctest] alias for +diff ndiff.")

        return parser

    def _map_doctest_opts_to_byexample_opts(self, where):
        '''
        In compatibility mode, take all the Python doctest's options and flags
        and map them to a byexample option if possible.
        Otherwise log a message.

        Also, in compatibility mode, disable any "capture" unless the ELLIPSIS
        flag is present.

        Return a dictionary with the mapped flags; self.options is unchanged.
        '''
        options = self.options
        options.mask_default(False)
        mapped = {}
        if options['py_doctest']:
            # map the following doctest's options to byexample's ones
            if options['NORMALIZE_WHITESPACE']:
                mapped['norm_ws'] = True

            if options['SKIP']:
                mapped['skip'] = True

            if options['ELLIPSIS']:
                # enable the capture if ELLIPSIS but see also expected_from_match
                # as this byexample's option is not equivalent to doctest's one
                mapped['capture'] = True

            if options['REPORT_UDIFF']:
                mapped['diff'] = 'unified'

            if options['REPORT_CDIFF']:
                mapped['diff'] = 'context'

            if options['REPORT_NDIFF']:
                mapped['diff'] = 'ndiff'

            # the following are not supported: ignore them and print a note
            # somewhere
            if options['DONT_ACCEPT_TRUE_FOR_1']:
                log(build_exception_msg("[Note] DONT_ACCEPT_TRUE_FOR_1 flag is not supported.", where, self),
                        self.verbosity-2)

        # in compatibility mode, do not capture by default [force this]
        if self.options['py_doctest'] and 'capture' not in mapped:
            mapped['capture'] = False

        options.unmask_default()
        return mapped

    def _double_parse(self, parse_method, args, kwargs, where):
        '''
        Call parse_method at most twice.
        The first call is under compatibility mode.

        If the options parsed (in union with the options before) say that
        the compatibility mode is not ON, parse them again under
        non-compatibility mode.

        Finally, map any doctest option to a byexample option.

        Return the options parsed and mapped; self.options is unchanged.
        '''
        # let's force a compatibility mode before parsing,
        # the compatibility mode uses a parser that it is a superset of the
        # parser in non-compatibility mode so we should be safe
        self.compatibility_mode = True
        options = parse_method(*args, **kwargs)

        # temporally, merge the new options found (options) with the
        # the obtained previously (self.options)
        self.options.up(options)

        if self.options.get('py_doctest', False):
            # okay, the user really wanted to be in compatibility mode
            pass
        else:
            # ups, the user don't want this mode, re parse the options
            # in non-compatibility mode
            self.compatibility_mode = False
            options = parse_method(*args, **kwargs)

        # take the self.options and see if there are doctest flags
        # to be mapped to byexample's options
        mapped = self._map_doctest_opts_to_byexample_opts(where)

        # revert the merge
        self.options.down()

        # take the original options parsed, update them with the mapped options,
        # and return them
        options.update(mapped)
        return options

    def extract_cmdline_options(self, opts_from_cmdline):
        return self._double_parse(ExampleParser.extract_cmdline_options,
                                    args=(self, opts_from_cmdline),
                                    kwargs={},
                                    where=None)


    def extract_options(self, snippet, where):
        return self._double_parse(ExampleParser.extract_options,
                                    args=(self, snippet, where),
                                    kwargs={},
                                    where=where)

    def process_snippet_and_expected(self, snippet, expected, where):
        snippet, expected = ExampleParser.process_snippet_and_expected(self,
                                            snippet, expected, where)

        expected = self._mutate_expected_based_on_doctest_flags(expected, where)
        snippet = self._remove_empty_line_if_enabled(snippet)

        return snippet, expected

    def _mutate_expected_based_on_doctest_flags(self, expected_str, where):
        options = self.options
        options.mask_default(False)
        if options['py_doctest']:
            if not options['DONT_ACCEPT_BLANKLINE']:
                expected_str = re.sub(r'^<BLANKLINE>$', '', expected_str,
                                        flags=re.MULTILINE|re.DOTALL)

            m = _EXCEPTION_RE.match(expected_str)
            if options['ELLIPSIS'] or m:
                # we will enable the capture mode, check and warn if the example
                # contains strings like <label> that may confuse byexample and
                # or the user
                if self.capture_tag_regex().search(expected_str):
                    log(build_exception_msg("[Warn] The expected strings has <label> strings that will not be considered literal but as capture tags.", where, self),
                            self.verbosity)

            if options['ELLIPSIS']:
                ellipsis_tag = '<%s>' % self.ellipsis_marker()
                expected_str = expected_str.replace('...', ellipsis_tag)

            # yes, again, we modified the expected_str in the step before
            m = _EXCEPTION_RE.match(expected_str)
            if m:
                # make an expected string ignoring the stack trace
                # and the traceback header like doctest does.
                ellipsis_tag = '<%s>' % self.ellipsis_marker()

                msg = m.group('msg')
                if options['IGNORE_EXCEPTION_DETAIL']:
                    # we assume, like doctest does, that the first : is at
                    # the end of the class name of the exception.
                    full_class_name = msg.split(":", 1)[0]
                    class_name = full_class_name.rsplit(".", 1)[-1]
                    msg = class_name + ":"

                expected_str = '\n'.join([
                                    # a Traceback header
                                    'Traceback ' + ellipsis_tag,

                                    # the stack trace (ignored)
                                    ellipsis_tag,

                                    # the "relaxed" exception message
                                    # in Python 2.x this starts with a class
                                    # name while in Python 3.x starts with
                                    # a full name (module dot class name)
                                    #
                                    # this breaks almost all the exception
                                    # checks in doctest so this should be a nice
                                    # improvement.
                                    ellipsis_tag + msg + \
                                        (ellipsis_tag if options['IGNORE_EXCEPTION_DETAIL'] else ""),
                                    ])

                # enable the capture, this should affect to this example only
                options['capture'] = True

        options.unmask_default()
        return expected_str

    def _remove_empty_line_if_enabled(self, snippet):
        if self.options.get('py_remove_empty_lines', True):
            # remove the empty lines if they are followed by indented lines
            # if they are followed by non-indented lines, the empty lines means
            # "end the block" of code and they should not be removed or we will
            # have SyntaxError
            filtered = []
            lines = snippet.split("\n")
            for i, line in enumerate(lines[:-1]):
                if line or (not lines[i+1].startswith(" ") and lines[i+1]):
                    filtered.append(line)

            filtered.append(lines[-1])
            lines = filtered

            return '\n'.join(lines)
        return snippet

class PythonInterpreter(ExampleRunner, PexepctMixin):
    language = 'python'

    def __init__(self, verbosity, encoding, **unused):
        self.encoding = encoding

        self._PS1 = r'/byexample/py/ps1> '
        self._PS2 = r'/byexample/py/ps2> '

        PexepctMixin.__init__(self,
                                cmd=None, # patchme later
                                PS1_re = self._PS1,
                                any_PS_re = r'/byexample/py/ps\d> ')

    def _get_cmd(self, pretty_print):
        change_prompts = r'''
import sys
import pprint as _byexample_pprint

# change the prompts
sys.ps1="%s"
sys.ps2="%s"

# patch the pprint _safe_repr function
def patch_pprint_safe_repr():
    import re
    ub_marker_re = re.compile(r"^[uUbB]([rR]?[" + "\\" + chr(39) + r"\"])", re.UNICODE)
    orig_repr = _byexample_pprint._safe_repr
    def patched_repr(object, *args, **kargs):
        orepr, readable, recursive = orig_repr(object, *args, **kargs)

        _repr = ub_marker_re.sub(r"\1", orepr)
        readable = False if _repr != orepr else readable

        return _repr, readable, recursive
    _byexample_pprint._safe_repr = patched_repr

if %s:
    patch_pprint_safe_repr() # patch!

    # change the displayhook to use pprint instead of repr
    sys.displayhook = lambda s: (
                    None if s is None
                    else _byexample_pprint.PrettyPrinter(indent=1, width=80, depth=None).pprint(s))

# remove introduced symbols
del sys
del patch_pprint_safe_repr
''' % (self._PS1, self._PS2, pretty_print)

        return "/usr/bin/env python -i -c '%s'" % change_prompts

    def run(self, example, flags):
        return self._exec_and_wait(example.source,
                                    timeout=int(flags['timeout']))

    def interact(self, example, options):
        PexepctMixin.interact(self)

    def initialize(self, examples, options):
        py_doctest = options.get('py_doctest', False)
        py_pretty_print = options.get('py_pretty_print', False)
        pretty_print = (py_doctest and py_pretty_print) \
                        or not py_doctest

        # set the final command
        self.cmd = self._get_cmd(pretty_print)

        # run!
        self._spawn_interpreter()

    def shutdown(self):
        self._shutdown_interpreter()

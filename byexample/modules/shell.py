"""
Example:
  $ hello() {
  >     echo "hello bla world"
  > }

  $ hello
  hello<...>world

  $ for i in 0 1 2 3; do
  >    echo $i
  > done
  0
  1
  2
  3
"""

from __future__ import unicode_literals
import re, pexpect, sys, time
from byexample.common import constant
from byexample.parser import ExampleParser
from byexample.finder import ExampleFinder
from byexample.runner import ExampleRunner, PexepctMixin, ShebangTemplate
from byexample.executor import TimeoutException

stability = 'provisional'

class ShellPromptFinder(ExampleFinder):
    target = 'shell-prompt'

    @constant
    def example_regex(self):
        return re.compile(r'''
            (?P<snippet>
                (?:^(?P<indent> [ ]*) (?:\$)[ ]  .*)      # PS1 line
                (?:\n           [ ]*  >             .*)*)    # PS2 lines
            \n?
            ## Want consists of any non-blank lines that do not start with PS1
            (?P<expected> (?:(?![ ]*$)        # Not a blank line
                          (?![ ]*(?:\$))      # Not a line starting with PS1
                          .+$\n?              # But any other line
                      )*)
            ''', re.MULTILINE | re.VERBOSE)

    def get_language_of(self, *args, **kargs):
        return 'shell'

    def get_snippet_and_expected(self, match, where):
        snippet, expected = ExampleFinder.get_snippet_and_expected(self, match, where)

        snippet = self._remove_prompts(snippet)
        return snippet, expected

    def _remove_prompts(self, snippet):
        lines = snippet.split("\n")
        return '\n'.join(line[2:] for line in lines)

class ShellParser(ExampleParser):
    language = 'shell'

    @constant
    def example_options_string_regex(self):
        return re.compile(r'#\s*byexample:\s*([^\n\'"]*)$',
                                                    re.MULTILINE)

    def extend_option_parser(self, parser):
        parser.add_flag("stop-on-timeout", default=False, help="stop the process if it timeout.")
        parser.add_argument(
                "+stop-on-silence",
                nargs='?',
                default=False,
                const=0.2,
                type=float,
                help="stop the process if it timeout.")

class ShellInterpreter(ExampleRunner, PexepctMixin):
    language = 'shell'

    def __init__(self, verbosity, encoding, **unused):
        self.encoding = encoding

        PexepctMixin.__init__(self,
                                PS1_re = r"/byexample/sh/ps1> ",
                                any_PS_re = r"/byexample/sh/ps\d+> ")

    def get_default_cmd(self, *args, **kargs):
        return  "%e %p %a", {
                    'e': '/usr/bin/env',
                    'p': 'sh',
                    'a': [],
                    }

    def run(self, example, options):
        return PexepctMixin._run(self, example, options)

    def _run_impl(self, example, options):
        stop_on_timeout = options['stop_on_timeout'] is not False
        stop_on_silence = options['stop_on_silence'] is not False
        try:
            return self._exec_and_wait(example.source, options)
        except TimeoutException as ex:
            if stop_on_timeout or stop_on_silence:
                # get the current output
                out = ex.output

                # stop the process to get back the control of the shell.
                # this require that the job monitoring system of
                # the shell is on (set -m)
                self.interpreter.sendcontrol('z')

                # wait for the prompt, ignore any extra output
                self._expect_prompt(
                        options,
                        timeout=options['x']['dfl_timeout'],
                        prompt_re=self.PS1_re)

                self._drop_output()
                return out
            raise

    def _expect_prompt(self, options, timeout, prompt_re=None):
        if options['stop_on_silence'] is not False:
            silence_timeout = options['stop_on_silence']
            prev = 0
            while 1:
                try:
                    begin = time.time()
                    return PexepctMixin._expect_prompt(self, options, silence_timeout, prompt_re)
                except TimeoutException as ex:
                    timeout -= max(time.time() - begin, 0)
                    silence_timeout = min(silence_timeout, timeout)

                    # a real timeout
                    if timeout <= 0 or silence_timeout <= 0:
                        raise

                    # inactivity or silence detected
                    if prev >= len(ex.output):
                        raise

                    prev = len(ex.output)

        else:
            return PexepctMixin._expect_prompt(self, options, timeout, prompt_re)

    def interact(self, example, options):
        PexepctMixin.interact(self)

    def initialize(self, options):
        shebang, tokens = self.get_default_cmd()
        shebang = options['shebangs'].get(self.language, shebang)

        cmd = ShebangTemplate(shebang).quote_and_substitute(tokens)
        self._spawn_interpreter(cmd, options, wait_first_prompt=False)

        self._exec_and_wait(
'''export PS1="/byexample/sh/ps1> "
export PS2="/byexample/sh/ps2> "
export PS3="/byexample/sh/ps3> "
export PS4="/byexample/sh/ps4> "
''', options, timeout=options['x']['dfl_timeout'])
        self._drop_output() # discard banner and things like that

    def shutdown(self):
        self._shutdown_interpreter()

    def cancel(self, example, options):
        return self._abort(example, options)


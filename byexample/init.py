import sys, pkgutil, inspect, pprint

from .options import Options
from .interpreter import Interpreter
from .finder import ExampleFinder, MatchFinder
from .runner import ExampleRunner
from .checker import Checker
from .parser import ExampleParser
from .concern import Concern, ConcernComposite
from .common import log

def is_a(target_class, key_attr):
    '''
    Returns a function that will return True if its argument
    is a subclass of target_class and it has the attribute key_attr
    '''
    def _is_X(obj):
        if not inspect.isclass(obj):
            return False

        return issubclass(obj, target_class) and \
               obj is not target_class and \
               hasattr(obj, key_attr)

    return _is_X

def load_modules(dirnames, cfg):
    verbosity = cfg['verbosity']
    registry = {'interpreters': {},
                'finders': {},
                'parsers': {},
                'concerns': {},
                }
    for importer, name, is_pkg in pkgutil.iter_modules(dirnames):
        path = importer.path

        log("From '%s' loading '%s'..." % (path, name), verbosity-2)

        try:
            module = importer.find_module(name).load_module(name)
        except Exception as e:
            log("From '%s' loading '%s'...failed: %s" % (path, name, str(e)),
                                                        verbosity-2)
            continue

        log("From '%s' loaded '%s'" % (path, name), verbosity-1)
        for klass, key, what in [(Interpreter, 'language', 'interpreters'),
                                 (ExampleParser, 'language', 'parsers'),
                                 (MatchFinder, 'target', 'finders'),
                                 (Concern, 'target', 'concerns')]:

            # we are interested in any class that is a subclass of 'klass'
            # and it has an attribute 'key'
            predicate = is_a(klass, key)

            container = registry[what]
            klasses_found = inspect.getmembers(module, predicate)
            if klasses_found:
                klasses_found = list(zip(*klasses_found))[1]

                # remove already loaded
                klasses_found = set(klasses_found) - set(container.values())

            objs = [klass(**cfg) for klass in klasses_found]
            if objs:
                loaded_objs = []
                for obj in objs:
                    key_value = getattr(obj, key)
                    if key_value:
                        container[key_value] = obj
                        loaded_objs.append(obj)

                log("\n".join((" - %s" % repr(i)) for i in loaded_objs), verbosity-1)

    return registry

def get_allowed_languages(registry, selected):
    available = set([obj.language for obj in registry['interpreters'].values()] + \
                      [obj.language for obj in registry['parsers'].values()])

    selected = set(selected)
    not_found = selected - available

    if not_found:
        not_found = ', '.join(not_found)
        raise ValueError(("The following languages were specified " + \
                          "but they were not found in any module:\n -> %s\n" + \
                          "May be you forgot to add another place where to " + \
                          "find it with -m or --modules.\nRun again with -vvv to get " + \
                          "more information about why is this happening.") %
                               not_found)
    return selected

def get_encoding(encoding, verbosity):
    if sys.version_info[0] <= 2: # version major
        # we don't support a different encoding
        encoding = None

    log("Encoding: %s." % encoding, verbosity-2)
    return encoding

def init(args):
    encoding = get_encoding(args.encoding, args.verbosity)

    cfg = {
            'use_progress_bar': args.pretty == 'all',
            'use_colors': args.pretty == 'all',
            'quiet':      args.quiet,
            'verbosity':  args.verbosity,
            'encoding':   encoding,
            'output':     sys.stdout,
            'interact':   args.interact,
            }

    # if the output is not atty, disable the color anyways
    cfg['use_colors'] &= cfg['output'].isatty()

    registry = load_modules(args.modules_dirs, cfg)

    allowed_languages = get_allowed_languages(registry, args.languages)

    allowed_files = set(args.files) - set(args.skip)
    testfiles = [f for f in args.files if f in allowed_files]

    if cfg['quiet']:
        registry['concerns'].pop('progress', None)

    log("Configuration:\n%s." % pprint.pformat(cfg), cfg['verbosity']-2)
    log("Registry:\n%s." % pprint.pformat(registry), cfg['verbosity']-2)

    concerns = ConcernComposite(registry, **cfg)

    checker  = Checker(**cfg)
    options  = Options(FAIL_FAST=args.fail_fast, WS=False, PASS=False,
                       SKIP=False, ENHANCE_DIFF=args.enhance_diff,
                       TIMEOUT=args.timeout,
                       UDIFF=args.diff=='unified',
                       NDIFF=args.diff=='ndiff',
                       CDIFF=args.diff=='context',
                       INTERACT=args.interact
                       )

    options.up(args.options)

    finder = ExampleFinder(allowed_languages, registry, **cfg)
    runner = ExampleRunner(concerns, checker, **cfg)

    return testfiles, finder, runner, options

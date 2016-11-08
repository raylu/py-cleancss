# -*- coding: utf-8 -*-
"""
CleanCSS is a simple pythonic language for CSS inspired by
`CleverCSS <http://sandbox.pocoo.org/clevercss/>`_ but simpler and with less
obstrusive features.

Library usage
-------------
Import the cleancss module and call the convert() function with a file-like object.

Example::

    import cleancss
    with open('file.css') as f:
        print cleancss.convert(f)
"""
import sys
import re
from . import callbacks

version = '1.4'
copyright = '(c) 2010 Massimiliano Torromeo'
__all__ = ['convert']

class ParserError(Exception):
    """Raised on syntax errors."""

    def __init__(self, lineno, message):
        self.lineno = lineno
        Exception.__init__(self)
        self.message = message

    def __str__(self):
        return '%s (line %s)' % (
            self.message,
            self.lineno
        )

class Parser(object):
    """CCSS Parser that handles the conversion to the standard CSS syntax."""

    _r_indentation = re.compile(r'^\s*')
    _r_selector = re.compile(r'^(.+)\s*:$')
    _r_property_prefix = re.compile(r'^([^:>\s]+)->$')
    _r_definition = re.compile(r'^([^\s]+)\s*:\s*(.+)$')
    _r_comment = re.compile(r'/\*.*?\*/|(?<!:)//.*$')
    _multi_comment_start = "/*"
    _multi_comment_end = "*/"


    def __init__(self, sourcestream):
        self.sourcestream = sourcestream
        self.__callbacks = []

    def flattenSelectors(self, selectorTree):
        selectors = []
        base = selectorTree[0][:]
        tails = None
        if len(selectorTree)>1:
            tails = self.flattenSelectors(selectorTree[1:])
        for i, sel in enumerate(base):
            if tails is not None:
                for tail in tails:
                    if tail[0] == '&':
                        tail = tail[1:]
                    else:
                        tail = ' '+tail
                    selectors.append( base[i] + tail )
            else:
                selectors.append( base[i] )
        return selectors

    def toCss(self):
        level = 0
        indenter = 0
        selectorsChanged = False
        rules = []
        comment = False
        cur_rule_tree = []
        rule_prefixes = []

        lineno = 0
        for line in self.sourcestream:
            lineno += 1

            if comment:
                if self._multi_comment_end in line:
                    comment = False
                    line = line[line.index(self._multi_comment_end)+len(self._multi_comment_end):]
                else:
                    continue

            line = self._r_comment.sub('', line)

            if self._multi_comment_start in line:
                comment = True
                line = line[:line.index(self._multi_comment_start)]

            if line.strip() == "":
                continue

            indentation = self._r_indentation.match(line).group(0)
            if indenter == 0 and len(indentation)>0:
                indenter = len(indentation)

            if indenter>0 and len(indentation) % indenter != 0:
                raise ParserError(lineno, 'Indentation error')

            newlevel = 0
            if indenter > 0:
                newlevel = len(indentation) / indenter
            line = line.strip()

            if newlevel-level>1:
                raise ParserError(lineno, 'Indentation error')

            # Pop to new level
            while len(cur_rule_tree)+len(rule_prefixes)>newlevel and len(rule_prefixes)>0:
                rule_prefixes.pop()
            while len(cur_rule_tree)>newlevel:
                cur_rule_tree.pop()
            level = newlevel

            match = self._r_selector.match(line)
            if match:
                selectors = match.group(1).split(',')
                for i, sel in enumerate(selectors):
                    selectors[i] = sel.strip()
                cur_rule_tree.append(selectors)
                selectorsChanged = True
                continue

            match = self._r_property_prefix.match(line)
            if match:
                rule_prefixes.append(match.group(1))
                continue

            match = self._r_definition.match(line)
            if match:
                if len(cur_rule_tree) == 0:
                    raise ParserError(lineno, 'Selector expected, found definition')
                if selectorsChanged:
                    if cur_rule_tree[0][0].startswith('@media'):
                        new_selectors = self.flattenSelectors(cur_rule_tree[1:])
                        selectors = (cur_rule_tree[0][0], ',\n'.join(new_selectors))
                    else:
                        new_selectors = self.flattenSelectors(cur_rule_tree)
                        selectors = ',\n'.join(new_selectors)
                    rules.append((selectors, []))
                    selectorsChanged = False
                if len(rule_prefixes)>0:
                    prefixes = '-'.join(rule_prefixes) + '-'
                else:
                    prefixes = ''

                # Apply callbacks if present
                if self.__callbacks:
                    properties = []
                    for callback in self.__callbacks:
                        properties.extend( callback(match.group(1), match.group(2)) )
                else:
                    properties = [(match.group(1), match.group(2))]

                for (prop, value) in properties:
                    rules[-1][1].append("%s: %s;" % (prefixes + prop, value))
                continue

            raise ParserError(lineno, 'Unexpected item')

        output = []
        media_query = None
        for selectors, definitions in rules:
            if isinstance(selectors, tuple):
                rendered_defns = '\n\t\t'.join(definitions)
                if selectors[0] != media_query:
                    media_query = selectors[0]
                    output.append('%s {\n' % selectors[0])
                output.append('\t%s {\n\t\t%s\n\t}\n' % (selectors[1], rendered_defns))
            else:
                if media_query is not None:
                    output.append('}\n')
                    media_query = None
                rendered_defns = '\n\t'.join(definitions)
                output.append('%s {\n\t%s\n}\n' % (selectors, rendered_defns))
        if media_query is not None:
            output.append('}\n')
        return ''.join(output)

    def registerPropertyCallback(self, callback):
        """
        Registers a callback that will be called on every property parsed and can alter them

        Example::

            import cleancss

            def noop_callback(prop, value):
                return [(prop, value)]

            with open("test.ccss") as f:
                p = cleancss.Parser(f)
                p.registerPropertyCallback(noop_callback)
                print p.toCss()
        """

        self.__callbacks.append( callback )

def convert(sourcestream, callback=None):
    """Convert a CleanCSS file into a normal stylesheet."""
    parser = Parser(sourcestream)
    if callback is not None:
        parser.registerPropertyCallback(callback)
    return parser.toCss()

def main():
    import argparse, os, os.path

    parser = argparse.ArgumentParser(description="""Convert CleanCSS files to CSS.

Version {}
{}

Example usage:

> %(prog)s one.ccss two.ccss
Writes output to one.css and two.css

> %(prog)s one.ccss two.ccss -o file.css file_two.css
Writes output to file.css and file_two.css

> %(prog)s -d ~/project/css
Convert all files in a directory""".format(version, copyright), formatter_class=argparse.RawDescriptionHelpFormatter)

    parser.add_argument("input_files", nargs="*", type=argparse.FileType('r'), help="one or more .ccss files", metavar="file")
    parser.add_argument("-d", "--dir", help="specify a directory of .ccss files to convert. Overrides any other input files, and ignores -o/--out", metavar="directory")
    parser.add_argument("-r", "--recursive", action="store_true", default=False, help="look for .ccss files in subdirectories")
    parser.add_argument("-o", "--out", nargs="+", default=[], type=argparse.FileType('w'), help="files to write output to", metavar="file")
    parser.add_argument("--version", action="version", version="""CleanCSS {} - {}""".format(version, copyright))

    try:
        args = parser.parse_args()

        # if a directory is supplied, override other files
        if args.dir:
            args.out = []
            args.input_files = []
            try:
                if args.recursive:
                    # walk the directory, find all .ccss files and open them
                    for root, dirs, files in os.walk(os.path.expanduser(args.dir)):
                        for file in files:
                            if os.path.splitext(file)[1] == ".ccss":
                                args.input_files.append(open(os.path.join(root, file), "r"))
                else:
                    # list the directory, find .ccss files and open them
                    for item in os.listdir(args.dir):
                        full_name = os.path.join(args.dir, item)
                        if os.path.splitext(item)[1] == ".ccss" and os.path.isfile(full_name):
                            args.input_files.append(open(full_name, "r"))
            except Exception as e:
                parser.error(e)
        
        if not len(args.input_files):
            parser.error("No input files!")

        for file in args.input_files:
            try:
                css = convert(file)
                
                # check if there are any output files to use
                if len(args.out):
                    out_file = args.out.pop(0)
                else:
                    # if not, use file name but with .css instead of .ccss
                    name, _ = os.path.splitext(file.name)
                    out_file = open(name + ".css", "w")
                out_file.write(css)
                print("Wrote", out_file.name)
                out_file.close()
            except ParserError as e:
                print("Error in", os.path.basename(file.name) + ":", e)
    except Exception as e:
        parser.error(e)

if __name__ == '__main__':
    main()

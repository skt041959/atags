#!python3
# encoding: utf-8

import asyncio
from itertools import chain
import logging
import os
from pathlib import Path
import re
import sqlite3
import sys

from aiomultiprocess import Pool
import pygments.lexers
from pygments.token import Token
from atags.profile import profileit

logging.basicConfig(
    filename=Path.home() / '.cache/tags.log',
    filemode='a',
    format='%(asctime)s %(name)-12s %(levelname)-8s %(message)s',
    datefmt='%m-%d %H:%M',
    level=logging.DEBUG,
)
# define a Handler which writes INFO messages or higher to the sys.stderr
console = logging.StreamHandler()
console.setLevel(logging.INFO)
# set a format which is simpler for console use
formatter = logging.Formatter('%(name)-12s: %(levelname)-8s %(message)s')
# tell the handler to use this format
console.setFormatter(formatter)
# add the handler to the root logger
logging.getLogger('').addHandler(console)


LANGUAGE_ALIASES = {
    'fantom': 'fan',
    'haxe': 'haXe',
    'sourcepawn': 'sp',
    'typescript': 'ts',
    'xbase': 'XBase',
}


class PygmentsParser:
    class ContentParser:
        def __init__(self, path, fileid, text, lexer):
            self.path = path
            self.fileid = fileid
            self.text = text
            self.lexer = lexer

        def parse(self):
            self.lines_index = self.build_lines_index(self.text)
            tokens = self.lexer.get_tokens_unprocessed(self.text)
            return self.parse_tokens(tokens)

        # builds index of beginning of line
        def build_lines_index(self, text):
            lines_index = []
            cur = 0
            while True:
                i = text.find('\n', cur)
                if i == -1:
                    break
                cur = i + 1
                lines_index.append(cur)
            lines_index.append(len(text))  # sentinel
            return lines_index

        def parse_tokens(self, tokens):
            result = []
            cur_line = 0
            #  from IPython.core.debugger import set_trace; set_trace()

            for index, tokentype, tag in tokens:
                if tokentype in Token.Name:
                    # we can assume index are delivered in ascending order
                    while self.lines_index[cur_line] <= index:
                        cur_line += 1
                    if re.fullmatch(r'\s*', tag):
                        continue  # remove newline and spaces
                    if len(tag) < 3:
                        continue
                    result.append((tag, cur_line, self.fileid))
            return result

    def __init__(self, langmap):
        self.langmap = langmap

    async def parse(self, args):
        #  print("parse file", path)
        path, (mtime, fileid) = args
        lexer = self.get_lexer_by_langmap(path)
        if lexer:
            text = self.read_file(path)
            if text:
                parser = self.ContentParser(path, fileid, text, lexer)
                result = parser.parse()
                return fileid, result

        return fileid, []

    def get_lexer_by_langmap(self, path):
        ext = Path(path).suffix
        if sys.platform == 'win32':
            lang = self.langmap.get(ext.lower(), None)
        else:
            lang = self.langmap.get(ext, None)
        if lang:
            name = lang.lower()
            if name in LANGUAGE_ALIASES:
                name = LANGUAGE_ALIASES[name]
            return pygments.lexers.get_lexer_by_name(name)
        else:
            return pygments.lexers.get_lexer_for_filename(path)

    def read_file(self, path):
        try:
            with open(path, 'r', encoding='latin1') as f:
                text = f.read()
                return text
        except Exception as e:
            print(e, file=sys.stderr)
            return None


class CtagsParser:
    TERMINATOR = '###terminator###\n'
    CLOSEFDS = sys.platform != 'win32'

    def __init__(self, ctags_command, output_format):
        self.command = ctags_command
        self.format = output_format

    def __enter__(self):
        import subprocess

        self.process = subprocess.Popen(
            [
                self.command,
                '-xu',
                '--filter',
                '--filter-terminator=' + self.TERMINATOR,
                '--format={}'.format(self.format),
            ],
            bufsize=-1,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            close_fds=self.CLOSEFDS,
            universal_newlines=True,
        )
        assert self.process.stdout is not None
        assert self.process.stdin is not None
        #  self.child_stdout = io.TextIOWrapper(self.process.stdout.buffer, encoding='latin1')
        self.child_stdout = self.process.stdout
        self.child_stdin = self.process.stdin
        logging.debug("launched ctags %s", self.command)

        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.process.terminate()
        self.process.wait()

    def parse(self, file_map):
        results = {}
        for path, (mtime, fileid) in file_map.items():
            print(path, file=self.child_stdin)
            self.child_stdin.flush()
            values = []
            results[fileid] = values
            pattern = re.compile(r'(\S+)\s+(\d+)\s+' + re.escape(path) + r'\s+(.*)$')
            #  pattern = re.compile(r'(\S+)\s+(\S+)\s+(\d+)\s+' + re.escape(path) + r'\s+(.*)$')
            while True:
                line = self.child_stdout.readline()
                if not line or line.startswith(self.TERMINATOR):
                    break
                match = pattern.search(line)
                if match:
                    (tag, lnum, image) = match.groups()
                    values.append((tag, fileid, int(lnum), image))
        return results


def find_files():
    return []


def build_path_db(cnx, files, args):
    #  from IPython.core.debugger import set_trace; set_trace()
    from time import time

    current = time()  # TODO

    if not args.incremental:
        #  cnx.execute(
        #      '''create table if not exists timeindexed (time);
        #      insert into timeindexed values (?) ''',
        #      (current,),
        #  )
        cnx.execute(
            '''create table if not exists path
                    (file text, mtime int, fileid int primary key)'''
        )
        file_map = {file: (int(os.path.getmtime(file)), id) for id, file in enumerate(files)}
        logging.info("%d files", len(file_map))
        cnx.executemany(
            'insert into path values (?,?,?)',
            ((file, mtime, id) for file, (mtime, id) in file_map.items()),
        )
        cnx.execute('create unique index if not exists file_index on path(file)')
        return file_map, []
    else:
        maxid = cnx.execute('select max(fileid) from path').fetchone()[0]
        maxid = 0 if maxid is None else maxid
        file_map = {
            value[0]: (value[1], value[2]) for value in cnx.execute('select * from path').fetchall()
        }

        deleted_files = {}
        for file, (mtime, id) in file_map.items():
            if not os.path.isfile(file):
                deleted_files[file] = file_map.pop(file)
        if deleted_files:
            cnx.executemany('delete from path where id=?', deleted_files)
            logging.info("%d deleted files", len(deleted_files))

        new_files = {
            file: (int(os.path.getmtime(file)), id)
            for id, file in enumerate(
                (file for file in files if file not in file_map), start=maxid + 1
            )
        }
        logging.info("%d new files", len(new_files))
        for file, (mtime, id) in file_map.items():
            new_mtime = int(os.path.getmtime(file))
            if new_mtime > mtime:
                new_files[file] = (new_mtime, id)
        logging.info("%d modified files", len(new_files))
        cnx.executemany(
            'replace into path values (?,?,?)',
            ((file, mtime, id) for file, (mtime, id) in new_files.items()),
        )
        return new_files, deleted_files


async def build_reference_db(cnx, langmap, new_file_map, deleted_file_map, args):
    pygments_parser = PygmentsParser(langmap)

    cnx.execute(
        '''create table if not exists ref
                (tag text, lineno int, fileid int)'''
    )
    if args.incremental:
        cnx.execute('drop index if exists ref_tag_index')
        cnx.executemany(
            'delete from ref where fileid=?',
            [(id,) for file, (mtime, id) in chain(new_file_map.items(), deleted_file_map.items())],
        )
    if len(new_file_map) > args.num_jobs:
        async with Pool(args.num_jobs) as pool:
            async for id, values in pool.map(pygments_parser.parse, new_file_map.items()):
                cnx.executemany("insert into ref values (?,?,?)", values)
                logging.debug("finished %d", id)
    else:
        for item in new_file_map.items():
            id, values = await pygments_parser.parse(item)
            cnx.executemany("insert into ref values (?,?,?)", values)
            logging.debug("finished %d", id)
    cnx.execute('create index if not exists ref_tag_index on ref(tag)')
    cnx.execute('create index if not exists ref_file_index on ref(fileid)')


async def build_definition_db(cnx, langmap, new_file_map, deleted_file_map, args):
    with CtagsParser('ctags', 1) as parser:
        cnx.execute(
            '''create table if not exists def
                    (tag text, fileid int, lineno int, image text)'''
        )
        if args.incremental:
            cnx.executemany(
                'delete from def where fileid=?',
                (
                    (id,)
                    for file, (mtime, id) in chain(new_file_map.items(), deleted_file_map.items())
                ),
            )
        results = parser.parse(new_file_map)
        for id, values in results.items():
            cnx.executemany("insert into def values (?,?,?,?)", values)
            logging.debug("finished %d", id)


@profileit
def tags_index(args):
    dbpath = Path(args.dbpath) / 'tags.db'

    if args.single_update:
        files = [args.single_update]
        args.incremental = True
    elif os.path.isfile('gtags.files'):
        with open('gtags.files', 'r') as f:
            files = f.read().splitlines()
    else:
        files = find_files()

    if args.incremental and not dbpath.is_file():
        args.incremental = False
    if not args.incremental and dbpath.is_file():
        dbpath.unlink()

    dbpath = dbpath.as_posix()
    with sqlite3.connect(dbpath) as cnx:
        cnx.execute("PRAGMA temp_store = MEMORY")
        cnx.execute('PRAGMA synchronous = 0')

        new_file_map, deleted_file_map = build_path_db(cnx, files, args)

        asyncio.run(
            build_definition_db(cnx, args.langmap, new_file_map, deleted_file_map, args)
        )
        logging.info('done index definition')
        asyncio.run(  #
            build_reference_db(cnx, args.langmap, new_file_map, deleted_file_map, args)
        )
        logging.info('done index reference')


@profileit
def tags_query(args):
    dbpath = Path(args.dbpath) / 'tags.db'

    results = []
    with sqlite3.connect(dbpath) as cnx:
        cnx.set_trace_callback(print)
        if args.query_ref:
            results = cnx.execute(
                '''select path.file,ref.lineno
                from path,ref
                where ref.tag=:pattern and path.fileid=ref.fileid''',
                {'pattern': args.pattern},
            ).fetchall()
        elif args.query_file:
            results = cnx.execute(
                '''select def.tag,def.lineno,def.image
                from path,def
                where path.file=:pattern and def.fileid = path.fileid''',
                {"pattern": args.pattern},
            ).fetchall()
        elif args.file_token:
            results = cnx.execute(
                '''select ref.tag,ref.lineno
                from path,ref
                where path.file=:pattern and ref.fileid = path.fileid''',
                {"pattern": args.pattern},
            ).fetchall()
        else:
            results = cnx.execute(
                '''select path.file,def.lineno,def.image
                from path,def
                where def.tag=:pattern and path.fileid=def.fileid''',
                {"pattern": args.pattern},
            ).fetchall()
    import pprint

    pprint.pprint(results)


def main():
    import argparse

    def parse_langmap(string):
        langmap = {}
        if not string:
            return langmap

        mappings = string.split(',')
        for mapping in mappings:
            lang, exts = mapping.split(':')
            if not lang[0].islower():  # skip lowercase, that is for builtin parser
                for ext in exts.split('.'):
                    if ext:
                        if sys.platform == 'win32':
                            langmap['.' + ext.lower()] = lang
                        else:
                            langmap['.' + ext] = lang
        return langmap

    root_arg = argparse.ArgumentParser()
    root_arg.add_argument('--dbpath', default='.')
    root_arg.add_argument('--langmap', type=parse_langmap, default={})
    root_arg.add_argument('-s', '--statistics', action='store_true')

    sub_parser = root_arg.add_subparsers(dest='command')

    index_parser = sub_parser.add_parser('index')
    index_parser.add_argument('-i', '--incremental', action='store_true')
    index_parser.add_argument('-u', '--single_update', type=str)
    index_parser.add_argument('-j', dest='num_jobs', type=int, default=8)

    query_parser = sub_parser.add_parser('query')
    query_parser.add_argument('-d', action='store_true', dest='query_def', help='find definition')
    query_parser.add_argument('-r', action='store_true', dest='query_ref', help='find reference')
    query_parser.add_argument(
        '-f', action='store_true', dest='query_file', help='find symbols in file'
    )
    query_parser.add_argument(
        '-a', action='store_true', dest='context', help='query base on location'
    )
    query_parser.add_argument('--file_token', action='store_true')
    query_parser.add_argument('pattern')

    args = root_arg.parse_args()

    #  from IPython.core.debugger import set_trace; set_trace()

    if args.statistics:
        profileit.enable_profile = True

    if args.command == 'index':
        tags_index(args)
    elif args.command == 'query':
        tags_query(args)
    else:
        root_arg.print_help()


if __name__ == "__main__":
    main()

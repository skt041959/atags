# atags
Yet another tagging system. This project aims to provide a modern remake of GNU Global.
It use universal-ctags as the definition parser and pygments as the reference parser.

## Features
- [x] Multi-language support, provided by pygements and universal-ctags
- [x] Multi-processing indexing.

## Install


## Usage
### Index
```
usage: atags.py index [-h] [-i] [--single_update SINGLE_UPDATE] [-j NUM_JOBS]

optional arguments:
  -h, --help            show this help message and exit
  -i, --incremental
  --single_update SINGLE_UPDATE
  -j NUM_JOBS
```

### Query
```
usage: atags.py query [-h] [-d] [-r] [-f] [-a] pattern

positional arguments:
  pattern

optional arguments:
  -h, --help  show this help message and exit
  -d          find definition
  -r          find reference
  -f          find symbols in file
  -a          query base on location
```

## Todos
- [ ] interface to integrated with fuzzy finders used by editors

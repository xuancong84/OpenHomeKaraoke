#!/bin/bash

cd "$(dirname $(readlink $0))"
PATH=$PWD/miniconda3/bin:$PATH python3 app.py -nv -V $*


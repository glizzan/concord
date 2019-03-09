#!/bin/bash

rm -r concord.egg-info/
rm -r dist/
python setup.py sdist

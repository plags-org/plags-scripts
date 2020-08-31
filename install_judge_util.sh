#!/bin/sh

for d in $*
do
    echo mkdir -p $d/.judge
    echo cp -v judge_util.py $d/.judge/
done

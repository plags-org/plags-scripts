#!/bin/sh

for d in $*
do
    mkdir -p $d/.judge
    cp -v judge_util.py $d/.judge/
done

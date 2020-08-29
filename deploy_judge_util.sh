#!/bin/sh

for d in exercises_bundled/*
do
    mkdir -p $d/.judge
    cp -v judge_util.py $d/.judge/
done

mkdir -p exercises_separate/.judge
cp -v judge_util.py exercises_separate/.judge/

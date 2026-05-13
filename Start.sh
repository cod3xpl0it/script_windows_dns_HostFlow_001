#!/bin/bash

nohup ~/miniforge3/bin/conda run -n base python HostFlow.py > log.txt 2>&1 &
disown

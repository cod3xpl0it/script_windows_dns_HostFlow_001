#!/bin/bash

echo "Downloading Miniforge..."
wget -O Miniforge3.sh https://github.com/conda-forge/miniforge/releases/latest/download/Miniforge3-Linux-x86_64.sh

echo "Installing Miniforge..."
bash Miniforge3.sh -b -p "$HOME/miniforge3"

echo "Configuration..."
source "$HOME/miniforge3/etc/profile.d/conda.sh"

conda init bash

echo "Loading shell..."
source ~/.bashrc

echo "Testing..."
conda --version

echo "Finished!!"
source ~/.bashrc
source ~/miniforge3/etc/profile.d/conda.sh
conda config --set auto_activate_base false

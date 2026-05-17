#!/usr/local/bin/bash

echo "Updating repositories..."
sudo pkg update

echo "Installing Python and pip..."
sudo pkg install -y python311 py311-pip bash py311-tkinter freerdp

echo "Configuring python symlink..."
sudo ln -sf /usr/local/bin/python3.11 /usr/local/bin/python

echo "Upgrading pip..."
python -m pip install --upgrade pip setuptools wheel

echo "Checking installation..."
python --version
pip --version

echo ""
echo "Installation completed successfully!"

#!/bin/bash

########
# Actual script
########

# If $1 is not provided, exit
if [ -z "$1" ]; then
        echo "You must provide a version number"
        exit -1
fi
# Check if the version is in semver format, if not exit
if ! [[ "$1" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
        echo "Version must be in semver format"
        exit -1
fi

echo "Creating version $1"
read -r -p "Do you want to create git tag? [y/N] " r
if [[ "$r" =~ ^([yY][eE][sS]|[yY])$ ]]; then
        git tag -a "v$1" -m "New version from script! $1"
        if [ $? -eq 0 ]; then
                echo "Tag created successfully"
        else
                echo "Error, git tag failed!"
                exit -2
        fi
        git push --tags
fi

echo "Setting up version for the package"
cp setup.py setup.py.bak
sed -i "s/#TAG_VERSION#/$1/" setup.py

echo "Making sure you have all you need"
pip install -U pip pep517 twine

echo "Creating virtualenv to run build"
virtualenv -p python3 .env
source .env/bin/activate
python3 -m pip install --upgrade build

echo "Installing requirement to push to repo the new version"
pip install twine
echo "Running build"
python3 -m build

echo "Pushing build - IF THIS FAILS YOU MUST CREATE ~/.pypirc < AND READ README!"
twine upload -r takelan dist/*
deactivate

echo "Setting up version for the package back to dev"
cp setup.py.bak setup.py

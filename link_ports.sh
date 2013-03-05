#!/bin/sh

# This script creates a macports directory structure of portfiles
# based on their category. The first argument is the directory that
# holds our entire collection of ports, the second argument is the
# target port directory. The directory structure will be populated
# with symbolic links to their original.
#
# This script needs to be run whenever new ports are added to/removed
# from our collection.
#
# If portfiles are otherwise updated, it is sufficient to run the
# portindex utility in the target directory.
#
# Bugs: this script can't handle multiple categories per Portfile

SOURCE="$1"
PORTS_DIR="$2"

usage()
{
    echo "Usage:"
    echo "  link_ports <source directory> <local ports repository>"
    echo
    echo "Note that the local ports repository will be deleted and recreated."
}

if [ -z "$SOURCE" -o -z "$PORTS_DIR" ]; then
    usage
    exit -1
fi

# Make source dir absolute; otherwise the symbolic links will point nowhere
if ! `echo "$SOURCE" | grep -q '^/'` ; then
    SOURCE=`pwd`/"$SOURCE"
fi

# Clean ports dir
if [ -d "$PORTS_DIR" ]; then
    rm -rf "$PORTS_DIR"
fi

mkdir -p $PORTS_DIR

for port in "$SOURCE"/* ; do
    if [ ! -f "$SOURCE/$port/Portfile" ]; then
        continue
    fi

    category=`awk '/^categories/ {print $2}'  "$SOURCE/$port/Portfile"`

    if [ "$?" != "0" ]; then
        echo "error"
        exit -1
    fi

    if [ ! -d "$PORTS_DIR/$category" ]; then
        mkdir "$PORTS_DIR/$category"
    fi

    ln -s "$SOURCE/$port" "$PORTS_DIR/$category/"
done

cd $PORTS_DIR
portindex

echo "Add this line to /opt/local/etc/macports/sources.conf:"
echo "file://$PORTS_DIR"



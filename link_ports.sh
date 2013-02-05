#!/bin/bash

SOURCE="$1"
PORTS_DIR="$2"

function usage()
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

# Clean ports dir
if [ -d "$PORTS_DIR" ]; then
    rm -rf "$PORTS_DIR"
fi

PORTS=`ls "$SOURCE"`

mkdir -p $PORTS_DIR

for port in $PORTS; do
    if [ ! -f "$SOURCE/$port/Portfile" ]; then
        continue
    fi

    category=`grep "^categories" "$SOURCE/$port/Portfile" | awk '{print $2}'`

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



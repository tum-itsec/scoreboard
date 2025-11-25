#!/bin/bash

# without "version pinning", so versions might mismatch:
# pip list | cut -f1 -d' '

# with version pinning, but seems to be missing some packages
pip list | sed 's/  */==/g' | tail -n+3

# by using pkg_resources - includes some low-level packages
# python3 -c $'import pkg_resources\nfor i in pkg_resources.working_set:\n\tprint(f"{i.key}=={i.version}")'

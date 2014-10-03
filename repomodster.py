#!/usr/bin/python

# oh hai!

# let's have some fun with repomd.xml's ...

import os
import re
import sys
import bz2
import time
import urllib2
import sqlite3

try:
    import xml.etree.ElementTree as et
except ImportError:  # if sys.version_info[0:2] == (2,4):
    import elementtree.ElementTree as et

def usage(status=0):
    print "usage: %s [EL] PACKAGE" % os.path.basename(__file__)
    sys.exit(status)

try:
    if len(sys.argv) == 3:
        epel = int(sys.argv[1])
        pkg_name = sys.argv[2]
    elif len(sys.argv) == 2:
        epel = 6
        pkg_name = sys.argv[1]
    else:
        raise
except:
    usage()

baseurl = 'http://dl.fedoraproject.org/pub/epel/%d/SRPMS' % epel
repomd  = baseurl + '/repodata/repomd.xml'

cachedir  = os.getenv('HOME') + "/.cache/repomodster"
cachets   = cachedir + "/primary.ts"
cachedb   = cachedir + "/primary.sqlite"

def get_repomd_xml():
    handle = urllib2.urlopen(repomd)
    xml = handle.read()
    # strip xmlns garbage to simplify extracting things...
    xml = re.sub(r'<repomd [^>]*>', '<repomd>', xml)
    xmltree = et.fromstring(xml)
    return xmltree

def is_pdb(x):
    return x.get('type') == 'primary_db'

def cache_is_recent():
    # if the cache is < 1h old, don't even bother to see if there's a newer one
    return (os.path.exists(cachets) and
            os.path.exists(cachedb) and
            os.stat(cachets).st_mtime + 3600 > time.time())

def do_cache_setup():
    tree = get_repomd_xml()
    datas = tree.findall('data')
    primary = filter(is_pdb, datas)[0]
    primary_href = primary.find('location').get('href')
    primary_url = baseurl + '/' + primary_href
    primary_ts = float(primary.find('timestamp').text)  # hey let's use this...

    if not os.path.exists(cachedir):
        os.makedirs(cachedir)
    if os.path.exists(cachets) and os.path.exists(cachedb):
        last_ts = float(open(cachets).read().strip())
    else:
        last_ts = 0
        print >> open(cachets, "w"), primary_ts

    if primary_ts > last_ts:
        primary_zip = urllib2.urlopen(primary_url).read()
        primary_dat = bz2.decompress(primary_zip)
        open(cachedb, "w").write(primary_dat)
    else:
        # touch ts file to mark as recent
        os.utime(cachets, None)

if not cache_is_recent():
    do_cache_setup()

db = sqlite3.connect(cachedb)
c  = db.cursor()
c.execute("select name, version, release, arch from packages where name = ?",
          [pkg_name])

for nvra in c:
    print '-'.join(nvra[:3]) + "." + nvra[3] + ".rpm"


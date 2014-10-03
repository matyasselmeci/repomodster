#!/usr/bin/python

# oh hai!

# let's have some fun with repomd.xml's ...

import os
import re
import sys
import bz2
import time
import getopt
import urllib2
import sqlite3

try:
    import xml.etree.ElementTree as et
except ImportError:  # if sys.version_info[0:2] == (2,4):
    import elementtree.ElementTree as et

def usage(status=0):
    script = os.path.basename(__file__)
    print "usage: %s [-ubs567] PACKAGE [...]" % script
    print "specify -u to print full download urls"
    print "specify -b to match binary packages (default=%s)" % what
    print "specify -s to print source package name too"
    print "specify -5,-6,-7 for EL release series (default=%d)" % epel
    print "each PACKAGE can be a full package name or contain '%' wildcards"
    sys.exit(status)

epel = 6
what = 'SRPMS'
printurl = False
printsrpm = False

ops,pkg_names = getopt.getopt(sys.argv[1:], 'ubs567')
for op,val in ops:
    if   op == '-u': printurl = True
    elif op == '-b': what = 'x86_64'
    elif op == '-s': printsrpm = True
    else           : epel = int(op[1:])

if not pkg_names:
    usage()

baseurl = 'http://dl.fedoraproject.org/pub/epel/%d/%s' % (epel, what)
repomd  = baseurl + '/repodata/repomd.xml'

cachedir  = os.getenv('HOME') + "/.cache/epeldb"
cachets   = cachedir + "/primary.epel%d.%s.ts" % (epel, what)
cachedb   = cachedir + "/primary.epel%d.%s.db" % (epel, what)

def msg(m=""):
    if sys.stderr.isatty():
        sys.stderr.write("\r%s\x1b[K" % m)

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
    # if the cache is < 1h old, don't bother to see if there's a newer one
    return (os.path.exists(cachets) and
            os.path.exists(cachedb) and
            os.stat(cachets).st_mtime + 3600 > time.time())

def do_cache_setup():
    msg("fetching latest repomd.xml...")
    tree = get_repomd_xml()
    msg()
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
        msg("fetching latest primary db...")
        primary_zip = urllib2.urlopen(primary_url).read()
        msg("decompressing...")
        primary_dat = bz2.decompress(primary_zip)
        msg("saving cache...")
        open(cachedb, "w").write(primary_dat)
        msg()
    else:
        # touch ts file to mark as recent
        os.utime(cachets, None)

if not cache_is_recent():
    do_cache_setup()

db = sqlite3.connect(cachedb)
c  = db.cursor()

def like(name):
    return "%s ?" % ("like" if "%" in name else "=")

if '%' in ''.join(pkg_names) or len(pkg_names) == 1:
    nameclause = ' or name '.join(map(like,pkg_names))
else:
    nameclause = "in (" + ','.join('?' for x in pkg_names) + ")"

select  = "select location_href, rpm_sourcerpm from packages"
where   = "where name " + nameclause
if printsrpm:
    orderby = "order by rpm_sourcerpm, name, version, release, arch"
else:
    orderby = "order by name, version, release, arch"
sql = ' '.join([select, where, orderby])

c.execute(sql, pkg_names)

for href,srpm in c:
    if printsrpm and what != 'SRPMS':
        srpm = srpm.rsplit('-',2)[0]
        print "[" + srpm + "]",
    if printurl:
        print baseurl + "/" + href
    else:
        print href.split('/')[-1]


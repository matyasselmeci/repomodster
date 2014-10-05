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
    print "usage: %s [-ubsSc567] PACKAGE [...]" % script
    print
    print "each PACKAGE can be a full package name or contain '%' wildcards"
    print
    print "Options:"
    print "  -u   print full download urls"
    print "  -b   match binary packages (default=%s)" % what
    print "  -s   print source package name too"
    print "  -S   match source package names for binary package list"
    print "  -c   always use cached primary db (don't attempt to update)"
    print "  -5,-6,-7   specify EL release series (default=%d)" % epel
    sys.exit(status)

epel = 6
what = 'SRPMS'
printurl = False
printspkg = False
matchspkg = False
autoupdate = True

ops,pkg_names = getopt.getopt(sys.argv[1:], 'ubsSc567')
for op,val in ops:
    if   op == '-u': printurl = True
    elif op == '-b': what = 'x86_64'
    elif op == '-s': printspkg = True
    elif op == '-S': matchspkg = True
    elif op == '-c': autoupdate = False
    else           : epel = int(op[1:])

# fer later...
osg_series  = '3.2'
osg_repo    = 'release'
osg_what    = 'source/SRPMS'
osg_baseurl = 'http://repo.grid.iu.edu/osg/%s/el%d/%s/%s' % (
                osg_series, epel, osg_repo, osg_what)

baseurl = 'http://dl.fedoraproject.org/pub/epel/%d/%s' % (epel, what)
repomd  = baseurl + '/repodata/repomd.xml'

cachedir  = os.getenv('HOME') + "/.cache/epeldb"
cachets   = cachedir + "/primary.epel%d.%s.ts" % (epel, what)
cachedb   = cachedir + "/primary.epel%d.%s.db" % (epel, what)

def msg(m=""):
    if sys.stderr.isatty():
        sys.stderr.write("\r%s\x1b[K" % m)

def fail(m="",status=1):
    print >>sys.stderr, m
    sys.exit(status)

def get_repomd_xml():
    handle = urllib2.urlopen(repomd)
    xml = handle.read()
    # strip xmlns garbage to simplify extracting things...
    xml = re.sub(r'<repomd [^>]*>', '<repomd>', xml)
    xmltree = et.fromstring(xml)
    return xmltree

def is_pdb(x):
    return x.get('type') == 'primary_db'

def cache_exists():
    return os.path.exists(cachets) and os.path.exists(cachedb)

def cache_is_recent():
    # if the cache is < 1h old, don't bother to see if there's a newer one
    return cache_exists() and os.stat(cachets).st_mtime + 3600 > time.time()

def update_cache():
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
    if cache_exists():
        last_ts = float(open(cachets).readline().strip())
    else:
        last_ts = 0

    if primary_ts > last_ts:
        msg("fetching latest primary db...")
        primary_zip = urllib2.urlopen(primary_url).read()
        msg("decompressing...")
        primary_dat = bz2.decompress(primary_zip)
        msg("saving cache...")
        open(cachedb, "w").write(primary_dat)
        print >> open(cachets, "w"), primary_ts
        msg()
    else:
        # touch ts file to mark as recent
        os.utime(cachets, None)

def do_cache_setup():
    if not autoupdate:
        if cache_exists():
            return
        else:
            fail("cache requested but does not exist...")
    if not cache_is_recent():
        try:
            update_cache()
        except urllib2.URLError:
            msg()
            if not cache_exists():
                fail("primary db cache does not exist and download failed...")

def getsql():
    match = 'spkg' if matchspkg else 'name'

    def like(name):
        return match + " %s ?" % ("like" if "%" in name else "=")

    if '%' in ''.join(pkg_names) or len(pkg_names) == 1:
        nameclause = ' or '.join(map(like,pkg_names))
    else:
        nameclause = match + " in (" + ','.join('?' for x in pkg_names) + ")"

    select  = "select location_href, vrstrip(rpm_sourcerpm) spkg from packages"
    where   = "where (%s) and arch not in ('i386','i686')" % nameclause 
    if printspkg:
        orderby = "order by rpm_sourcerpm, name, version, release, arch"
    else:
        orderby = "order by name, version, release, arch"
    return ' '.join([select, where, orderby])


def regexp(rx,s):
    return re.search(rx,s) is not None

def vrstrip(s):
    if s is not None:
        return s.rsplit('-',2)[0]

def main():
    if not pkg_names:
        usage()

    do_cache_setup()

    db = sqlite3.connect(cachedb)
    # db.create_function("regexp", 2, regexp)
    db.create_function("vrstrip", 1, vrstrip)
    c  = db.cursor()

    sql = getsql()
    c.execute(sql, pkg_names)

    for href,spkg in c:
        if printspkg and what == 'x86_64':
            print "[%s]" % spkg,
        if printurl:
            print baseurl + "/" + href
        else:
            print href.split('/')[-1]

if __name__ == '__main__':
    main()


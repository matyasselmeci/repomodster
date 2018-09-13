#!/usr/bin/python

# oh hai!

# let's have some fun with repomd.xml's ...

import os
import re
import rpm
import sys
import bz2
import time
import getopt
import urllib2
import sqlite3
import hashlib

try:
    import xml.etree.ElementTree as et
except ImportError:  # if sys.version_info[0:2] == (2,4):
    import elementtree.ElementTree as et

def usage(status=0):
    print "usage: %s [OPTIONS] PACKAGE [...]" % script
    print
    print "each PACKAGE can be a full package name or contain '%' wildcards"
    print
    print "Options:"
    print "  -u   print full download urls"
    print "  -b   match binary packages (default=%s)" % what
    print "  -s   print source package name too"
    print "  -S   match source package names for binary package list"
    print "  -c   always use cached primary db (don't attempt to update)"
#   print "  -m   only list 1 rpm (max NVR) per package name, per repo"
    print "  -a   show all versions of each package; default max VR per repo"
    print "  -d   download matching rpm(s)"
    print "  -O   use OSG repos  (defaults: -o %s -r %s)" % (osgser, osgrepo)
    print "  -C   use CentOS repos"
    print "  -J   use JPackage repos"
    print "  -D%d  use cloudera (cdh%d) repos" % (cloudera_cdh, cloudera_cdh)
    print "  -L   Scientific Linux (SL) repos"
    print "  -F   Scientific Linux Fermi (SLF) repos"
    print "  -E   use EPEL repos"
    print "  -G   use generic rpm repo: set [S]RPMS_BASEURL as needed"
    print "  -f%d use fedora-%d repos" % (fedora, fedora)
    print "  -5,-6,-7   specify EL release series (default=%d)" % default_epel
    print
    print "  -o series  use osg series (3.3, 3.4, upcoming)"
    print "  -r repo    use osg repo (development, testing, release)"
    print
    print "  -H repo    use UW HTCondor repo (stable, development)"
    print
    sys.exit(status)

def get_default_reposet():
    m = re.search(r'^([a-z]\w*)-srpms$', script)
    return m.group(1) if m else 'epel'

script = os.path.basename(__file__)
cachedir  = os.getenv('HOME') + "/.cache/epeldb"
default_epel = 6
fedora = 26
epels = []
what = 'SRPMS'
printurl = False
printspkg = False
matchspkg = False
autoupdate = True
downloadrpms = False
# maxnvr = False
maxnvr = True
stale_cache_age = 3600   # seconds
reposet = get_default_reposet()
osgser = '3.4'
osgrepo = 'release'
condorrepo = 'development'
cloudera_cdh = 5

try:
    ops,pkg_names = getopt.getopt(sys.argv[1:], 'ubsScadOCEJLFG567r:o:f:D:H:')
except getopt.GetoptError:
    usage()

for op,val in ops:
    if   op == '-u': printurl = True
    elif op == '-b': what = 'x86_64'
    elif op == '-s': printspkg = True
    elif op == '-S': matchspkg = True
    elif op == '-c': autoupdate = False
#   elif op == '-m': maxnvr = True
    elif op == '-a': maxnvr = False
    elif op == '-d': downloadrpms = True
    elif op == '-O': reposet = 'osg'
    elif op == '-C': reposet = 'centos'
    elif op == '-E': reposet = 'epel'
    elif op == '-J': reposet = 'jpackage'
    elif op == '-L': reposet = 'scientific'
    elif op == '-F': reposet = 'slf'
    elif op == '-D': reposet = 'cloudera'; cloudera_cdh = int(val)
    elif op == '-r': osgrepo = val
    elif op == '-H': reposet = 'htcondor'; condorrepo = val
    elif op == '-o': osgser = val
    elif op == '-f': reposet = 'fedora'; fedora = int(val)
    else           : epels += [int(op[1:])]

if len(epels) == 0:
    epels += [default_epel]

class Container:
    pass

def getfn(name):
    return getattr(sys.modules[__name__], name)


# reposet infos...

def osg_baseurl_ex(el, what):
    whatpath = 'source/SRPMS' if what == 'SRPMS' else what
    basefmt  = 'http://repo.opensciencegrid.org/osg/%s/el%d/%s/%s'
    return basefmt % (osgser, el, osgrepo, whatpath)

def osg_cachename_ex(el, what):
    if re.search(r'\W', osgrepo):
        fail("[%s] is not a healthy repo name..." % osgrepo)
    return "osg-%s-el%d-%s.%s" % (osgser, el, osgrepo, what)


def centos_baseurl_ex(el, what):
    if what == 'SRPMS':
        whatpath = 'Source'
        basefmt = 'http://vault.centos.org/centos/%d/os/%s'
    else:
        # centos mirrors don't seem to have Source pkgs
        whatpath = what
        basefmt = 'http://mirror.batlab.org/pub/linux/centos/%d/os/%s'
    return basefmt % (el, whatpath)

def centos_cachename_ex(el, what):
    return "centos%d.%s" % (el, what)


def cloudera_baseurl_ex(el, what):
    basefmt = 'http://archive.cloudera.com/cdh%d/redhat/%d/x86_64/cdh/%d'
    return basefmt % (cloudera_cdh, el, cloudera_cdh)

def cloudera_cachename_ex(el, what):
    return "cloudera-cdh%d-el%d.%s" % (cloudera_cdh, el, what)


def htcondor_baseurl_ex(el, what):
    basefmt = 'http://research.cs.wisc.edu/htcondor/yum/%s/rhel%d'
    return basefmt % (condorrepo, el)

def htcondor_cachename_ex(el, what):
    return "htcondor-%s-rhel%d.%s" % (condorrepo, el, what)


def scientific_baseurl_ex(el, what):
    base = 'http://ftp.scientificlinux.org/linux/scientific'
    if el == 5:
        if what == 'SRPMS':
            basefmt = base + '/%dx/%s'
        else:
            basefmt = base + '/%dx/%s/SL'
    else:
        if what == 'SRPMS':
            basefmt = base + '/%d/%s'
        else:
            basefmt = base + '/%d/%s/os'
    return basefmt % (el, what)

def scientific_cachename_ex(el, what):
    return "scientific%d.%s" % (el, what)


def slf_baseurl_ex(el, what):
    basefmt = 'http://ftp.scientificlinux.org/linux/fermi/slf%d/%s'
    if what != 'SRPMS':
        if el == 5:
            basefmt += '/SL'
        else:
            basefmt += '/os'
    return basefmt % (el, what)

def slf_cachename_ex(el, what):
    return "slf%d.%s" % (el, what)


def fedora_baseurl_ex(el, what):
    basefmt = ('http://download.fedoraproject.org/pub/fedora/linux/releases/'
              '%d/Everything')
    if what == 'SRPMS':
        if fedora >= 24:
            basefmt += '/source/tree'
        else:
            basefmt += '/source/SRPMS'
        return basefmt % fedora
    else:
        basefmt += '/%s/os'
        return basefmt % (fedora, what)

def fedora_cachename_ex(el, what):
    return "fedora%d.%s" % (fedora, what)


def jpackage_baseurl_ex(el, what):
    #whatpath = 'SRPMS.free' if what == 'SRPMS' else 'RPMS'
    #basefmt = 'http://mirror.batlab.org/pub/jpackage/%d/%s'
    whatpath = 'free'
    basefmt = 'http://mirrors.dotsrc.org/jpackage/%d.0/generic/%s'
    return basefmt % (el, whatpath)

def jpackage_cachename_ex(el, what):
    #whatpath = what if what == 'SRPMS' else 'RPMS'
    whatpath = 'free'
    return "jpackage%d.%s" % (el, whatpath)


def epel_baseurl_ex(el, what):
    basefmt = 'http://mirror.batlab.org/pub/linux/epel/%d/%s'
    #basefmt = 'http://ftp.osuosl.org/pub/fedora-epel/%d/%s'
    #basefmt = 'http://dl.fedoraproject.org/pub/epel/%d/%s'
    return basefmt % (el, what)

def epel_cachename_ex(el, what):
    return "epel%d.%s" % (el, what)


def generic_baseurl_ex(el, what):
    envname = '%s_BASEURL' % (what if what == 'SRPMS' else 'RPMS')
    if envname not in os.environ:
        print >>sys.stderr, "Please set %s" % envname
        sys.exit(1)
    return os.environ[envname].rstrip('/')

def generic_cachename_ex(el, what):
    cachename = hashlib.md5(generic_baseurl_ex(el, what)).hexdigest()
    return "generic-%s.%s" % (cachename, what)


def get_reposet_info(el, what):
    info = Container()
    baseurl_ex    = getfn(reposet + "_baseurl_ex")
    cachename_ex  = getfn(reposet + "_cachename_ex")

    info.baseurl  = baseurl_ex(el, what)
    info.repomd   = info.baseurl + '/repodata/repomd.xml'
    cachename     = cachename_ex(el, what)
    info.cachets  = cachedir + "/primary.%s.ts" % cachename
    info.cachedb  = cachedir + "/primary.%s.db" % cachename
    info.cachebu  = cachedir + "/primary.%s.baseurl" % cachename
    return info


def msg(m=""):
    if sys.stderr.isatty():
        sys.stderr.write("\r%s\x1b[K" % m)

def fail(m="",status=1):
    print >>sys.stderr, m
    sys.exit(status)

def get_repomd_xml(info):
    handle = urllib2.urlopen(info.repomd)
    xml = handle.read()
    # strip xmlns garbage to simplify extracting things...
    xml = re.sub(r'<repomd [^>]*>', '<repomd>', xml)
    xmltree = et.fromstring(xml)
    return xmltree

def is_pdb(x):
    return x.get('type') == 'primary_db'

def is_primary(x):
    return x.get('type') == 'primary'

def cache_exists(info):
    return os.path.exists(info.cachets) and os.path.exists(info.cachedb)

def cache_is_recent(info):
    # if the cache is < 1h old, don't bother to see if there's a newer one
    return cache_exists(info) and \
           os.stat(info.cachets).st_mtime + stale_cache_age > time.time()

def xyz_decompress(dat, method):
    from subprocess import Popen, PIPE
    return Popen([method, '-d'], stdin=PIPE, stdout=PIPE).communicate(dat)[0]

def datafilter(cmdline):
    if cmdline is None:
        return (lambda x:x)
    from subprocess import Popen, PIPE
    return (lambda x:Popen(cmdline, stdin=PIPE, stdout=PIPE).communicate(x)[0])

def get_lmd(url):
    req = urllib2.Request(url)
    req.get_method = lambda : 'HEAD'
    resp = urllib2.urlopen(req)
    lmd = resp.headers.getdate('Last-Modified')
    return time.mktime(lmd)

def snoop_primary_db(info):
    # hack to deal with unpublished primary.sqlite.gz2 for centos5
    html = slurp_url(info.baseurl + '/repodata')
    m = re.search(r'href="(primary.sqlite.(?:bz2|gz|xz))"', html)
    if m:
        return "%s/repodata/%s" % (info.baseurl, m.group(1))
    else:
        raise RuntimeError("Can't find primary_db under %s/repodata" %
                           info.baseurl)

def pkg_et2row(pkg):
    name = pkg.find('name').text
    arch = pkg.find('arch').text
    vvv  = pkg.find('version')
    epoch   = vvv.get('epoch')
    version = vvv.get('ver')
    release = vvv.get('rel')
    rpm_sourcerpm = pkg.find('format').find('rpm_sourcerpm').text
    location_href = pkg.find('location').get('href')
    return name, arch, version, epoch, release, rpm_sourcerpm, location_href

def convert_primary_xml2db(xml, cachedb):
    if os.path.exists(cachedb):
        os.unlink(cachedb)
    db = sqlite3.connect(cachedb)
    c  = db.cursor()
    c.execute("create table packages "
              "(name, arch, version, epoch, release, "
              "rpm_sourcerpm, location_href);");
    c.execute("CREATE INDEX packagename ON packages (name);");

    xml = re.sub(r'<metadata xmlns="[^"]+"', '<metadata', xml)
    xml = re.sub(r'<metadata xmlns:rpm="[^"]+"', '<metadata', xml)
    xml = re.sub(r'<(/?)rpm:', r'<\1rpm_', xml)
    xmltree = et.fromstring(xml)
    rows = map(pkg_et2row, xmltree.findall('package'))
    c.executemany("insert into packages values (?,?,?,?,?,?,?);", rows)
    db.commit()
    db.close()

def update_cache(info):
    msg("fetching latest repomd.xml...")
    tree = get_repomd_xml(info)
    msg()
    datas = tree.findall('data')
    try:
        primary = filter(is_pdb, datas)[0]
        primary_href = primary.find('location').get('href')
        primary_url = info.baseurl + '/' + primary_href
        primary_ts = float(primary.find('timestamp').text)
    except IndexError:
        try:
            primary_url = snoop_primary_db(info)
            primary_ts = get_lmd(primary_url)
        except RuntimeError:
            primary = filter(is_primary, datas)[0]
            primary_href = primary.find('location').get('href')
            primary_url = info.baseurl + '/' + primary_href
            primary_ts = float(primary.find('timestamp').text)

    if not os.path.exists(cachedir):
        os.makedirs(cachedir)
    if cache_exists(info):
        last_ts = float(open(info.cachets).readline().strip())
    else:
        last_ts = 0

    if primary_ts > last_ts:
        msg("fetching latest primary db...")
        primary_zip = slurp_url(primary_url)
        msg("decompressing...")

#       ext = re.sub(r'^.*\.', '', primary_url)
#       primary_db = { 'xz'     : datafilter(['xz','-d'])
#                    , 'gz'     : datafilter(['gzip','-d'])
#                    , 'bz2'    : bz2.decompress
#                    , 'sqlite' : datafilter(None)
#                    }[ext](primary_zip)

        if primary_url.endswith('.xml.gz'):
            primary_xml = xyz_decompress(primary_zip, 'gzip')
            msg("converting primary.xml to sqlite db...")
            convert_primary_xml2db(primary_xml, info.cachedb)
        else:
            if primary_url.endswith('.xz'):
                primary_db = xyz_decompress(primary_zip, 'xz')
            elif primary_url.endswith('.gz'):
                primary_db = xyz_decompress(primary_zip, 'gzip')
            elif primary_url.endswith('.bz2'):
                primary_db = bz2.decompress(primary_zip)
            else:
                fail("what kind of compression is '%s' using?" % primary_url)
            msg("saving cache...")
            open(info.cachedb, "w").write(primary_db)
        print >>open(info.cachets, "w"), primary_ts
        print >>open(info.cachebu, "w"), info.baseurl
        msg()
    else:
        # touch ts file to mark as recent
        os.utime(info.cachets, None)

def do_cache_setup(info):
    if not autoupdate:
        if cache_exists(info):
            return
        else:
            fail("cache requested but does not exist...")
    if not cache_is_recent(info):
        try:
            update_cache(info)
        except urllib2.URLError:
            msg()
            if not cache_exists(info):
                fail("primary db cache does not exist and download failed..."
                     "\n(baseurl = %s)" % info.baseurl)

def slurp_url(url):
    return urllib2.urlopen(url).read()

def download(url):
    dest = url.split('/')[-1]
    handle = urllib2.urlopen(url)
    msg("downloading %s..." % dest)
    open(dest, "w").write(handle.read())
    msg()

def getsql(what):
    match = 'spkg' if matchspkg else 'name'

    def like(name):
        return match + " %s ?" % ("like" if "%" in name else "=")

    if '%' in ''.join(pkg_names) or len(pkg_names) == 1:
        nameclause = ' or '.join(map(like,pkg_names))
    else:
        nameclause = match + " in (" + ','.join('?' for x in pkg_names) + ")"

    if what == 'SRPMS':
        archclause = "arch = 'src'"
    else:
        archclause = "arch not in ('i386','i686','src')"

    select = ("select location_href, vrstrip(rpm_sourcerpm) spkg,"
                    " name, epoch, version, release from packages")
    where  = "where (%s) and (%s)" % (nameclause, archclause)
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

def rpmvercmp(a,b):
    return rpm.labelCompare(a,b)

def _maxrpmver(a,b):
    return a if rpmvercmp(a,b) > 0 else b

def maxrpmver(*seq):
    if len(seq) == 1 and hasattr(seq[0],"__iter__"):
        seq = seq[0]
    return reduce(_maxrpmver, seq, (None,None,None))

def main():
    if not pkg_names:
        usage()

    n = 0
    for info in ( get_reposet_info(epel, what) for epel in epels ):
        n += run_for_repo(info)

    return n == 0

def maxnvr_stunt(c):
    nnn = []
    nd  = {}
    for href,spkg,n,e,v,r in c:
        if n not in nd:
            nd[n] = {}
            nnn.append(n)
        nd[n][e,v,r] = [href, spkg]

    for n in nnn:
        evrs = ([maxrpmver(nd[n].keys())] if maxnvr
                else sorted(nd[n], cmp=rpmvercmp))
        for evr in evrs:
            yield nd[n][evr]

def run_for_repo(info):
    do_cache_setup(info)

    db = sqlite3.connect(info.cachedb)
    # db.create_function("regexp", 2, regexp)
    db.create_function("vrstrip", 1, vrstrip)
    c  = db.cursor()

    sql = getsql(what)
    c.execute(sql, pkg_names)

    n = 0
    for href,spkg in maxnvr_stunt(c):
        n += 1
        if printspkg and what == 'x86_64':
            print "[%s]" % spkg,
        if printurl:
            print info.baseurl + "/" + href
        else:
            print href.split('/')[-1]
        if downloadrpms:
            download(info.baseurl + "/" + href)

    return n

if __name__ == '__main__':
    sys.exit(main())


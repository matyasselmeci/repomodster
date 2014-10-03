#!/usr/bin/python

# oh hai!

# let's have some fun with repomd.xml's ...

import urllib2
import re
try:
    import xml.etree.ElementTree as et
except ImportError:  # if sys.version_info[0:2] == (2,4):
    import elementtree.ElementTree as et

baseurl = 'http://dl.fedoraproject.org/pub/epel/7/SRPMS'
repomd  = baseurl + '/repodata/repomd.xml'

def get_repomd_xml():
    handle = urllib2.urlopen(repomd)
    xml = handle.read()
    # strip xmlns garbage to simplify extracting things...
    xml = re.sub(r'<repomd [^>]*>', '<repomd>', xml)
    xmltree = et.fromstring(xml)
    return xmltree

def is_pdb(x):
    return x.get('type') == 'primary_db'

tree = get_repomd_xml()
datas = tree.findall('data')
primary = filter(is_pdb, datas)[0]
primary_href = primary.find('location').get('href')
primary_url = baseurl + '/' + primary_href
primary_ts = primary.find('timestamp').text  # hey let's use this...


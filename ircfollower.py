#!/usr/bin/env python
import binascii
import hashlib
import hmac
import httplib
import random
import sys
import time
import urllib
import urlparse
import simplejson as json

CONSUMER_KEY=""
CONSUMER_SECRET=""
ACCESS_TOKEN=""
ACCESS_SECRET=""

API_TARGET="api.twitter.com"
STATUS_PATH="/1.1/statuses/user_timeline.json"

def escape(s):
    return urllib.quote(s, safe='~')

def hmac_sign(uri, headers):
    key = escape(CONSUMER_SECRET) + '&' + escape(ACCESS_SECRET)
    raw = escape('GET') + '&' + escape(uri) + '&' + \
        escape(urllib.urlencode(sorted(headers.items()), True))
    hashed = hmac.new(key, raw, hashlib.sha1)
    return binascii.b2a_base64(hashed.digest())[:-1]

def make_auth_header(uri, headers):
    stringy_params = ((k, escape(str(v))) for k, v in sorted(headers.items()) if k.startswith('oauth_'))
    header_params = ('%s="%s"' % (k, v) for k, v in stringy_params)
    params_header = ', '.join(header_params)

    return "OAuth " + params_header

def make_oauth_headers(uri, params):
    headers = {
        'oauth_consumer_key' : CONSUMER_KEY,
        'oauth_timestamp' :  str(int(time.time())),
        'oauth_nonce' : str(random.randint(0, 100000000)),
        'oauth_version' : '1.0',
        'oauth_token' : ACCESS_TOKEN,
        'oauth_signature_method' : 'HMAC-SHA1',
    }
    headers.update(params)
    signature = hmac_sign(uri, headers)
    headers['oauth_signature'] = signature
    return { 'Authorization' : make_auth_header(uri, headers) }

def get_latest_tweet(user):
    conn = httplib.HTTPSConnection(API_TARGET)
    uri = API_TARGET + STATUS_PATH + "?count=1&screen_name=%s" % user
    parsed_uri = urlparse.urlparse(uri)
    params = urlparse.parse_qs(parsed_uri.query)
    headers = make_oauth_headers("https://" + API_TARGET + STATUS_PATH, params)
    conn.request("GET", uri, headers=headers)
    resp_json =  conn.getresponse().read()
    resp = json.loads(resp_json)
    old_id = "0"
    tmpfile = None
    try:
        tmpfile =  open("/tmp/cscbot_twitter_%s" % user, "r")
        old_id = tmpfile.read()
        tmpfile.close()
    except:
        if tmpfile != None:
            tmpfile.close()
        pass
    if str(resp[0]['id']) != old_id:
        print "< " + user + "> " + resp[0]['text'].encode('ascii', 'ignore')
    try:
        tmpfile = open("/tmp/cscbot_twitter_%s" % user, "w")
        tmpfile.write(str(resp[0]['id']))
        tmpfile.close()
    except:
        if tmpfile != None:
            tmpfile.close()
        pass

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print "Supply twitter handle as argument"
        sys.exit(1)
    get_latest_tweet(sys.argv[1])

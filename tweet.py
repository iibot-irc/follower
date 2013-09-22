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
from os.path import expanduser

from config import config

HANDLE = config('twitter.handle')

CONSUMER_KEY    = config('twitter.consumerKey')
CONSUMER_SECRET = config('twitter.consumerSecret')
ACCESS_TOKEN    = config('twitter.accessToken')
ACCESS_SECRET   = config('twitter.accessSecret')

API_TARGET = 'api.twitter.com'

STATUS_PATH     = '/1.1/statuses/user_timeline.json'
UPDATE_PATH     = '/1.1/statuses/update.json'
DESTROY_PATH    = '/1.1/statuses/destroy/'
FOLLOWERS_PATH  = '/1.1/followers/ids.json'
LOOKUP_PATH     = '/1.1/users/lookup.json'
MENTIONS_PATH   = '/1.1/statuses/mentions_timeline.json'
RETWEETS_PATH   = '/1.1/statuses/retweets_of_me.json'
RETWEETERS_PATH = '/1.1/statuses/retweeters/ids.json'

STATE_DIR = expanduser('~') + '/state/'

MENTIONS_FILE   = STATE_DIR + 'twitter_mentions'
RETWEETS_FILE   = STATE_DIR + 'twitter_retweets'
FOLLOWERS_FILE  = STATE_DIR + 'twitter_followers'
TWEET_FILE_BASE = STATE_DIR + 'twitter_tweets_'

# Input: Array a, Array b
# Output: all x in a such that x is not in b
def diff(a, b):
    b = set(b)
    return [aa for aa in a if aa not in b]

#
# OAuth/API request stuff
#

def escape(s):
    return urllib.quote(s, safe='~')

def urlencode_space(d):
    params = [(escape(str(k)), escape(str(v))) for k, v in d]
    return '&'.join(['%s=%s' % (k, v) for k, v in params])

def hmac_sign(verb, uri, oauth_params):
    key = escape(CONSUMER_SECRET) + '&' + escape(ACCESS_SECRET)
    raw = escape(verb) + '&' + escape(uri) + '&' + escape(urlencode_space(sorted(oauth_params.items())))
    hashed = hmac.new(key, raw, hashlib.sha1)
    return binascii.b2a_base64(hashed.digest())[:-1]

def make_auth_header(uri, oauth_params):
    stringy_params = ((k, escape(str(v))) for k, v in sorted(oauth_params.items()) if k.startswith('oauth_'))
    header_params = ('%s="%s"' % (k, v) for k, v in stringy_params)
    params_header = ', '.join(header_params)
    return "OAuth " + params_header

def make_oauth_headers(verb, uri, params, body):
    uri = 'https://' + uri
    if body == None:
        body = {}
    oauth_params = {
        'oauth_consumer_key' : CONSUMER_KEY,
        'oauth_timestamp' :  str(int(time.time())),
        'oauth_nonce' : str(random.randint(0, 100000000)),
        'oauth_version' : '1.0',
        'oauth_token' : ACCESS_TOKEN,
        'oauth_signature_method' : 'HMAC-SHA1',
    }
    oauth_params.update(params)
    oauth_params.update(body)
    signature = hmac_sign(verb, uri, oauth_params)
    oauth_params['oauth_signature'] = signature
    return { 'Authorization' : make_auth_header(uri, oauth_params) }

def api_call(verb, route, params = {}, headers = {}, body = None):
    uri = API_TARGET + route
    conn = httplib.HTTPSConnection(API_TARGET)
    headers.update(make_oauth_headers(verb, uri, params, body))
    if body != None:
        body = urlencode_space(body.items())
    params_str = '?' + urlencode_space(params.items())
    conn.request(verb, uri + params_str, body, headers)
    return json.loads(conn.getresponse().read())

#
# File IO helpers
#

def read_file(path):
    f = open(path, "r")
    contents = f.read()
    f.close()
    return contents

def try_read_file(path, def_contents):
    contents = def_contents
    f = None
    try:
        contents = read_file(path)
    except:
        if f != None:
            f.close()
        pass
    return contents

def write_file(path, contents):
    f = open(path, 'w')
    f.write(contents)
    f.close()

#
# Twitter methods
#

def delete_tweet(tweet_id):
    resp = api_call(
        verb   = 'POST',
        route  = DESTROY_PATH + tweet_id + '.json')
    if 'text' in resp:
        print 'Tweet successfully deleted: ' + resp['text']
    else:
        print 'Could not delete tweet'
        sys.exit(1)

def send_tweet(msg, irc_user):
    #if len(msg) > 140:
    #    print irc_user + ': Your message was too long. Please shorten.'
    #    sys.exit(1)
    resp = api_call(
        verb    = 'POST',
        route   = UPDATE_PATH,
        body    = { 'status': msg },
        headers = { 'Content-Type': 'application/x-www-form-urlencoded' })
    if 'id_str' in resp:
        print '\0037::\003 https://m.twitter.com/' + HANDLE + '/status/' + str(resp['id_str'])
    else:
        print irc_user + ': bonk bonk glorp: ' + str(resp)
        sys.exit(1)

def get_latest_tweet(screen_name, chan, filtered=False):
    TWEET_FILE = TWEET_FILE_BASE + chan + "_" + screen_name
    resp = api_call(
        verb   = 'GET',
        route  = STATUS_PATH,
        params = {
            'include_rts': not filtered,
            'exclude_replies': filtered,
            'count': '5',
            'screen_name': screen_name
        })

    old_id = try_read_file(TWEET_FILE, '0')

    out = []
    for r in resp:
        if str(r['id']) != old_id:
            out += ["\0036@@\003 " + screen_name + ": " + r['text'].encode('ascii', 'ignore')]
        else:
            break

    out.reverse()
    print '\n'.join(out)

    write_file(TWEET_FILE, str(resp[0]['id']))

# Input: Array of user_id
# Output: Array of screen_name
def fetch_names(ids):
    ids_str = str(ids)[1:-1].replace(' ', '')
    resp = api_call(
        verb   = 'POST',
        route  = LOOKUP_PATH,
        params = { 'user_id': ids_str })
    for user in resp:
        ids[ids.index(int(user['id_str']))] = user['name'] + ' (@' + user['screen_name'] + ')'
    return ids

def update_followers():
    resp = api_call(
        verb  = 'GET',
        route = FOLLOWERS_PATH)
    if 'ids' in resp:
        followers = resp['ids']
    else:
        print 'hurrrrr: ' + str(resp)
        sys.exit(1)

    old_followers = json.loads(try_read_file(FOLLOWERS_FILE, '[]'))

    news = diff(followers, old_followers)
    if news != []:
        print '\0033++\003 Now followed by: ' + str(fetch_names(news))[1:-1].replace("'", '')

    gones = diff(old_followers, followers)
    if gones != []:
        print '\0034--\003 No longer followed by: ' + str(fetch_names(gones))[1:-1].replace("'", '')

    write_file(FOLLOWERS_FILE, str(followers))

def get_retweets():
    data = json.loads(try_read_file(RETWEETS_FILE, '{}'))
    resp = api_call(
        verb   = 'GET',
        route  = RETWEETS_PATH,
        params = { 'trim_user': 'true', 'include_entities': 'false', 'count': '3' })
    for tweet in resp:
        old_uids = []
        if tweet['id_str'] in data:
            old_uids = data[tweet['id_str']]
        uids = api_call(
            verb   = 'GET',
            route  = RETWEETERS_PATH,
            params = { 'id': tweet['id_str'] })['ids']
        data[tweet['id_str']] = uids
        news = diff(uids, old_uids)
        if news == []:
            continue
        news = fetch_names(news)
        for screen_name in news:
            text = unicode(tweet['text'], 'utf-8')
            print '\0037RT\003 ' + screen_name + ': ' + text
    write_file(RETWEETS_FILE, json.dumps(data, sort_keys=True, indent=4, separators=(',', ':')))

def get_mentions():
    # TODO: filter out mentions from people we follow?
    old_id = int(try_read_file(MENTIONS_FILE, '1'))
    resp = api_call(
        verb   = 'GET',
        route  = MENTIONS_PATH,
        params = { 'since_id': old_id, 'include_rts': '1', 'contributor_details': 'true' })

    for mention in resp:
        if mention['user']['screen_name'] == HANDLE:
            continue
        old_id = max(old_id, int(mention['id']))
        print '\0032**\003 @' + mention['user']['screen_name'].encode('utf-8', 'ignore') + ': ' + mention['text'].encode('utf-8', 'ignore')

    write_file(MENTIONS_FILE, str(old_id))

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print 'Supply command and at least one argument.'
        sys.exit(1)

    if sys.argv[1] == 'get_tweets':
        filtered = len(sys.argv) == 5 and sys.argv[4] == 'filter'
        get_latest_tweet(sys.argv[2], sys.argv[3], filtered)
    elif sys.argv[1] == 'tweet':
        send_tweet(sys.argv[2], sys.argv[3])
    elif sys.argv[1] == 'delete_tweet':
        delete_tweet(sys.argv[2])
    elif sys.argv[1] == 'update_followers':
        update_followers()
    elif sys.argv[1] == 'get_mentions':
        get_mentions()
    elif sys.argv[1] == 'get_retweets':
        get_retweets()
    else:
        print 'Unknown command'

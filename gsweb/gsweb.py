# -*- encoding: utf-8 -*-
#
# gsweb.py - en del av Gatusmart, http://gatusmart.se
# Tillgängliggjord under Apache Software License 2.0, se LICENSE.txt
#

from flask import Flask, g, request, render_template
from flask.ext.cors import CORS
from flask.json import dumps, jsonify
from pymongo import MongoClient
from datetime import datetime

app = Flask(__name__)
cors = CORS(app)


def connect_to_database():
    client = MongoClient()
    return client


def get_db():
    db_client = getattr(g, '_db_client', None)
    if db_client is None:
        db_client = g._db_client = connect_to_database()
    return db_client.streetsmart


@app.route('/')
def index():
    return render_template('index.html')


def has_no(qs):
    for q in qs:
        if q.isdigit():
            return True
    else:
        return False


def find_places(q, p):
    db = get_db()
    ps = db.places.find({'searchable_name': {'$regex': '^' + q }, 'location': { '$near': p }})
    rs = []
    for p in ps:
        r = {
            'primary': u'%s' % p['place_name'],
            'secondary': '',
            'location': p['location'],
        }
        rs.append(r)
    return rs


def find_streets(q, p):
    db = get_db()
    if has_no(q):
        ps = db.streets.find({'searchable_name': {'$regex': '^' + q }, 'location': { '$near': { 'type': 'Point', 'coordinates': p }}}).limit(100)
    else:
        ps = db.streets.find({'searchable_name': {'$regex': '^' + q }, 'house_number': '', 'location': { '$near': { 'type': 'Point', 'coordinates': p }} }).limit(100)
    rs = []
    dupes = set()
    for p in ps:
        if p['house_number']:
            r = {
                'primary': u'%s %s' % (p['street_name'], p['house_number']),
                'secondary': p['place_name'],
                'location': p['location'],
            }
        else:
            r = {
                'primary': u'%s' % (p['street_name']),
                'secondary': p['place_name'],
                'location': p['location'],
            }

        dupe_candidate = (r['primary'], r['secondary'])
        if not dupe_candidate in dupes:
            rs.append(r)
            dupes.add(dupe_candidate)
    return rs


def prepare_q(q):
    q = q.lower()
    q = q.replace(',', ' ')
    q = q.replace('.', ' ')
    q = ' '.join(q.split())
    return q


def prepare_p(p):
    p = p[0:-1]
    a, b = p.split(',')
    p = (float(a), float(b))
    return p


@app.route('/ping')
def ping():
    return 'pong'


@app.route('/api/auto_complete')
def auto_complete():
    q = prepare_q(request.values['q'])
    if request.values.has_key('p'):
        p = prepare_p(request.values['p'])
        print 'using given position', p
    else:
        p = [ 55.7091, 13.2010 ]
        print 'using default position', p

    results = []

    mark = datetime.now()
    results.extend(find_places(q, p))
    print 'find_places %f seconds' % (datetime.now() - mark).total_seconds()

    mark = datetime.now()
    results.extend(find_streets(q, p))
    print 'find_streets %f seconds' % (datetime.now() - mark).total_seconds()

    msg = u'%s: %d\n' % (q, len(results))
    msg = msg.encode('utf-8')
    with open('q.log', 'a') as f:
        f.write(msg)
    return jsonify(results=results)


@app.teardown_appcontext
def close_connection(exception):
    db_client = getattr(g, '_db_client', None)
    if db_client is not None:
        db_client.close()


if __name__ == '__main__':
    app.debug = True
    app.run()
